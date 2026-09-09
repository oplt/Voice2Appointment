"""Bounded Redis connection lifecycle and low-cardinality telemetry."""

from __future__ import annotations

import logging
import time
from threading import Lock
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
_state_lock = Lock()


def _is_pool_exhaustion(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return "maxconnections" in text or "no connection available" in text


def _is_connection_failure(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    needles = ("timeout", "connection", "closed", "reset", "broken pipe", "busy")
    return _is_pool_exhaustion(exc) or any(part in text for part in needles)


def _close_client() -> None:
    global _client, _reset_count
    with _state_lock:
        client = _client
        if client is None:
            return
        _client = None
        _reset_count += 1
    try:
        client.close()
    except Exception:  # noqa: BLE001
        pass
    metrics.incr("cache_events", labels={"cache": "redis", "result": "reset"})


def note_failure(
    exc: BaseException, operation: str, *, latency_ms: float | None = None
) -> None:
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
    if latency_ms is not None:
        metrics.observe(
            "redis_latency_ms",
            latency_ms,
            labels={"operation": operation, "result": result},
        )
    if _is_connection_failure(exc):
        _close_client()
        _retry_after = time.monotonic() + settings.redis_retry_after_seconds
        logger.warning("Redis client reset: %s", type(exc).__name__)


def note_success(operation: str, *, latency_ms: float | None = None) -> None:
    metrics.incr(
        "cache_operations",
        labels={"cache": "redis", "operation": operation, "result": "success"},
    )
    if latency_ms is not None:
        metrics.observe(
            "redis_latency_ms",
            latency_ms,
            labels={"operation": operation, "result": "success"},
        )


def redis_client() -> Any | None:
    global _client, _retry_after, _degraded, _recovery_count
    with _state_lock:
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
        started = time.perf_counter()
        client.ping()
        note_success("connect", latency_ms=(time.perf_counter() - started) * 1000.0)
        with _state_lock:
            if _client is None:
                _client = client
                if _degraded:
                    _degraded = False
                    _recovery_count += 1
                    metrics.incr(
                        "cache_events", labels={"cache": "redis", "result": "recovery"}
                    )
                return _client
        try:
            client.close()
        except Exception:  # noqa: BLE001
            pass
        with _state_lock:
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
