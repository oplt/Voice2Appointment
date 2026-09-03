"""Appointment CRUD (tenant-scoped by user_id)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.appointments.idempotency import build_appointment_idempotency_key
from app.db.models import Appointment


def list_appointments(
    db: Session,
    user_id: int,
    *,
    status: str | None = None,
    limit: int = 100,
) -> list[Appointment]:
    stmt = select(Appointment).where(Appointment.user_id == user_id)
    if status:
        stmt = stmt.where(Appointment.status == status)
    stmt = stmt.order_by(Appointment.start_datetime.asc()).limit(limit)
    return list(db.scalars(stmt).all())


def get_appointment(db: Session, user_id: int, appointment_id: int) -> Appointment | None:
    return db.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.user_id == user_id,
        )
    )


def get_by_idempotency_key(db: Session, idempotency_key: str) -> Appointment | None:
    return db.scalar(
        select(Appointment).where(Appointment.idempotency_key == idempotency_key)
    )


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def create_appointment(
    db: Session,
    user_id: int,
    *,
    summary: str,
    start_datetime: datetime,
    end_datetime: datetime,
    timezone: str = "UTC",
    description: str | None = None,
    client_name: str | None = None,
    client_phone: str | None = None,
    client_email: str | None = None,
    notes: str | None = None,
    status: str = "pending",
    calendar_id: str = "primary",
    call_sid: str | None = None,
    idempotency_key: str | None = None,
    **extra: Any,
) -> Appointment:
    start_datetime = _ensure_aware(start_datetime)
    end_datetime = _ensure_aware(end_datetime)

    key = idempotency_key or build_appointment_idempotency_key(
        user_id=user_id,
        calendar_id=calendar_id,
        start_utc=start_datetime,
        end_utc=end_datetime,
        summary=summary,
        call_sid=call_sid,
    )
    existing = get_by_idempotency_key(db, key)
    if existing is not None and existing.user_id == user_id:
        return existing

    allowed_extra = {
        k: v
        for k, v in extra.items()
        if hasattr(Appointment, k) and k not in {"idempotency_key", "user_id"}
    }
    row = Appointment(
        user_id=user_id,
        summary=summary,
        description=description,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        timezone=timezone,
        client_name=client_name,
        client_phone=client_phone,
        client_email=client_email,
        notes=notes,
        status=status,
        idempotency_key=key,
        **allowed_extra,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = get_by_idempotency_key(db, key)
        if existing is not None and existing.user_id == user_id:
            return existing
        raise
    db.refresh(row)
    from app.core.cache import invalidate_user_calendar_caches

    invalidate_user_calendar_caches(user_id)
    return row


def update_appointment(
    db: Session,
    user_id: int,
    appointment_id: int,
    **fields: Any,
) -> Appointment | None:
    row = get_appointment(db, user_id, appointment_id)
    if row is None:
        return None
    for key, value in fields.items():
        if value is not None and hasattr(row, key) and key != "idempotency_key":
            if key in {"start_datetime", "end_datetime"} and isinstance(value, datetime):
                value = _ensure_aware(value)
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    from app.core.cache import invalidate_user_calendar_caches

    invalidate_user_calendar_caches(user_id)
    return row


def delete_appointment(db: Session, user_id: int, appointment_id: int) -> bool:
    row = get_appointment(db, user_id, appointment_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    from app.core.cache import invalidate_user_calendar_caches

    invalidate_user_calendar_caches(user_id)
    return True
