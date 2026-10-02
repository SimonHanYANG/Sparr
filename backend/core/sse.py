"""Server-Sent Events helpers for streaming interview/exam dialogue (PLAN.md §6).

Event types: delta | turn_eval | phase_change | done | error
"""
import json

from django.http import StreamingHttpResponse


def sse_event(event: str, data: dict | str, event_id: str | None = None) -> str:
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    parts = []
    if event_id:
        parts.append(f"id: {event_id}")
    parts.append(f"event: {event}")
    for line in payload.splitlines() or [""]:
        parts.append(f"data: {line}")
    return "\n".join(parts) + "\n\n"


def sse_response(iterator) -> StreamingHttpResponse:
    """Wrap an iterator of sse_event() strings as a no-buffering streaming response."""
    response = StreamingHttpResponse(iterator, content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # disable proxy buffering (PLAN.md §11.0)
    return response
