"""Appointment HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.appointments import service as appointments_service
from app.appointments.policy import (
    BookingConflictError,
    BookingPolicyError,
    load_booking_policy,
    resolve_slot_end,
    validate_slot,
)
from app.appointments.schemas import AppointmentCreate, AppointmentOut, AppointmentUpdate
from app.auth.deps import get_current_user, require_db
from app.db.models import User

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("", response_model=list[AppointmentOut])
def list_appointments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> list[AppointmentOut]:
    rows = appointments_service.list_appointments(db, current_user.id)
    return [AppointmentOut.model_validate(r) for r in rows]


@router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def create_appointment(
    payload: AppointmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> AppointmentOut:
    policy = load_booking_policy(current_user.config_json)
    try:
        end_datetime = resolve_slot_end(
            policy,
            summary=payload.summary,
            start=payload.start_datetime,
            end=payload.end_datetime,
        )
        validate_slot(
            db,
            current_user.id,
            start=payload.start_datetime,
            end=end_datetime,
            timezone_name=payload.timezone,
        )
    except BookingConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BookingPolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    row = appointments_service.create_appointment(
        db,
        current_user.id,
        **payload.model_dump(exclude={"end_datetime"}),
        end_datetime=end_datetime,
    )
    return AppointmentOut.model_validate(row)


@router.get("/{appointment_id}", response_model=AppointmentOut)
def get_appointment(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> AppointmentOut:
    row = appointments_service.get_appointment(db, current_user.id, appointment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
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
        raise HTTPException(status_code=404, detail="Appointment not found")
    if payload.start_datetime is not None or payload.end_datetime is not None:
        start_datetime = payload.start_datetime or existing.start_datetime
        if payload.end_datetime is not None:
            end_datetime = payload.end_datetime
        elif payload.start_datetime is not None:
            end_datetime = start_datetime + (
                existing.end_datetime - existing.start_datetime
            )
        else:
            end_datetime = existing.end_datetime
        try:
            validate_slot(
                db,
                current_user.id,
                start=start_datetime,
                end=end_datetime,
                timezone_name=payload.timezone or existing.timezone,
                exclude_appointment_id=appointment_id,
            )
        except BookingConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except BookingPolicyError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        payload = payload.model_copy(
            update={"start_datetime": start_datetime, "end_datetime": end_datetime}
        )
    row = appointments_service.update_appointment(
        db,
        current_user.id,
        appointment_id,
        **payload.model_dump(exclude_unset=True),
    )
    assert row is not None
    return AppointmentOut.model_validate(row)


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_appointment(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> None:
    ok = appointments_service.delete_appointment(db, current_user.id, appointment_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Appointment not found")
