"""Dashboard HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_db
from app.dashboard.schemas import DashboardSummaryResponse
from app.dashboard.service import dashboard_summary
from app.db.models import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> dict:
    return dashboard_summary(db, current_user.id)
