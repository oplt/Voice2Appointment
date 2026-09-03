"""Calendar HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_db
from app.calendars import service as calendars_service
from app.db.models import User

router = APIRouter(prefix="/calendars", tags=["calendars"])


@router.get("/status")
def get_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> dict:
    return calendars_service.calendar_status(db, current_user.id)


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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/embed/{view_type}")
def get_embed(
    view_type: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> dict:
    try:
        return calendars_service.embed_link(db, current_user.id, view_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.delete("/google")
def disconnect_google(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> dict:
    ok = calendars_service.disconnect_google(db, current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Google Calendar not connected")
    return {"ok": True, "message": "Google Calendar disconnected"}
