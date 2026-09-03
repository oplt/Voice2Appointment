"""Appointment HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.appointments import booking as booking_service
from app.appointments import service as appointments_service
from app.appointments.schemas import (
    AppointmentCreate,
    AppointmentListOut,
    AppointmentOut,
    AppointmentUpdate,
)
from app.auth.deps import get_current_user, require_db
from app.calendars import service as calendars_service
from app.core.errors import NotFoundError, map_exception, raise_http
from app.db.models import User

router = APIRouter(prefix="/appointments", tags=["appointments"])


def _provider_hooks(db: Session, user_id: int):
    return calendars_service.booking_provider_hooks(db, user_id)


@router.get("", response_model=AppointmentListOut)
def list_appointments(
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
        items=[AppointmentOut.model_validate(r) for r in rows],
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
            status=payload.status.value,
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
    return AppointmentOut.model_validate(row)


@router.patch("/{appointment_id}", response_model=AppointmentOut)
def update_appointment(
    appointment_id: int,
    payload: AppointmentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> AppointmentOut:
    existing = appointments_service.get_appointment(
        db, current_user.id, appointment_id
    )
    if existing is None:
        raise_http(NotFoundError("Appointment not found"))

    fields = payload.model_dump(exclude_unset=True)
    time_change = "start_datetime" in fields or "end_datetime" in fields
    try:
        if time_change:
            start_datetime = fields.get("start_datetime") or existing.start_datetime
            if "end_datetime" in fields and fields["end_datetime"] is not None:
                end_datetime = fields["end_datetime"]
            elif "start_datetime" in fields and fields["start_datetime"] is not None:
                end_datetime = start_datetime + (
                    existing.end_datetime - existing.start_datetime
                )
            else:
                end_datetime = existing.end_datetime
            timezone_name = fields.get("timezone") or existing.timezone
            hooks = _provider_hooks(db, current_user.id)
            row = booking_service.reschedule_appointment_slot(
                db,
                current_user.id,
                appointment_id=appointment_id,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                timezone_name=timezone_name,
                provider_update=hooks.update_event,
                check_provider_availability=hooks.check_availability,
            )
            other = {
                k: v
                for k, v in fields.items()
                if k not in {"start_datetime", "end_datetime", "timezone"}
            }
            if other:
                updated = appointments_service.update_appointment(
                    db, current_user.id, appointment_id, **other
                )
                if updated is None:
                    raise_http(NotFoundError("Appointment not found"))
                row = updated
            return AppointmentOut.model_validate(row)

        if "timezone" in fields and fields["timezone"] is None:
            raise ValueError("timezone cannot be cleared")
        updated = appointments_service.update_appointment(
            db,
            current_user.id,
            appointment_id,
            **fields,
        )
        if updated is None:
            raise_http(NotFoundError("Appointment not found"))
        return AppointmentOut.model_validate(updated)
    except Exception as exc:
        raise_http(map_exception(exc))


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
