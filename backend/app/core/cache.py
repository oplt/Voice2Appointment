"""Thin Redis JSON cache with TTL (Phase 9.4)."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = None
_client_failed = False


def _redis():
    global _client, _client_failed
    if _client_failed:
        return None
    if _client is not None:
        return _client
    try:
        import redis

        _client = redis.Redis.from_url(
            settings.redis_url, decode_responses=True, socket_connect_timeout=0.5
        )
        _client.ping()
        return _client
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis cache unavailable: %s", exc)
        _client_failed = True
        _client = None
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
        logger.debug("cache_get failed key=%s: %s", key, exc)
        return None


def cache_set(key: str, value: Any, *, ttl_seconds: int) -> None:
    client = _redis()
    if client is None:
        return
    try:
        client.setex(key, ttl_seconds, json.dumps(value, default=str))
    except Exception as exc:  # noqa: BLE001
        logger.debug("cache_set failed key=%s: %s", key, exc)


def cache_delete(*keys: str) -> None:
    client = _redis()
    if client is None or not keys:
        return
    try:
        client.delete(*keys)
    except Exception as exc:  # noqa: BLE001
        logger.debug("cache_delete failed: %s", exc)


def cache_delete_prefix(prefix: str) -> None:
    client = _redis()
    if client is None:
        return
    try:
        for key in client.scan_iter(match=f"{prefix}*", count=100):
            client.delete(key)
    except Exception as exc:  # noqa: BLE001
        logger.debug("cache_delete_prefix failed prefix=%s: %s", prefix, exc)


def invalidate_user_calendar_caches(user_id: int) -> None:
    cache_delete_prefix(f"cal:events:{user_id}:")
    cache_delete(f"cal:status:{user_id}")
    cache_delete(f"dashboard:summary:{user_id}")


def invalidate_user_analytics_caches(user_id: int) -> None:
    cache_delete_prefix(f"analytics:summary:{user_id}:")


def invalidate_user_settings_cache(user_id: int) -> None:
    cache_delete(f"user:settings:{user_id}")
