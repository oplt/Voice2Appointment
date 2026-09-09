"""Analytics HTTP routes."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.analytics import service as analytics_service
from app.analytics.schemas import (
    AnalyticsMetaResponse,
    AnalyticsSummaryResponse,
    TwilioSyncStatusResponse,
)
from app.analytics.service import AnalyticsRangeError
from app.auth.deps import get_current_user, require_db
from app.core.config import settings
from app.core.errors import ValidationAppError, raise_http
from app.core.rate_limit import rate_limit
from app.core.thread_db import to_thread_db
from app.db.models import User
from app.tenancy.api import require_org_permission

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _sync_chain_key(user_id: int) -> str:
    return f"twilio-sync-chain:{user_id}"


def _claim_sync_chain(user_id: int) -> bool:
    from app.core.cache_backend import redis_client

    client = redis_client()
    if client is None:
        return True
    try:
        return bool(
            client.set(
                _sync_chain_key(user_id),
                "1",
                nx=True,
                ex=max(60, settings.twilio_sync_lease_seconds * 3),
            )
        )
    except Exception:  # noqa: BLE001
        return True


def _is_sync_queued(user_id: int) -> bool:
    from app.core.cache_backend import redis_client

    client = redis_client()
    if client is None:
        return False
    try:
        return bool(client.get(_sync_chain_key(user_id)))
    except Exception:  # noqa: BLE001
        return False


def _twilio_sync_status_for_user(user: User) -> dict[str, str | None]:
    now = datetime.now(timezone.utc)
    lease_active = bool(
        user.twilio_sync_lease_token
        and user.twilio_sync_lease_expires_at
        and user.twilio_sync_lease_expires_at > now
    )
    queued = _is_sync_queued(user.id)

    status = "healthy"
    error_code = None
    updated_at = None
    try:
        cfg = json.loads(user.config_json or "{}")
        health = cfg.get("integration_health") if isinstance(cfg, dict) else None
        twilio = health.get("twilio_sync") if isinstance(health, dict) else None
        if isinstance(twilio, dict):
            raw = str(twilio.get("status") or "")
            if raw in {"permanent_failure", "error", "failed"}:
                status = "error"
            elif raw in {"queued", "syncing"}:
                status = raw
            elif raw == "healthy":
                status = "healthy"
            error_code = str(twilio.get("error_code")) if twilio.get("error_code") else None
            updated_at = str(twilio.get("updated_at")) if twilio.get("updated_at") else None
    except Exception:  # noqa: BLE001
        pass

    if lease_active:
        status = "syncing"
    elif queued:
        status = "queued"

    return {
        "status": status,
        "last_synced_at": (
            user.twilio_last_synced_at.isoformat() if user.twilio_last_synced_at else None
        ),
        "error_code": error_code,
        "updated_at": updated_at,
    }


def _enqueue_twilio_sync(user_id: int) -> None:
    from app.workers.tasks import sync_twilio_for_user

    sync_twilio_for_user.delay(user_id)


@router.get(
    "/meta",
    response_model=AnalyticsMetaResponse,
    dependencies=[Depends(require_org_permission("analytics.read"))],
)
def get_meta(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> dict:
    """Tenant timezone and permitted range metadata for filter defaults."""
    payload = analytics_service.analytics_meta(db, current_user.id)
    payload["twilio_sync"] = _twilio_sync_status_for_user(current_user)
    return payload


@router.get(
    "/twilio-sync-status",
    response_model=TwilioSyncStatusResponse,
    dependencies=[Depends(require_org_permission("analytics.read"))],
)
def twilio_sync_status(current_user: User = Depends(get_current_user)) -> dict[str, str | None]:
    return _twilio_sync_status_for_user(current_user)


@router.get(
    "/summary",
    response_model=AnalyticsSummaryResponse,
    dependencies=[Depends(require_org_permission("analytics.read"))],
)
def get_summary(
    start: date | None = Query(None),
    end: date | None = Query(None),
    compare: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> dict:
    try:
        return analytics_service.analytics_summary(
            db, current_user.id, start=start, end=end, compare=compare
        )
    except AnalyticsRangeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/fetch-twilio",
    dependencies=[
        Depends(rate_limit(limit=5, window_seconds=60, name="fetch-twilio")),
        Depends(require_org_permission("integration.manage")),
    ],
)
async def fetch_twilio(current_user: User = Depends(get_current_user)) -> JSONResponse:
    account_sid = current_user.twilio_account_sid or settings.twilio_account_sid
    auth_token = current_user.twilio_auth_token or settings.twilio_auth_token
    if not account_sid or not auth_token:
        raise_http(ValidationAppError("Twilio credentials not configured"))

    claimed = _claim_sync_chain(current_user.id)
    queued_now = False
    if claimed:
        await to_thread_db(_enqueue_twilio_sync, current_user.id)
        queued_now = True

    status_payload = _twilio_sync_status_for_user(current_user)
    if queued_now and status_payload["status"] == "healthy":
        status_payload["status"] = "queued"
    status_payload["queued_now"] = "true" if queued_now else "false"
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=status_payload)
