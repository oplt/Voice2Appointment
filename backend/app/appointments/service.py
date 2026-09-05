"""Appointment CRUD (tenant-scoped by user_id)."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.dialect_compat import datetime_comparison_value
from app.db.models import Appointment

Scope = Literal["upcoming", "history", "all"]


@dataclass(frozen=True)
class _PageCursor:
    start: datetime
    appointment_id: int
    scope: Scope
    snapshot_at: datetime
    reference_now: datetime
    status: str | None


def _encode_cursor(cursor: _PageCursor) -> str:
    start = cursor.start
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    else:
        start = start.astimezone(timezone.utc)
    payload = {
        "v": 1,
        "s": start.isoformat(),
        "i": cursor.appointment_id,
        "scope": cursor.scope,
        "snapshot": cursor.snapshot_at.astimezone(timezone.utc).isoformat(),
        "now": cursor.reference_now.astimezone(timezone.utc).isoformat(),
        "status": cursor.status,
    }
    return base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode()


def _decode_cursor(raw: str) -> _PageCursor:
    try:
        data = json.loads(
            base64.b64decode(raw.encode(), altchars=b"-_", validate=True).decode()
        )
        if data.get("v") != 1 or data.get("scope") not in {
            "upcoming",
            "history",
            "all",
        }:
            raise ValueError
        start = datetime.fromisoformat(str(data["s"]).replace("Z", "+00:00"))
        snapshot = datetime.fromisoformat(str(data["snapshot"]).replace("Z", "+00:00"))
        reference_now = datetime.fromisoformat(str(data["now"]).replace("Z", "+00:00"))
        if any(value.tzinfo is None for value in (start, snapshot, reference_now)):
            raise ValueError
        status = data.get("status")
        if status is not None and not isinstance(status, str):
            raise ValueError
        return _PageCursor(
            start=start.astimezone(timezone.utc),
            appointment_id=int(data["i"]),
            scope=data["scope"],
            snapshot_at=snapshot.astimezone(timezone.utc),
            reference_now=reference_now.astimezone(timezone.utc),
            status=status,
        )
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
    snapshot_at = now
    decoded = _decode_cursor(cursor) if cursor else None
    if decoded is not None:
        if decoded.scope != scope or decoded.status != status:
            raise ValueError("cursor does not match filters")
        now = decoded.reference_now
        snapshot_at = decoded.snapshot_at
    stmt = select(Appointment).where(Appointment.user_id == user_id)
    stmt = stmt.where(Appointment.created_at <= snapshot_at)
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

    if decoded is not None:
        c_start = decoded.start
        c_id = decoded.appointment_id
        comparison_start = datetime_comparison_value(db, c_start)
        if descending:
            stmt = stmt.where(
                (Appointment.start_datetime < comparison_start)
                | (
                    (Appointment.start_datetime == comparison_start)
                    & (Appointment.id < c_id)
                )
            )
        else:
            stmt = stmt.where(
                (Appointment.start_datetime > comparison_start)
                | (
                    (Appointment.start_datetime == comparison_start)
                    & (Appointment.id > c_id)
                )
            )

    rows = list(db.scalars(stmt.limit(limit + 1)).all())
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_cursor(
            _PageCursor(
                start=last.start_datetime,
                appointment_id=last.id,
                scope=scope,
                snapshot_at=snapshot_at,
                reference_now=now,
                status=status,
            )
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
    """Compatibility entry point routed through the locked booking service."""
    from app.appointments.booking import book_appointment

    return book_appointment(
        db,
        user_id,
        summary=summary,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        timezone_name=timezone,
        description=description,
        client_name=client_name,
        client_phone=client_phone,
        client_email=client_email,
        notes=notes,
        status=status,
        calendar_id=calendar_id,
        call_sid=call_sid,
        idempotency_key=idempotency_key,
        **extra,
    )


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
    return row


def delete_appointment(db: Session, user_id: int, appointment_id: int) -> bool:
    """Hard-delete local row (prefer cancel_appointment for calendar-aware cancel)."""
    row = get_appointment(db, user_id, appointment_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
