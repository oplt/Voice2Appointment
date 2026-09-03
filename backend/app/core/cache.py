"""Thin Redis JSON cache with TTL and tenant-versioned keys."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = None
_retry_after: float = 0  # monotonic time; retry connection after this
_failure_count: int = 0
_reset_count: int = 0

CACHE_TTL_CALENDAR = 45
CACHE_TTL_DASHBOARD = 45
CACHE_TTL_STATUS = 60
CACHE_TTL_SETTINGS = 180
CACHE_TTL_ANALYTICS = 300
CACHE_TTL_ANALYTICS_EMPTY = 60


def cache_failure_counts() -> dict[str, int]:
    return {"failures": _failure_count, "resets": _reset_count}


def _is_connection_failure(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    needles = ("timeout", "connection", "closed", "reset", "broken pipe", "busy")
    return any(n in name or n in text for n in needles)


def _reset_client(exc: BaseException | None = None) -> None:
    global _client, _retry_after, _failure_count, _reset_count
    _failure_count += 1
    if _client is not None:
        try:
            _client.close()
        except Exception:  # noqa: BLE001
            pass
        _client = None
        _reset_count += 1
    import time

    _retry_after = time.monotonic() + settings.redis_retry_after_seconds
    if exc is not None:
        logger.warning("Redis client reset: %s", exc.__class__.__name__)


def _redis():
    import time

    global _client, _retry_after
    if _client is not None:
        return _client
    now = time.monotonic()
    if now < _retry_after:
        return None
    try:
        import redis

        _client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=settings.redis_socket_connect_timeout,
            socket_timeout=settings.redis_socket_timeout,
            socket_keepalive=True,
        )
        _client.ping()
        return _client
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis cache unavailable: %s", exc)
        _reset_client(exc)
        return None


def cache_get(key: str) -> Any | None:
    client = _redis()
    if client is None:
        return None
    try:
        raw = client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        if _is_connection_failure(exc):
            _reset_client(exc)
        else:
            logger.debug("cache_get failed key=%s: %s", key, exc)
        return None


def cache_set(key: str, value: Any, *, ttl_seconds: int) -> None:
    client = _redis()
    if client is None:
        return
    try:
        client.setex(key, ttl_seconds, json.dumps(value, default=str))
    except Exception as exc:  # noqa: BLE001
        if _is_connection_failure(exc):
            _reset_client(exc)
        else:
            logger.debug("cache_set failed key=%s: %s", key, exc)


def cache_delete(*keys: str) -> None:
    client = _redis()
    if client is None or not keys:
        return
    try:
        client.delete(*keys)
    except Exception as exc:  # noqa: BLE001
        if _is_connection_failure(exc):
            _reset_client(exc)
        else:
            logger.debug("cache_delete failed: %s", exc)


def cache_delete_prefix(prefix: str) -> None:
    """Legacy SCAN helper; prefer tenant-version bumps (P1-08)."""
    client = _redis()
    if client is None:
        return
    try:
        for key in client.scan_iter(match=f"{prefix}*", count=100):
            client.delete(key)
    except Exception as exc:  # noqa: BLE001
        if _is_connection_failure(exc):
            _reset_client(exc)
        else:
            logger.debug("cache_delete_prefix failed prefix=%s: %s", prefix, exc)


def cache_version(user_id: int, namespace: str) -> int:
    client = _redis()
    if client is None:
        return 0
    try:
        raw = client.get(f"cv:{user_id}:{namespace}")
        return int(raw or 0)
    except Exception as exc:  # noqa: BLE001
        if _is_connection_failure(exc):
            _reset_client(exc)
        return 0


def bump_cache_version(user_id: int, namespace: str) -> None:
    client = _redis()
    if client is None:
        return
    try:
        client.incr(f"cv:{user_id}:{namespace}")
    except Exception as exc:  # noqa: BLE001
        if _is_connection_failure(exc):
            _reset_client(exc)


def versioned_key(user_id: int, namespace: str, *parts: Any) -> str:
    ver = cache_version(user_id, namespace)
    tail = ":".join("" if p is None else str(p) for p in parts)
    return f"{namespace}:v{ver}:{user_id}:{tail}"


def invalidate_user_calendar_caches(user_id: int) -> None:
    bump_cache_version(user_id, "cal")
    bump_cache_version(user_id, "dashboard")


def invalidate_user_analytics_caches(user_id: int) -> None:
    bump_cache_version(user_id, "analytics")


def invalidate_user_settings_cache(user_id: int) -> None:
    bump_cache_version(user_id, "settings")
