"""MinerU open API client for resume PDF parsing (PLAN.md §5.1).

User-supplied API key; the actual parse pipeline (PDF → markdown →
structured extraction) lands in Phase 1. This module fixes the interface
and key validation now.
"""
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

    def validate_key(self) -> tuple[bool, str]:
        """Lightweight call to verify the key; full parse comes in Phase 1."""
        try:
            resp = httpx.get(f"{self.base_url}/users/me", headers=self._headers(), timeout=30)
            if resp.status_code in (200, 201):
                return True, "ok"
            if resp.status_code == 401:
                return False, "invalid MinerU API key"
            return False, f"MinerU HTTP {resp.status_code}"
        except httpx.HTTPError as exc:
            return False, f"MinerU unreachable: {exc}"
