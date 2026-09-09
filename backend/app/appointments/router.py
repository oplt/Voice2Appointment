"""Appointment HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.appointments import booking as booking_service
from app.appointments import service as appointments_service
from app.appointments.patch import patch_appointment
from app.appointments.schemas import (
    AppointmentCreate,
    AppointmentListItemOut,
    AppointmentListOut,
    AppointmentOut,
    AppointmentUpdate,
)
from app.auth.deps import get_current_user, require_db
from app.calendars import service as calendars_service
from app.core.errors import NotFoundError, map_exception, raise_http
from app.core.feature_flags import require_reservation_domain
from app.db.models import User
from app.tenancy.api import require_domain_permission

router = APIRouter(
    prefix="/appointments",
    tags=["appointments"],
    dependencies=[
        Depends(require_reservation_domain),
        Depends(require_domain_permission("reservation")),
    ],
)


def _provider_hooks(db: Session, user_id: int):
    return calendars_service.booking_provider_hooks(db, user_id)


@router.get("", response_model=AppointmentListOut)
def list_appointments(
    limit: int = Query(100, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> AppointmentListOut:
    """Bounded minimized list; sensitive fields require the detail endpoint."""
    rows = appointments_service.list_appointments(
        db, current_user.id, status=status_filter, limit=limit
    )
    return AppointmentListOut(
        items=[AppointmentListItemOut.model_validate(row) for row in rows],
        next_cursor=None,
        scope="all",
        limit=limit,
    )


@router.get("/page", response_model=AppointmentListOut)
def list_appointments_page(
    scope: str = Query("upcoming", pattern="^(upcoming|history|all)$"),
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> AppointmentListOut:
    try:
        rows, next_cursor = appointments_service.list_appointments_page(
            db,
            current_user.id,
            scope=scope,  # type: ignore[arg-type]
            limit=limit,
            cursor=cursor,
            status=status_filter,
        )
    except ValueError as exc:
        raise_http(map_exception(exc))
    return AppointmentListOut(
        items=[AppointmentListItemOut.model_validate(r) for r in rows],
        next_cursor=next_cursor,
        scope=scope,
        limit=limit,
    )


@router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def create_appointment(
    payload: AppointmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> AppointmentOut:
    hooks = _provider_hooks(db, current_user.id)
    try:
        row = booking_service.book_appointment(
            db,
            current_user.id,
            summary=payload.summary,
            start_datetime=payload.start_datetime,
            end_datetime=payload.end_datetime,
            timezone_name=payload.timezone,
            description=payload.description,
            client_name=payload.client_name,
            client_phone=payload.client_phone,
            client_email=payload.client_email,
            notes=payload.notes,
            # Disconnected calendars stay local-only; do not leak DTO pending default.
            status=payload.status.value if hooks.create_event is not None else None,
            calendar_id=hooks.calendar_id,
            provider_create=hooks.create_event,
            check_provider_availability=hooks.check_availability,
        )
    except Exception as exc:
        raise_http(map_exception(exc))
    return AppointmentOut.model_validate(row)


@router.get("/{appointment_id}", response_model=AppointmentOut)
def get_appointment(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> AppointmentOut:
    row = appointments_service.get_appointment(db, current_user.id, appointment_id)
    if row is None:
        raise_http(NotFoundError("Appointment not found"))
    payload = AppointmentOut.model_validate(row)
    if row.transcript_purged_at is not None:
        payload.transcript = None
    return payload


@router.patch("/{appointment_id}", response_model=AppointmentOut)
def update_appointment(
    appointment_id: int,
    payload: AppointmentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> AppointmentOut:
    return patch_appointment(db, current_user.id, appointment_id, payload)


@router.delete(
    "/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
def delete_appointment(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> None:
    """Cancel via shared booking service; syncs Google when connected."""
    hooks = _provider_hooks(db, current_user.id)
    try:
        booking_service.cancel_appointment(
            db,
            current_user.id,
            appointment_id=appointment_id,
            provider_delete=hooks.delete_event,
        )
    except Exception as exc:
        mapped = map_exception(exc)
        if mapped.code == "validation_error" and "not found" in mapped.message.lower():
            raise_http(NotFoundError("Appointment not found"))
        raise_http(mapped)
