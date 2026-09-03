"""Optional Sentry error monitoring (Phase 13.4)."""

from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)
_initialized = False


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
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
    )
    _initialized = True
    logger.info("Sentry error monitoring enabled")
    return True
