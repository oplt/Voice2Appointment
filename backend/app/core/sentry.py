"""Optional Sentry error monitoring (Phase 13.4)."""

from __future__ import annotations

import logging
import re
from typing import Any, cast

from app.core.config import settings

logger = logging.getLogger(__name__)
_initialized = False


def _redact_voice_stream_path(value: str) -> str:
    return re.sub(r"(/ws/voice/)[^?#\s]+", r"\1[redacted]", value)


def scrub_sensitive_paths(event: dict[str, Any], _hint: Any = None) -> dict[str, Any]:
    """Remove path-bound stream credentials from Sentry errors and traces."""
    request = event.get("request")
    if isinstance(request, dict) and isinstance(request.get("url"), str):
        request["url"] = _redact_voice_stream_path(request["url"])
    if isinstance(event.get("transaction"), str):
        event["transaction"] = _redact_voice_stream_path(event["transaction"])
    return event


def init_sentry() -> bool:
    """Initialize Sentry when SENTRY_DSN is set. Returns True if enabled."""
    global _initialized
    if _initialized:
        return True
    dsn = (settings.sentry_dsn or "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:
        logger.warning("SENTRY_DSN set but sentry-sdk is not installed")
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.app_env,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        include_local_variables=False,
        before_send=cast(Any, scrub_sensitive_paths),
        before_send_transaction=cast(Any, scrub_sensitive_paths),
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
    )
    _initialized = True
    logger.info("Sentry error monitoring enabled")
    return True
