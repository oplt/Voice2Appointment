"""Calendar HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_db
from app.calendars import service as calendars_service
from app.core.errors import NotFoundError, map_exception, raise_http
from app.db.models import User

router = APIRouter(prefix="/calendars", tags=["calendars"])


class CalendarPreferencesUpdate(BaseModel):
    calendar_id: str | None = Field(default=None, max_length=255)
    time_zone: str | None = Field(default=None, max_length=100)


@router.get("/status")
def get_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> dict:
    return calendars_service.calendar_status(db, current_user.id)


@router.patch("/preferences")
def patch_preferences(
    payload: CalendarPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> dict:
    try:
        return calendars_service.update_calendar_preferences(
            db,
            current_user.id,
            calendar_id=payload.calendar_id,
            time_zone=payload.time_zone,
        )
    except Exception as exc:
        raise_http(map_exception(exc))


@router.get("/google/connect")
def google_connect(
    current_user: User = Depends(get_current_user),
) -> dict:
    try:
        return calendars_service.start_google_oauth(current_user.id)
    except Exception as exc:
        raise_http(map_exception(exc))


@router.get("/google/callback")
def google_callback(
    request: Request,
    db: Session = Depends(require_db),
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    # Public callback — state JWT binds the user; no cookie required.
    if not state:
        raise_http(map_exception(ValueError("missing OAuth state")))
    url = calendars_service.finish_google_oauth(
        db, state=state, code=code, error=error
    )
    return RedirectResponse(url=url, status_code=302)


@router.get("/events")
def get_events(
    timeMin: str = Query(...),
    timeMax: str = Query(...),
    timezone: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> list:
    try:
        return calendars_service.list_events(
            db, current_user.id, timeMin, timeMax, timezone
        )
    except Exception as exc:
        raise_http(map_exception(exc))


@router.get("/availability")
def get_availability(
    datetime_start: str = Query(...),
    datetime_end: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> dict:
    try:
        return calendars_service.check_availability(
            db, current_user.id, datetime_start, datetime_end
        )
    except Exception as exc:
        raise_http(map_exception(exc))


@router.get("/embed/{view_type}")
def get_embed(
    view_type: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> dict:
    try:
        return calendars_service.embed_link(db, current_user.id, view_type)
    except Exception as exc:
        raise_http(map_exception(exc))


@router.delete("/google")
def disconnect_google(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> dict:
    ok = calendars_service.disconnect_google(db, current_user.id)
    if not ok:
        raise_http(NotFoundError("Google Calendar not connected"))
    return {"ok": True, "message": "Google Calendar disconnected"}
