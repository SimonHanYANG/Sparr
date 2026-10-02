"""MinerU open API client (docs: https://mineru.net/apiManage/docs).

Two parsing modes — the pipeline prefers accurate and falls back to the
lightweight Agent API when the cloud queue is slow (user requirement):

🎯 精准解析 (accurate, token required)
   POST /api/v4/file-urls/batch   {files:[{name}], is_ocr, enable_table,
                                   enable_formula, language, model_version}
     -> {batch_id, file_urls:[presigned OSS url]}
   PUT  <presigned url>  raw bytes, NO Content-Type (signature covers it)
   GET  /api/v4/extract-results/batch/{batch_id}
     -> {extract_result:[{file_name, state, err_msg, full_zip_url,
                          extract_progress{extracted_pages,total_pages}}]}
   states: waiting-file | pending | running | converting | done | failed
   done output: full_zip_url — zip containing full.md (markdown) + jsons

⚡ Agent 轻量解析 (lightweight, NO token — IP rate-limited)
   POST /api/v1/agent/parse/file {file_name, language, enable_table, is_ocr}
     -> {task_id, file_url}
   PUT  <file_url>  raw bytes (same rule)
   GET  /api/v1/agent/parse/{task_id}
     -> {task_id, state, markdown_url, err_msg, err_code}
   states: waiting-file | uploading | pending | running | done | failed
   done output: markdown_url — CDN link to full.md
   limits: ≤10MB, ≤20 pages, single file
"""
import io
import time
import zipfile

import httpx
from django.conf import settings


class MinerUError(Exception):
    pass


class MinerUClient:
    ACCURATE = "accurate"
    AGENT = "agent"

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
    # 🎯 精准解析
    # ------------------------------------------------------------------
    def submit_pdf(self, content: bytes, filename: str, *,
                   is_ocr: bool = True, language: str = "ch",
                   model_version: str = "vlm") -> str:
        """Accurate parse: upload one PDF and start extraction; returns batch_id."""
        payload = {
            "files": [{"name": filename}],
            "is_ocr": is_ocr,
            "enable_table": True,
            "enable_formula": True,
            "language": language,
            "model_version": model_version,
        }
        batch_id, upload_url = self._request_upload_urls(payload)
        self._put_file(upload_url, content)
        return batch_id

    def get_results(self, batch_id: str) -> list[dict]:
        resp = httpx.get(f"{self.base_url}/extract-results/batch/{batch_id}",
                         headers=self._headers(), timeout=30)
        body = _safe_json(resp)
        if body.get("code") != 0:
            raise MinerUError(f"MinerU result poll failed: {str(body)[:300]}")
        return (body.get("data") or {}).get("extract_result") or []

    def wait_for_result(self, batch_id: str, timeout_s: int = 1200,
                        interval_s: float = 3.0) -> dict:
        """Poll accurate-parse until done/failed/timeout.

        Returns the file result dict; raises MinerUError on failed/timeout.
        Interval backs off 3s -> 10s (cloud queue can hold tasks for minutes).
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
        raise MinerUTimeout(f"accurate parse still '{last_state or 'unknown'}' after {timeout_s}s")

    def fetch_markdown(self, result_item: dict) -> str:
        """Accurate-parse done item -> markdown text (full.md inside full_zip_url)."""
        zip_url = result_item.get("full_zip_url")
        if not zip_url:
            raise MinerUError(f"no full_zip_url in result (keys: {list(result_item.keys())})")
        resp = _download(zip_url)
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            for name in zf.namelist():
                if name.endswith("full.md"):
                    return zf.read(name).decode("utf-8", errors="replace")
        raise MinerUError(f"full.md not found in zip (files: {zf.namelist()[:10]})")

    # ------------------------------------------------------------------
    # ⚡ Agent 轻量解析 (no token)
    # ------------------------------------------------------------------
    def submit_pdf_agent(self, content: bytes, filename: str, *,
                         is_ocr: bool = True, language: str = "ch") -> str:
        """Lightweight Agent parse; returns task_id. Limits: ≤10MB, ≤20 pages."""
        resp = httpx.post(
            "https://mineru.net/api/v1/agent/parse/file",
            json={"file_name": filename, "language": language,
                  "enable_table": True, "is_ocr": is_ocr},
            timeout=60,
        )
        body = _safe_json(resp)
        data = body.get("data") or {}
        if body.get("code") != 0 or not data.get("task_id"):
            raise MinerUError(f"agent parse submit failed: {str(body)[:300]}")
        self._put_file(data["file_url"], content)
        return data["task_id"]

    def wait_for_agent_result(self, task_id: str, timeout_s: int = 600,
                              interval_s: float = 3.0) -> dict:
        deadline = time.monotonic() + timeout_s
        started = time.monotonic()
        last_state = ""
        while time.monotonic() < deadline:
            resp = httpx.get(f"https://mineru.net/api/v1/agent/parse/{task_id}", timeout=30)
            body = _safe_json(resp)
            data = body.get("data") or {}
            state = data.get("state", "")
            if state != last_state:
                last_state = state
            if state == "done":
                return data
            if state == "failed":
                raise MinerUError(
                    f"agent parse failed: {data.get('err_msg', 'unknown')[:200]} "
                    f"(err_code={data.get('err_code')})")
            waited = time.monotonic() - started
            time.sleep(min(10.0, interval_s + waited / 60.0))
        raise MinerUError(f"agent parse timed out after {timeout_s}s (last state: {last_state})")

    def fetch_agent_markdown(self, agent_item: dict) -> str:
        url = agent_item.get("markdown_url")
        if not url:
            raise MinerUError(f"no markdown_url in agent result (keys: {list(agent_item.keys())})")
        return _download(url).text

    # ------------------------------------------------------------------
    def _request_upload_urls(self, payload: dict) -> tuple[str, str]:
        resp = httpx.post(f"{self.base_url}/file-urls/batch",
                          headers=self._headers(), json=payload, timeout=60)
        body = _safe_json(resp)
        if body.get("code") != 0 or not body.get("data"):
            raise MinerUError(f"MinerU upload-url request failed: {str(body)[:300]}")
        return body["data"]["batch_id"], body["data"]["file_urls"][0]

    @staticmethod
    def _put_file(upload_url: str, content: bytes) -> None:
        # NO Content-Type header — the presigned signature forbids it
        put = httpx.put(upload_url, content=content, timeout=300)
        if put.status_code != 200:
            raise MinerUError(f"MinerU OSS upload failed: HTTP {put.status_code}")


class MinerUTimeout(MinerUError):
    """Accurate parse exceeded the patience window — caller may fall back to Agent."""


def _safe_json(resp: httpx.Response) -> dict:
    try:
        return resp.json()
    except ValueError:
        return {}


def _download(url: str, attempts: int = 3) -> httpx.Response:
    """CDN download with retries — proxy/SSL drops happen intermittently."""
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            resp = httpx.get(url, timeout=120, follow_redirects=True)
            resp.raise_for_status()
            return resp
        except (httpx.HTTPError, httpx.TransportError) as exc:
            last_exc = exc
            time.sleep(2 * (attempt + 1))
    raise MinerUError(f"download failed after {attempts} attempts: {last_exc}")
