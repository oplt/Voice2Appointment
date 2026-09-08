"""Tenant-safe JSON caching with durable database-backed generations."""

from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import cache_backend

CACHE_TTL_CALENDAR = 45
CACHE_TTL_DASHBOARD = 45
CACHE_TTL_STATUS = 300
CACHE_TTL_SETTINGS = 900
CACHE_TTL_ANALYTICS = 300
CACHE_TTL_ANALYTICS_EMPTY = 60

_VERSION_ATTRS = {
    "cal": "cache_calendar_version",
    "dashboard": "cache_dashboard_version",
    "analytics": "cache_analytics_version",
    "settings": "cache_settings_version",
}


def cache_get(key: str) -> Any | None:
    client = cache_backend.redis_client()
    if client is None:
        return None
    try:
        started = time.perf_counter()
        raw = client.get(key)
        cache_backend.note_success(
            "get", latency_ms=(time.perf_counter() - started) * 1000.0
        )
        return None if raw is None else json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        cache_backend.note_failure(
            exc, "get", latency_ms=(time.perf_counter() - started) * 1000.0
        )
        return None


def cache_set(key: str, value: Any, *, ttl_seconds: int) -> None:
    client = cache_backend.redis_client()
    if client is None:
        return
    try:
        started = time.perf_counter()
        client.setex(key, ttl_seconds, json.dumps(value, default=str))
        cache_backend.note_success(
            "set", latency_ms=(time.perf_counter() - started) * 1000.0
        )
    except Exception as exc:  # noqa: BLE001
        cache_backend.note_failure(
            exc, "set", latency_ms=(time.perf_counter() - started) * 1000.0
        )


def cache_get_many(keys: list[str]) -> dict[str, Any]:
    """Fetch independent cache values in one Redis round trip when available."""
    client = cache_backend.redis_client()
    if client is None or not keys:
        return {}
    try:
        started = time.perf_counter()
        raw_values = client.mget(keys)
        cache_backend.note_success(
            "mget", latency_ms=(time.perf_counter() - started) * 1000.0
        )
        return {
            key: json.loads(value)
            for key, value in zip(keys, raw_values, strict=True)
            if value is not None
        }
    except Exception as exc:  # noqa: BLE001
        cache_backend.note_failure(
            exc, "mget", latency_ms=(time.perf_counter() - started) * 1000.0
        )
        return {}


def cache_delete(*keys: str) -> None:
    client = cache_backend.redis_client()
    if client is None or not keys:
        return
    try:
        started = time.perf_counter()
        client.delete(*keys)
        cache_backend.note_success(
            "delete", latency_ms=(time.perf_counter() - started) * 1000.0
        )
    except Exception as exc:  # noqa: BLE001
        cache_backend.note_failure(
            exc, "delete", latency_ms=(time.perf_counter() - started) * 1000.0
        )


def cache_failure_counts() -> dict[str, int]:
    return cache_backend.failure_counts()


def versioned_key(
    user_id: int,
    namespace: str,
    *parts: Any,
    generation: int,
) -> str:
    tail = ":".join("" if part is None else str(part) for part in parts)
    return f"{namespace}:v{generation}:{user_id}:{tail}"


def durable_versioned_key(
    db: Session,
    user_id: int,
    namespace: str,
    *parts: Any,
) -> str:
    """Build a key whose generation survives Redis outages and process restarts."""
    from app.db.models import User

    attr = _VERSION_ATTRS.get(namespace)
    if attr is None:
        raise ValueError(f"unsupported cache namespace: {namespace}")
    memo: dict[tuple[int, str], int] = db.info.setdefault("cache_generation_memo", {})
    memo_key = (user_id, namespace)
    generation = memo.get(memo_key)
    if generation is None:
        generation = int(
            db.scalar(select(getattr(User, attr)).where(User.id == user_id)) or 0
        )
        memo[memo_key] = generation
    return versioned_key(
        user_id,
        namespace,
        *parts,
        generation=generation,
    )
