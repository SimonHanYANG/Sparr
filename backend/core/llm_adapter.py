"""Unified OpenAI-compatible LLM adapter (PLAN.md §2).

DeepSeek v4 and Xiaomi MiMo both speak the OpenAI chat-completions protocol;
providers are configured in settings.LLM_PROVIDERS and can be overridden
per-user with a custom base_url/model. API keys are supplied per call
(decrypted from ProviderCredential in memory, never persisted in logs).

Supports streaming (SSE from upstream, re-yielded as plain text chunks).
"""
from collections.abc import Iterator
from dataclasses import dataclass, field

import httpx
from django.conf import settings


class LLMError(Exception):
    """Upstream LLM call failed (after any retries)."""


@dataclass
class ChatMessage:
    role: str  # system | user | assistant
    content: str


@dataclass
class LLMClient:
    provider: str
    api_key: str
    model: str | None = None
    base_url: str | None = None
    timeout: int = field(default_factory=lambda: settings.LLM_REQUEST_TIMEOUT)

    def __post_init__(self):
        provider_conf = settings.LLM_PROVIDERS.get(self.provider)
        if provider_conf is None and not self.base_url:
            raise LLMError(f"unknown provider: {self.provider}")
        self.base_url = (self.base_url or provider_conf["base_url"]).rstrip("/")
        if self.model is None:
            self.model = provider_conf["default_model"]

    # ------------------------------------------------------------------
    def _headers(self) -> dict:
        # Send both auth styles: OpenAI-compatible Bearer + MiMo's `api-key`
        # header (Token Plan accepts both; others ignore the extra header).
        return {
            "Authorization": f"Bearer {self.api_key}",
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }

    def _payload(self, messages: list[ChatMessage], *, stream: bool,
                 temperature: float = 0.7, max_tokens: int | None = None,
                 **extra) -> dict:
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        payload.update(extra)
        return payload

    # ------------------------------------------------------------------
    def chat(self, messages: list[ChatMessage], **kwargs) -> str:
        """Non-streaming completion; returns full text."""
        url = f"{self.base_url}/chat/completions"
        try:
            resp = httpx.post(url, headers=self._headers(),
                              json=self._payload(messages, stream=False, **kwargs),
                              timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"].get("content") or ""
            if not content:
                # 思考模型（reasoning）会把 max_tokens 预算吃光导致正文为空/截断
                finish = data["choices"][0].get("finish_reason", "")
                raise LLMError(
                    f"LLM {self.provider} returned empty content"
                    + (f" (finish_reason={finish}, 提高 max_tokens 或关闭思考)" if finish else ""))
            return content
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"LLM {self.provider} HTTP {exc.response.status_code}: "
                           f"{exc.response.text[:300]}") from exc
        except (httpx.HTTPError, KeyError, IndexError) as exc:
            raise LLMError(f"LLM {self.provider} call failed: {exc}") from exc

    def chat_stream(self, messages: list[ChatMessage], **kwargs) -> Iterator[str]:
        """Streaming completion; yields incremental text chunks.

        Normalizes upstream SSE (`data: {...}` lines) to plain text deltas,
        so callers/providers stay decoupled (PLAN.md §2).
        """
        url = f"{self.base_url}/chat/completions"
        try:
            with httpx.stream(
                "POST", url, headers=self._headers(),
                json=self._payload(messages, stream=True, **kwargs),
                timeout=self.timeout,
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        return
                    yield _extract_delta(data)
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"LLM {self.provider} HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM {self.provider} stream failed: {exc}") from exc

    # ------------------------------------------------------------------
    def validate_key(self) -> tuple[bool, str]:
        """Minimal request to verify a user-supplied key (PLAN.md §5.1)."""
        try:
            self.chat([ChatMessage(role="user", content="hi")], max_tokens=1, temperature=0)
            return True, "ok"
        except LLMError as exc:
            return False, str(exc)


def fast_completion_kwargs(llm: "LLMClient") -> dict:
    """思考模型（MiMo v2.6 系列会输出 reasoning_content 且计入 max_tokens 预算）
    的提速开关：对时延敏感的调用（交互对话/出题/判卷）关闭 reasoning。
    其他 provider 忽略未知字段/无需该参数。"""
    return {"thinking": {"type": "disabled"}} if llm.provider == "mimo" else {}


def _extract_delta(data: str) -> str:
    """Pull the incremental content out of one SSE JSON chunk."""
    import json

    try:
        chunk = json.loads(data)
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        return delta.get("content") or ""
    except (ValueError, IndexError, AttributeError):
        return ""
