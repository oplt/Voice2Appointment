"""Unified atomic booking for HTTP and voice channels (P0-07 / P0-08)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

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
from app.appointments.provider_operations import complete_create
from app.db.models import Appointment, User

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
    idempotency_key: str | None = None,
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

    key = idempotency_key or build_appointment_idempotency_key(
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
                provider_operation="create" if provider_create is not None else None,
                provider_calendar_id=calendar_id,
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
            # The pending intent must survive a crash/timeout during provider I/O.
            row.provider_operation = "create"
            row.provider_calendar_id = calendar_id
            db.commit()
            db.refresh(row)
            row = complete_create(db, row, provider_create)
        else:
            # Local-only bookings finalize immediately: stage the durable
            # notification outbox row in the same transaction (P6-V01 #1).
            from app.notifications.service import stage_confirmation_intent

            stage_confirmation_intent(db, row)
            db.commit()
            db.refresh(row)
        if row.provider_sync_status != "confirmed":
            return row
        from app.notifications.service import enqueue_confirmation

        enqueue_confirmation(db, row)
        try:
            from app.core.metrics import metrics

            metrics.incr("bookings", labels={"result": "created"})
        except Exception:  # noqa: BLE001
            pass
        return row


# Preserve the established booking module API while implementations live in their
# own cohesive service module.
from app.appointments.provider_operations import (  # noqa: E402
    cancel_appointment,
    reschedule_appointment_slot,
)
from app.appointments.reconciliation import reconcile_pending_appointment  # noqa: E402

__all__ = [
    "book_appointment",
    "cancel_appointment",
    "reconcile_pending_appointment",
    "reschedule_appointment_slot",
]
