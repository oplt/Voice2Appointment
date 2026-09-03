"""Appointment CRUD (tenant-scoped by user_id)."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.appointments.idempotency import build_appointment_idempotency_key
from app.db.models import Appointment

Scope = Literal["upcoming", "history", "all"]


def _encode_cursor(start: datetime, appointment_id: int, *, descending: bool) -> str:
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    else:
        start = start.astimezone(timezone.utc)
    payload = {
        "s": start.isoformat(),
        "i": appointment_id,
        "d": descending,
    }
    return base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode()


def _decode_cursor(raw: str) -> tuple[datetime, int, bool]:
    try:
        data = json.loads(base64.urlsafe_b64decode(raw.encode()).decode())
        start = datetime.fromisoformat(str(data["s"]).replace("Z", "+00:00"))
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        return start, int(data["i"]), bool(data.get("d", False))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("invalid cursor") from exc


def list_appointments(
    db: Session,
    user_id: int,
    *,
    status: str | None = None,
    limit: int = 100,
) -> list[Appointment]:
    rows, _ = list_appointments_page(
        db, user_id, scope="all", limit=limit, status=status
    )
    return rows


def list_appointments_page(
    db: Session,
    user_id: int,
    *,
    scope: Scope = "upcoming",
    limit: int = 50,
    cursor: str | None = None,
    status: str | None = None,
) -> tuple[list[Appointment], str | None]:
    limit = max(1, min(int(limit), 100))
    now = datetime.now(timezone.utc)
    stmt = select(Appointment).where(Appointment.user_id == user_id)
    if status:
        stmt = stmt.where(Appointment.status == status)

    descending = scope == "history"
    if scope == "upcoming":
        stmt = stmt.where(Appointment.start_datetime >= now)
        stmt = stmt.order_by(Appointment.start_datetime.asc(), Appointment.id.asc())
    elif scope == "history":
        stmt = stmt.where(Appointment.start_datetime < now)
        stmt = stmt.order_by(Appointment.start_datetime.desc(), Appointment.id.desc())
    else:
        stmt = stmt.order_by(Appointment.start_datetime.asc(), Appointment.id.asc())

    if cursor:
        c_start, c_id, c_desc = _decode_cursor(cursor)
        if c_desc != descending and scope != "all":
            raise ValueError("cursor does not match scope")
        # Compare using UTC-naive literals so SQLite and PostgreSQL agree.
        c_start_naive = c_start.astimezone(timezone.utc).replace(tzinfo=None)
        if descending:
            stmt = stmt.where(
                (Appointment.start_datetime < c_start_naive)
                | (
                    (Appointment.start_datetime == c_start_naive)
                    & (Appointment.id < c_id)
                )
            )
        else:
            stmt = stmt.where(
                (Appointment.start_datetime > c_start_naive)
                | (
                    (Appointment.start_datetime == c_start_naive)
                    & (Appointment.id > c_id)
                )
            )

    rows = list(db.scalars(stmt.limit(limit + 1)).all())
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_cursor(
            last.start_datetime, last.id, descending=descending
        )
        rows = rows[:limit]
    return rows, next_cursor


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
    """Apply patch fields. Explicit ``None`` clears nullable columns (P3-04)."""
    row = get_appointment(db, user_id, appointment_id)
    if row is None:
        return None
    from app.appointments.schemas import assert_status_transition, validate_timezone_name

    if "timezone" in fields and fields["timezone"] is not None:
        fields["timezone"] = validate_timezone_name(str(fields["timezone"]))
    if "status" in fields and fields["status"] is not None:
        new_status = fields["status"]
        if hasattr(new_status, "value"):
            new_status = new_status.value
        assert_status_transition(row.status, str(new_status))
        fields["status"] = str(new_status)
    if "summary" in fields and fields["summary"] is not None:
        summary = str(fields["summary"]).strip()
        if not summary:
            raise ValueError("summary cannot be empty")
        fields["summary"] = summary

    clearable = {
        "description",
        "client_name",
        "client_phone",
        "client_email",
        "notes",
        "transcript",
    }
    for key, value in fields.items():
        if not hasattr(row, key) or key == "idempotency_key":
            continue
        if value is None and key not in clearable:
            continue
        if key in {"start_datetime", "end_datetime"} and isinstance(value, datetime):
            value = _ensure_aware(value)
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    from app.core.cache import invalidate_user_calendar_caches

    invalidate_user_calendar_caches(user_id)
    return row


def delete_appointment(db: Session, user_id: int, appointment_id: int) -> bool:
    """Hard-delete local row (prefer cancel_appointment for calendar-aware cancel)."""
    row = get_appointment(db, user_id, appointment_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    from app.core.cache import invalidate_user_calendar_caches

    invalidate_user_calendar_caches(user_id)
    return True
