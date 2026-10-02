"""MinerU open API v4 client for resume PDF parsing (PLAN.md §5.1).

Contract verified live against https://mineru.net/api/v4 (2026-10-02):
1. POST /file-urls/batch  {files:[{name}]}            -> {batch_id, file_urls:[presigned OSS url]}
2. PUT  <presigned url>   (raw bytes, NO Content-Type) — adding Content-Type breaks the signature
3. GET  /extract-results/batch/{batch_id}             -> {extract_result:[{file_name, state, err_msg, ...}]}
   state machine: waiting-file -> pending -> done | failed

User-supplied API key (ProviderCredential, decrypted in memory only).
"""
import time

import httpx
from django.conf import settings


class MinerUError(Exception):
    pass


class MinerUClient:
    def __init__(self, api_key: str, base_url: str | None = None):
        self.api_key = api_key
        self.base_url = (base_url or settings.MINERU_BASE_URL).rstrip("/")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"}

    # ------------------------------------------------------------------
    def validate_key(self) -> tuple[bool, str]:
        """Cheap auth check: an empty file list answers through the auth layer."""
        try:
            resp = httpx.post(f"{self.base_url}/file-urls/batch",
                              headers=self._headers(), json={"files": []}, timeout=30)
        except httpx.HTTPError as exc:
            return False, f"MinerU unreachable: {exc}"
        body = _safe_json(resp)
        if resp.status_code == 200 and body.get("code") in (0, -10002):
            return True, "ok"
        if body.get("success") is False or resp.status_code in (401, 403):
            return False, body.get("msg") or "invalid MinerU API key"
        return False, f"MinerU HTTP {resp.status_code}: {str(body)[:200]}"

    # ------------------------------------------------------------------
    def submit_pdf(self, content: bytes, filename: str) -> str:
        """Upload one PDF and start extraction; returns batch_id for polling."""
        with httpx.Client(timeout=120) as client:
            resp = client.post(f"{self.base_url}/file-urls/batch", headers=self._headers(),
                               json={"files": [{"name": filename}]})
            body = _safe_json(resp)
            if body.get("code") != 0 or not body.get("data"):
                raise MinerUError(f"MinerU upload-url request failed: {str(body)[:300]}")
            batch_id = body["data"]["batch_id"]
            upload_url = body["data"]["file_urls"][0]

            # NO Content-Type header — the presigned signature forbids it
            put = client.put(upload_url, content=content)
            if put.status_code != 200:
                raise MinerUError(f"MinerU OSS upload failed: HTTP {put.status_code}")
            return batch_id

    def get_results(self, batch_id: str) -> list[dict]:
        resp = httpx.get(f"{self.base_url}/extract-results/batch/{batch_id}",
                         headers=self._headers(), timeout=30)
        body = _safe_json(resp)
        if body.get("code") != 0:
            raise MinerUError(f"MinerU result poll failed: {str(body)[:300]}")
        return (body.get("data") or {}).get("extract_result") or []

    def wait_for_result(self, batch_id: str, timeout_s: int = 1200, interval_s: float = 3.0) -> dict:
        """Poll until state is done/failed; returns the file result dict.

        Interval backs off 3s -> 10s: MinerU's cloud queue can hold tasks for
        several minutes (observed live), so long waits must stay cheap.
        """
        deadline = time.monotonic() + timeout_s
        started = time.monotonic()
        last_state = ""
        while time.monotonic() < deadline:
            items = self.get_results(batch_id)
            if items:
                item = items[0]
                state = item.get("state", "")
                if state != last_state:
                    last_state = state
                if state == "done":
                    return item
                if state == "failed":
                    raise MinerUError(f"MinerU parse failed: {item.get('err_msg', 'unknown')[:300]}")
            waited = time.monotonic() - started
            time.sleep(min(10.0, interval_s + waited / 60.0))
        raise MinerUError(f"MinerU parse timed out after {timeout_s}s (last state: {last_state or 'unknown'})")


def _safe_json(resp: httpx.Response) -> dict:
    try:
        return resp.json()
    except ValueError:
        return {}
