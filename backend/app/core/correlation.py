"""Cross-boundary correlation identifiers (Phase 12).

Links Twilio call → voice websocket → Deepgram session → voice tool →
booking/provider work → Celery tasks via a single ``correlation_id``.

Never put phone numbers or transcripts into correlation IDs.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Any

from app.core.logging import (
    bind_log_context,
    get_call_sid,
    get_request_id,
    reset_log_context,
)

_correlation_id: ContextVar[str | None] = ContextVar("log_correlation_id", default=None)

CORRELATION_HEADER = "X-Correlation-ID"
CELERY_CORRELATION_HEADER = "va_correlation_id"
CELERY_REQUEST_HEADER = "va_request_id"
CELERY_CALL_SID_HEADER = "va_call_sid"


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def resolve_correlation_id(
    *,
    explicit: str | None = None,
    call_sid: str | None = None,
    request_id: str | None = None,
) -> str:
    """Prefer stable call identity, then request, then fresh UUID."""
    if explicit and explicit.strip():
        return explicit.strip()[:64]
    if call_sid and call_sid.strip():
        return f"call:{call_sid.strip()[:48]}"
    existing = get_correlation_id()
    if existing:
        return existing
    if request_id and request_id.strip():
        return request_id.strip()[:64]
    rid = get_request_id()
    if rid:
        return rid
    sid = get_call_sid()
    if sid:
        return f"call:{sid[:48]}"
    return new_correlation_id()


def bind_correlation(
    *,
    correlation_id: str | None = None,
    request_id: str | None = None,
    call_sid: str | None = None,
    user_id: int | None = None,
    operation: str | None = None,
) -> dict[str, Any]:
    """Bind logging + correlation context; return reset tokens."""
    cid = resolve_correlation_id(
        explicit=correlation_id,
        call_sid=call_sid,
        request_id=request_id,
    )
    tokens = bind_log_context(
        request_id=request_id,
        call_sid=call_sid,
        user_id=user_id,
        operation=operation,
    )
    tokens["correlation_id"] = _correlation_id.set(cid)
    return tokens


def reset_correlation(tokens: dict[str, Any]) -> None:
    corr_token = tokens.pop("correlation_id", None)
    if corr_token is not None:
        _correlation_id.reset(corr_token)
    reset_log_context(tokens)


def celery_correlation_headers() -> dict[str, str]:
    """Headers to attach when publishing Celery tasks from an active request."""
    headers: dict[str, str] = {
        CELERY_CORRELATION_HEADER: resolve_correlation_id(),
    }
    rid = get_request_id()
    if rid:
        headers[CELERY_REQUEST_HEADER] = rid
    sid = get_call_sid()
    if sid:
        headers[CELERY_CALL_SID_HEADER] = sid
    return headers
