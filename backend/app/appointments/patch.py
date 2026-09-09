"""Appointment PATCH orchestration (kept out of the HTTP router for size limits)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.appointments import booking as booking_service
from app.appointments import service as appointments_service
from app.appointments.policy import resolve_slot_end, validate_slot
from app.appointments.schemas import AppointmentOut, AppointmentUpdate, assert_status_transition
from app.calendars import service as calendars_service
from app.core.errors import NotFoundError, map_exception, raise_http
from app.db.models import Appointment


def patch_appointment(
    db: Session,
    user_id: int,
    appointment_id: int,
    payload: AppointmentUpdate,
) -> AppointmentOut:
    existing = appointments_service.get_appointment(db, user_id, appointment_id)
    if existing is None:
        raise_http(NotFoundError("Appointment not found"))

    fields = payload.model_dump(exclude_unset=True)
    try:
        return AppointmentOut.model_validate(
            _apply_patch(db, user_id, appointment_id, existing, fields)
        )
    except Exception as exc:
        raise_http(map_exception(exc))


def _apply_patch(
    db: Session,
    user_id: int,
    appointment_id: int,
    existing: Appointment,
    fields: dict,
) -> Appointment:
    summary = fields.get("summary", existing.summary)
    start_datetime = fields.get("start_datetime", existing.start_datetime)
    requested_end = fields.get("end_datetime", existing.end_datetime)
    timezone_name = fields.get("timezone", existing.timezone)
    policy = validate_slot(
        db,
        user_id,
        start=start_datetime,
        end=requested_end,
        timezone_name=timezone_name,
        exclude_appointment_id=existing.id,
    )
    end_datetime = resolve_slot_end(
        policy,
        summary=summary,
        start=start_datetime,
        end=requested_end,
    )
    validate_slot(
        db,
        user_id,
        start=start_datetime,
        end=end_datetime,
        timezone_name=timezone_name,
        exclude_appointment_id=existing.id,
    )
    if "status" in fields:
        assert_status_transition(existing.status, fields["status"].value)

    time_change = (
        start_datetime != existing.start_datetime
        or end_datetime != existing.end_datetime
        or timezone_name != existing.timezone
    )
    if time_change:
        hooks = calendars_service.booking_provider_hooks(db, user_id)
        row = booking_service.reschedule_appointment_slot(
            db,
            user_id,
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
                db, user_id, appointment_id, **other
            )
            if updated is None:
                raise_http(NotFoundError("Appointment not found"))
            return updated
        return row

    if "timezone" in fields and fields["timezone"] is None:
        raise ValueError("timezone cannot be cleared")
    updated = appointments_service.update_appointment(
        db,
        user_id,
        appointment_id,
        **fields,
    )
    if updated is None:
        raise_http(NotFoundError("Appointment not found"))
    return updated
