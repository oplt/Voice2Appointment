"""Tenant-safe JSON caching with durable database-backed generations."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import cache_backend

CACHE_TTL_CALENDAR = 45
CACHE_TTL_DASHBOARD = 45
CACHE_TTL_STATUS = 60
CACHE_TTL_SETTINGS = 180
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
        raw = client.get(key)
        cache_backend.note_success("get")
        return None if raw is None else json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        cache_backend.note_failure(exc, "get")
        return None


def cache_set(key: str, value: Any, *, ttl_seconds: int) -> None:
    client = cache_backend.redis_client()
    if client is None:
        return
    try:
        client.setex(key, ttl_seconds, json.dumps(value, default=str))
        cache_backend.note_success("set")
    except Exception as exc:  # noqa: BLE001
        cache_backend.note_failure(exc, "set")


def cache_delete(*keys: str) -> None:
    client = cache_backend.redis_client()
    if client is None or not keys:
        return
    try:
        client.delete(*keys)
        cache_backend.note_success("delete")
    except Exception as exc:  # noqa: BLE001
        cache_backend.note_failure(exc, "delete")


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
    generation = db.scalar(select(getattr(User, attr)).where(User.id == user_id))
    return versioned_key(
        user_id,
        namespace,
        *parts,
        generation=int(generation or 0),
    )
