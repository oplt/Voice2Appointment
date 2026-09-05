"""Bounded Redis connection lifecycle and low-cardinality telemetry."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.core.config import settings
from app.core.metrics import metrics

logger = logging.getLogger(__name__)

_client: Any | None = None
_retry_after = 0.0
_failure_count = 0
_reset_count = 0
_pool_exhaustion_count = 0
_recovery_count = 0
_degraded = False


def _is_pool_exhaustion(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return "maxconnections" in text or "no connection available" in text


def _is_connection_failure(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    needles = ("timeout", "connection", "closed", "reset", "broken pipe", "busy")
    return _is_pool_exhaustion(exc) or any(part in text for part in needles)


def _close_client() -> None:
    global _client, _reset_count
    if _client is None:
        return
    try:
        _client.close()
    except Exception:  # noqa: BLE001
        pass
    _client = None
    _reset_count += 1
    metrics.incr("cache_events", labels={"cache": "redis", "result": "reset"})


def note_failure(exc: BaseException, operation: str) -> None:
    global _failure_count, _pool_exhaustion_count, _retry_after, _degraded
    _failure_count += 1
    _degraded = True
    result = "pool_exhaustion" if _is_pool_exhaustion(exc) else "failure"
    if result == "pool_exhaustion":
        _pool_exhaustion_count += 1
    metrics.incr(
        "cache_events",
        labels={"cache": "redis", "operation": operation, "result": result},
    )
    if _is_connection_failure(exc):
        _close_client()
        _retry_after = time.monotonic() + settings.redis_retry_after_seconds
        logger.warning("Redis client reset: %s", type(exc).__name__)


def note_success(operation: str) -> None:
    metrics.incr(
        "cache_operations",
        labels={"cache": "redis", "operation": operation, "result": "success"},
    )


def redis_client() -> Any | None:
    global _client, _retry_after, _degraded, _recovery_count
    if _client is not None:
        return _client
    if time.monotonic() < _retry_after:
        return None
    try:
        import redis

        pool = redis.BlockingConnectionPool.from_url(
            settings.redis_url,
            max_connections=settings.redis_max_connections,
            timeout=settings.redis_pool_timeout,
            decode_responses=True,
            socket_connect_timeout=settings.redis_socket_connect_timeout,
            socket_timeout=settings.redis_socket_timeout,
            socket_keepalive=True,
        )
        client = redis.Redis(connection_pool=pool)
        client.ping()
        _client = client
        if _degraded:
            _degraded = False
            _recovery_count += 1
            metrics.incr(
                "cache_events", labels={"cache": "redis", "result": "recovery"}
            )
        return _client
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis cache unavailable: %s", type(exc).__name__)
        note_failure(exc, "connect")
        return None


def failure_counts() -> dict[str, int]:
    return {
        "failures": _failure_count,
        "resets": _reset_count,
        "pool_exhaustions": _pool_exhaustion_count,
        "recoveries": _recovery_count,
    }


def reset_state() -> None:
    """Test helper; reset process-local client and counters."""
    global _client, _retry_after, _failure_count, _reset_count
    global _pool_exhaustion_count, _recovery_count, _degraded
    _close_client()
    _client = None
    _retry_after = 0.0
    _failure_count = 0
    _reset_count = 0
    _pool_exhaustion_count = 0
    _recovery_count = 0
    _degraded = False
