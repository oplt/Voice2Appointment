"""Analytics HTTP routes."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.analytics import service as analytics_service
from app.analytics.schemas import AnalyticsMetaResponse, AnalyticsSummaryResponse
from app.analytics.service import AnalyticsRangeError
from app.auth.deps import get_current_user, require_db
from app.core.config import settings
from app.core.errors import ProviderUnavailableError, ValidationAppError, raise_http
from app.core.rate_limit import rate_limit
from app.db.models import User

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/meta", response_model=AnalyticsMetaResponse)
def get_meta(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> dict:
    """Tenant timezone and range limits for analytics filter defaults."""
    return analytics_service.analytics_meta(db, current_user.id)


@router.get("/summary", response_model=AnalyticsSummaryResponse)
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
        Depends(rate_limit(limit=5, window_seconds=60, name="fetch-twilio"))
    ],
)
def fetch_twilio(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> dict:
    account_sid = current_user.twilio_account_sid or settings.twilio_account_sid
    auth_token = current_user.twilio_auth_token or settings.twilio_auth_token
    if not account_sid or not auth_token:
        raise_http(ValidationAppError("Twilio credentials not configured"))
    try:
        return analytics_service.fetch_and_store_twilio(
            db,
            user_id=current_user.id,
            account_sid=account_sid,
            auth_token=auth_token,
        )
    except Exception as exc:
        raise_http(ProviderUnavailableError(cause=exc))
