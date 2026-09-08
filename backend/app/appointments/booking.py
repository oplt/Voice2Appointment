"""Unified atomic booking for HTTP and voice channels (P0-07 / P0-08)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.appointments import service as appointments_service
from app.appointments.idempotency import build_appointment_idempotency_key
from app.appointments.locking import SchedulingLockTarget, scheduling_lock
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
    scheduling_target: SchedulingLockTarget | None = None,
    **extra: Any,
) -> Appointment:
    """Persist a booking intent, then perform provider I/O outside the lock."""
    start_datetime = _aware(start_datetime)
    user = db.get(User, user_id)
    if user is None:
        raise BookingPolicyError("user not found")
    policy = load_booking_policy(user.config_json)
    requested_end = _aware(end_datetime) if end_datetime is not None else None
    from app.catalog.service import booking_duration_minutes

    catalog_duration = booking_duration_minutes(db, user, summary)
    if catalog_duration is None:
        end_datetime = resolve_slot_end(
            policy,
            summary=summary,
            start=start_datetime,
            end=requested_end,
        )
    else:
        end_datetime = start_datetime + timedelta(minutes=catalog_duration)
        if requested_end is not None and requested_end != end_datetime:
            raise BookingPolicyError(
                f"{summary.strip()} appointments must be {catalog_duration} minutes"
            )

    key = idempotency_key or build_appointment_idempotency_key(
        user_id=user_id,
        calendar_id=calendar_id,
        start_utc=start_datetime,
        end_utc=end_datetime,
        summary=summary,
        call_sid=call_sid,
    )

    # Do not keep the read transaction open while an external availability
    # check runs.  Existing requests skip that best-effort precheck and rely on
    # their durable idempotency key instead.
    existing_id = db.scalar(
        select(Appointment.id).where(
            Appointment.idempotency_key == key,
            Appointment.user_id == user_id,
        )
    )
    db.rollback()
    if existing_id is None and check_provider_availability is not None:
        check_provider_availability(start_datetime, end_datetime)

    should_call_provider = False
    pending_provider_id: int | None = None
    target = scheduling_target or SchedulingLockTarget(organization_id=user_id)
    with scheduling_lock(db, target):
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
            should_call_provider = provider_create is not None
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
                organization_id=user.organization_id,
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
                    row = existing
                    should_call_provider = provider_create is not None
                else:
                    raise
            should_call_provider = provider_create is not None

        if should_call_provider and not row.google_calendar_event_id:
            # The pending intent must survive a crash/timeout during provider
            # I/O.  Commit before leaving the advisory lock.
            pending_provider_id = row.id
            row.provider_operation = "create"
            row.provider_calendar_id = calendar_id
            db.commit()
        else:
            # Local-only bookings finalize immediately: stage the durable
            # notification outbox row in the same transaction (P6-V01 #1).
            from app.notifications.service import stage_confirmation_intent

            stage_confirmation_intent(db, row)
            db.commit()
            db.refresh(row)

    # Provider calls run only after the transaction-scoped scheduling lock and
    # its transaction have been released.  ``complete_create`` claims and
    # finalizes the durable intent in separate short transactions.
    if pending_provider_id is not None and provider_create is not None:
        row = complete_create(db, pending_provider_id, provider_create)
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
