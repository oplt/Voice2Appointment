"""Structured logging with request/call context (Phase 13.1).

Never log API keys, auth tokens, full transcripts, full phone numbers,
or calendar descriptions at info/warning levels.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterator

from app.core.config import settings

_REPO_ROOT = Path(__file__).resolve().parents[3]

_request_id: ContextVar[str | None] = ContextVar("log_request_id", default=None)
_call_sid: ContextVar[str | None] = ContextVar("log_call_sid", default=None)
_user_id: ContextVar[int | None] = ContextVar("log_user_id", default=None)
_operation: ContextVar[str | None] = ContextVar("log_operation", default=None)

_PHONE_RE = re.compile(r"(\+?\d[\d\-\s()]{6,}\d)")
_SECRET_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "auth_token",
        "token",
        "password",
        "secret",
        "fernet_key",
        "deepgram_api_key",
        "twilio_auth_token",
        "credentials_json",
        "token_json",
    }
)
_SENSITIVE_CONTENT_KEYS = frozenset(
    {
        "transcript",
        "content",
        "text",
        "prompt",
        "description",
        "notes",
        "message",
    }
)


def get_request_id() -> str | None:
    return _request_id.get()


def get_call_sid() -> str | None:
    return _call_sid.get()


def get_user_id() -> int | None:
    return _user_id.get()


def get_operation() -> str | None:
    return _operation.get()


def new_request_id() -> str:
    return uuid.uuid4().hex


def bind_log_context(
    *,
    request_id: str | None = None,
    call_sid: str | None = None,
    user_id: int | None = None,
    operation: str | None = None,
) -> dict[str, Any]:
    """Bind identifiers into contextvars; return tokens for reset."""
    tokens: dict[str, Any] = {}
    if request_id is not None:
        tokens["request_id"] = _request_id.set(request_id)
    if call_sid is not None:
        tokens["call_sid"] = _call_sid.set(call_sid)
    if user_id is not None:
        tokens["user_id"] = _user_id.set(user_id)
    if operation is not None:
        tokens["operation"] = _operation.set(operation)
    return tokens


def reset_log_context(tokens: dict[str, Any]) -> None:
    if "request_id" in tokens:
        _request_id.reset(tokens["request_id"])
    if "call_sid" in tokens:
        _call_sid.reset(tokens["call_sid"])
    if "user_id" in tokens:
        _user_id.reset(tokens["user_id"])
    if "operation" in tokens:
        _operation.reset(tokens["operation"])


@contextmanager
def log_context(
    *,
    request_id: str | None = None,
    call_sid: str | None = None,
    user_id: int | None = None,
    operation: str | None = None,
) -> Iterator[None]:
    tokens = bind_log_context(
        request_id=request_id,
        call_sid=call_sid,
        user_id=user_id,
        operation=operation,
    )
    try:
        yield
    finally:
        reset_log_context(tokens)


def mask_phone(value: str | None) -> str | None:
    if not value:
        return value
    digits = re.sub(r"\D", "", value)
    if len(digits) <= 4:
        return "****"
    return f"***{digits[-4:]}"


def redact_phones(text: str) -> str:
    def _sub(match: re.Match[str]) -> str:
        return mask_phone(match.group(0)) or "****"

    return _PHONE_RE.sub(_sub, text)


def sanitize_for_log(value: Any, *, depth: int = 0) -> Any:
    """Recursively redact secrets, phones, and long free-text fields."""
    if depth > 4:
        return "[truncated]"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            lower = str(key).lower()
            if lower in _SECRET_KEYS or any(s in lower for s in ("token", "password", "secret", "api_key")):
                out[key] = "[redacted]"
            elif lower in _SENSITIVE_CONTENT_KEYS and isinstance(item, str) and len(item) > 24:
                out[key] = f"[redacted:{len(item)}chars]"
            elif lower in {"from", "to", "from_number", "to_number", "client_phone", "phone"}:
                out[key] = mask_phone(str(item)) if item is not None else None
            else:
                out[key] = sanitize_for_log(item, depth=depth + 1)
        return out
    if isinstance(value, list):
        return [sanitize_for_log(v, depth=depth + 1) for v in value[:20]]
    if isinstance(value, str):
        return redact_phones(value)
    return value


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        record.call_sid = get_call_sid() or "-"
        record.user_id = get_user_id() if get_user_id() is not None else "-"
        record.operation = get_operation() or "-"
        return True


class StructuredFormatter(logging.Formatter):
    """JSON line formatter with standard observability fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "call_sid": getattr(record, "call_sid", "-"),
            "user_id": getattr(record, "user_id", "-"),
            "operation": getattr(record, "operation", "-"),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        # Attach non-standard extras (latency_ms, event, etc.).
        reserved = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "message",
            "request_id",
            "call_sid",
            "user_id",
            "operation",
            "asctime",
        }
        for key, value in record.__dict__.items():
            if key not in reserved and not key.startswith("_"):
                payload[key] = sanitize_for_log(value)
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = (
            f"{self.formatTime(record, datefmt='%Y-%m-%d %H:%M:%S')} "
            f"[{record.levelname}] {record.name} "
            f"request_id={getattr(record, 'request_id', '-')} "
            f"call_sid={getattr(record, 'call_sid', '-')} "
            f"user_id={getattr(record, 'user_id', '-')} "
            f"operation={getattr(record, 'operation', '-')} "
            f"{record.getMessage()}"
        )
        if record.exc_info:
            base = f"{base}\n{self.formatException(record.exc_info)}"
        return base


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Emit a structured event without putting secrets in the message."""
    safe = {k: sanitize_for_log(v) for k, v in fields.items()}
    logger.log(level, event, extra={"event": event, **safe})


def setup_logging() -> None:
    log_level = logging.DEBUG if settings.debug else logging.INFO
    logging.Formatter.converter = time.gmtime

    root = logging.getLogger()
    root.setLevel(log_level)
    # Replace handlers so format/env changes apply on re-init.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    use_json = (settings.log_format or "json").strip().lower() == "json"
    formatter: logging.Formatter = (
        StructuredFormatter() if use_json else TextFormatter()
    )
    context_filter = ContextFilter()

    log_dir = _REPO_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        log_dir / "VoiceAsst.log", maxBytes=5_000_000, backupCount=5
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)
    file_handler.addFilter(context_filter)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.setLevel(log_level)
    console.addFilter(context_filter)

    root.addHandler(file_handler)
    root.addHandler(console)

    # Quiet noisy libraries.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
