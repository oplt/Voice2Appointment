"""Unified atomic booking for HTTP and voice channels (P0-07 / P0-08)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.appointments import service as appointments_service
from app.appointments.idempotency import build_appointment_idempotency_key
from app.appointments.locking import tenant_booking_lock
from app.appointments.policy import (
    BookingConflictError,
    BookingPolicyError,
    load_booking_policy,
    resolve_slot_end,
    validate_slot,
)
from app.db.models import Appointment, User

logger = logging.getLogger(__name__)

ProviderCreate = Callable[..., dict[str, Any]]


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def book_appointment(
    db: Session,
    user_id: int,
    *,
    summary: str,
    start_datetime: datetime,
    end_datetime: datetime | None = None,
    timezone_name: str = "UTC",
    description: str | None = None,
    client_name: str | None = None,
    client_phone: str | None = None,
    client_email: str | None = None,
    notes: str | None = None,
    calendar_id: str = "primary",
    call_sid: str | None = None,
    transcript: str | None = None,
    provider_create: ProviderCreate | None = None,
    check_provider_availability: Callable[[datetime, datetime], None] | None = None,
    **extra: Any,
) -> Appointment:
    """Validate policy under a tenant lock, then create pending → provider → finalize."""
    start_datetime = _aware(start_datetime)
    user = db.get(User, user_id)
    if user is None:
        raise BookingPolicyError("user not found")
    policy = load_booking_policy(user.config_json)
    end_datetime = resolve_slot_end(
        policy,
        summary=summary,
        start=start_datetime,
        end=_aware(end_datetime) if end_datetime is not None else None,
    )

    key = build_appointment_idempotency_key(
        user_id=user_id,
        calendar_id=calendar_id,
        start_utc=start_datetime,
        end_utc=end_datetime,
        summary=summary,
        call_sid=call_sid,
    )

    with tenant_booking_lock(db, user_id):
        existing = appointments_service.get_by_idempotency_key(db, key)
        if existing is not None and existing.user_id == user_id:
            if (
                existing.provider_sync_status == "confirmed"
                or existing.google_calendar_event_id
                or provider_create is None
            ):
                if call_sid and not existing.callsession_id:
                    from app.analytics.funnel import link_call_session_on_book

                    link_call_session_on_book(
                        db,
                        user_id=user_id,
                        call_sid=call_sid,
                        appointment=existing,
                    )
                    db.commit()
                    db.refresh(existing)
                return existing
            row = existing
            if call_sid and not row.callsession_id:
                from app.analytics.funnel import link_call_session_on_book

                link_call_session_on_book(
                    db,
                    user_id=user_id,
                    call_sid=call_sid,
                    appointment=row,
                )
        else:
            try:
                validate_slot(
                    db,
                    user_id,
                    start=start_datetime,
                    end=end_datetime,
                    timezone_name=timezone_name,
                )
            except BookingConflictError:
                try:
                    from app.core.metrics import metrics

                    metrics.incr("bookings", labels={"result": "conflict"})
                except Exception:  # noqa: BLE001
                    pass
                raise
            if check_provider_availability is not None:
                check_provider_availability(start_datetime, end_datetime)

            allowed_extra = {
                k: v
                for k, v in extra.items()
                if hasattr(Appointment, k)
                and k
                not in {
                    "idempotency_key",
                    "user_id",
                    "provider_sync_status",
                    "google_calendar_event_id",
                    "google_calendar_link",
                    "status",
                    "start_datetime",
                    "end_datetime",
                    "summary",
                    "timezone",
                }
            }
            initial_status = extra.get("status") or (
                "pending" if provider_create is not None else "confirmed"
            )
            row = Appointment(
                user_id=user_id,
                summary=summary,
                description=description,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                timezone=timezone_name,
                client_name=client_name,
                client_phone=client_phone,
                client_email=client_email,
                notes=notes,
                status=initial_status,
                idempotency_key=key,
                provider_sync_status=(
                    "pending_provider" if provider_create is not None else "confirmed"
                ),
                transcript=transcript,
                **allowed_extra,
            )
            if call_sid:
                from app.analytics.funnel import link_call_session_on_book

                link_call_session_on_book(
                    db,
                    user_id=user_id,
                    call_sid=call_sid,
                    appointment=row,
                )
            db.add(row)
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                existing = appointments_service.get_by_idempotency_key(db, key)
                if existing is not None and existing.user_id == user_id:
                    return existing
                raise

        if provider_create is not None and not row.google_calendar_event_id:
            event = provider_create(
                summary=summary,
                datetime_start=start_datetime.isoformat(),
                datetime_end=end_datetime.isoformat(),
                description=description or f"Appointment: {summary}",
                timezone=timezone_name,
                calendar_id=calendar_id,
                idempotency_key=key,
            )
            row.google_calendar_event_id = event.get("id")
            row.google_calendar_link = event.get("htmlLink")
            row.provider_sync_status = "confirmed"
            row.status = "confirmed"

        db.commit()
        db.refresh(row)
        from app.core.cache import invalidate_user_calendar_caches
        from app.notifications.service import enqueue_confirmation

        invalidate_user_calendar_caches(user_id)
        enqueue_confirmation(db, row)
        try:
            from app.core.metrics import metrics

            metrics.incr("bookings", labels={"result": "created"})
        except Exception:  # noqa: BLE001
            pass
        return row


def reschedule_appointment_slot(
    db: Session,
    user_id: int,
    *,
    appointment_id: int | None = None,
    event_id: str | None = None,
    start_datetime: datetime,
    end_datetime: datetime,
    timezone_name: str = "UTC",
    provider_update: Callable[..., dict[str, Any]] | None = None,
    check_provider_availability: Callable[[datetime, datetime], None] | None = None,
) -> Appointment:
    """Reschedule under the same policy + lock as create."""
    start_datetime = _aware(start_datetime)
    end_datetime = _aware(end_datetime)

    with tenant_booking_lock(db, user_id):
        row: Appointment | None = None
        if appointment_id is not None:
            row = appointments_service.get_appointment(db, user_id, appointment_id)
        elif event_id:
            row = db.scalar(
                select(Appointment).where(
                    Appointment.user_id == user_id,
                    Appointment.google_calendar_event_id == event_id,
                )
            )
        if row is None:
            raise BookingPolicyError("appointment not found")

        validate_slot(
            db,
            user_id,
            start=start_datetime,
            end=end_datetime,
            timezone_name=timezone_name,
            exclude_appointment_id=row.id,
        )
        if check_provider_availability is not None:
            check_provider_availability(start_datetime, end_datetime)

        if provider_update is not None and row.google_calendar_event_id:
            provider_update(
                event_id=row.google_calendar_event_id,
                datetime_start=start_datetime.isoformat(),
                datetime_end=end_datetime.isoformat(),
                timezone=timezone_name,
            )

        row.start_datetime = start_datetime
        row.end_datetime = end_datetime
        row.timezone = timezone_name
        row.status = "confirmed"
        row.reminder_sent = False
        row.confirmation_sent_at = None
        db.commit()
        db.refresh(row)
        from app.core.cache import invalidate_user_calendar_caches
        from app.notifications.service import enqueue_confirmation

        invalidate_user_calendar_caches(user_id)
        enqueue_confirmation(db, row)
        return row


def cancel_appointment(
    db: Session,
    user_id: int,
    *,
    appointment_id: int | None = None,
    event_id: str | None = None,
    reason: str | None = None,
    provider_delete: Callable[..., bool] | None = None,
) -> Appointment:
    """Cancel under tenant lock; Google delete is optional sync side effect."""
    with tenant_booking_lock(db, user_id):
        row: Appointment | None = None
        if appointment_id is not None:
            row = appointments_service.get_appointment(db, user_id, appointment_id)
        elif event_id:
            row = db.scalar(
                select(Appointment).where(
                    Appointment.user_id == user_id,
                    Appointment.google_calendar_event_id == event_id,
                )
            )
        if row is None:
            raise BookingPolicyError("appointment not found")
        if row.status == "cancelled":
            return row

        if provider_delete is not None and row.google_calendar_event_id:
            provider_delete(event_id=row.google_calendar_event_id)

        row.status = "cancelled"
        if reason:
            note = (row.notes or "").strip()
            suffix = f"Cancelled: {reason.strip()}"
            row.notes = f"{note}\n{suffix}".strip() if note else suffix
        db.commit()
        db.refresh(row)
        from app.core.cache import invalidate_user_calendar_caches
        from app.notifications.service import cancel_pending_for_appointment

        invalidate_user_calendar_caches(user_id)
        cancel_pending_for_appointment(db, row.id)
        return row


def reconcile_pending_appointment(db: Session, row: Appointment) -> dict[str, Any]:
    """Mark long-stuck pending rows failed when no provider event id exists."""
    if row.provider_sync_status != "pending_provider":
        return {"id": row.id, "action": "skip"}
    if row.google_calendar_event_id:
        row.provider_sync_status = "confirmed"
        row.status = "confirmed"
        db.commit()
        return {"id": row.id, "action": "finalize"}
    row.provider_sync_status = "failed"
    row.status = "failed"
    db.commit()
    logger.warning(
        "Marked pending appointment failed id=%s user_id=%s", row.id, row.user_id
    )
    return {"id": row.id, "action": "failed"}
