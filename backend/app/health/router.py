"""Liveness and readiness probes (Phase 12.4)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.config import settings

router = APIRouter(tags=["health"])


def check_database() -> tuple[bool, str]:
    from app.db.session import SessionLocal

    if SessionLocal is None:
        return False, "database_url_missing"
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"error:{exc.__class__.__name__}"


def check_redis() -> tuple[bool, str]:
    """Ping Redis only — never external speech/telephony/calendar providers."""
    try:
        import redis

        client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        client.ping()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"error:{exc.__class__.__name__}"


def readiness_payload() -> tuple[dict[str, Any], bool]:
    db_ok, db_detail = check_database()
    redis_ok, redis_detail = check_redis()
    ready = db_ok and redis_ok
    return {
        "status": "ready" if ready else "not_ready",
        "checks": {
            "database": db_detail,
            "redis": redis_detail,
        },
    }, ready


@router.get("/health/live")
def health_live() -> dict[str, str]:
    """Process is up (no dependency checks)."""
    return {"status": "ok"}


@router.get("/health/ready")
def health_ready(response: Response) -> dict[str, Any]:
    """Database + Redis only — not third-party providers."""
    payload, ready = readiness_payload()
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return payload


@router.get("/health")
def health() -> dict[str, str]:
    """Backward-compatible alias for liveness."""
    return health_live()


@router.get("/api/v1/health")
def api_health() -> dict[str, str]:
    """SPA probe alias for liveness."""
    return health_live()
