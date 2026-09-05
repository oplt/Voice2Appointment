"""Durable, retryable appointment mutations against calendar providers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.appointments import service as appointments_service
from app.appointments.locking import tenant_booking_lock
from app.appointments.policy import BookingPolicyError, validate_slot
from app.db.models import Appointment

ProviderCall = Callable[..., Any]
_LEASE_SECONDS = 60
_MAX_ATTEMPTS = 5


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_error_code(exc: BaseException) -> str:
    return type(exc).__name__[:64]


def _claim_attempt(db: Session, appointment_id: int) -> Appointment | None:
    now = _utcnow()
    claimed = db.execute(
        update(Appointment)
        .where(
            Appointment.id == appointment_id,
            Appointment.provider_sync_status == "pending_provider",
            Appointment.provider_attempt_count < _MAX_ATTEMPTS,
            or_(
                Appointment.provider_next_retry_at.is_(None),
                Appointment.provider_next_retry_at <= now,
            ),
        )
        .values(
            provider_attempt_count=Appointment.provider_attempt_count + 1,
            provider_last_error_code=None,
            provider_next_retry_at=now + timedelta(seconds=_LEASE_SECONDS),
        )
        .returning(Appointment.id)
        .execution_options(synchronize_session=False)
    ).scalar_one_or_none()
    db.commit()
    if claimed is None:
        return None
    return db.get(Appointment, claimed)


def _record_failure(db: Session, appointment_id: int, exc: BaseException) -> None:
    db.rollback()
    row = db.get(Appointment, appointment_id)
    if row is None:
        return
    attempts = max(1, int(row.provider_attempt_count or 1))
    row.provider_last_error_code = _safe_error_code(exc)
    if attempts >= _MAX_ATTEMPTS:
        row.provider_sync_status = "failed"
        if row.provider_operation == "create":
            row.status = "failed"
        row.provider_next_retry_at = None
    else:
        row.provider_next_retry_at = _utcnow() + timedelta(
            seconds=min(300, 2 ** attempts)
        )
    db.commit()


def _clear_operation(row: Appointment) -> None:
    row.provider_sync_status = "confirmed"
    row.provider_operation = None
    row.provider_operation_payload = None
    row.provider_last_error_code = None
    row.provider_next_retry_at = None


def complete_create(
    db: Session,
    row: Appointment,
    provider_create: ProviderCall,
) -> Appointment:
    claimed = _claim_attempt(db, row.id)
    if claimed is None:
        db.expire_all()
        return db.get(Appointment, row.id) or row
    try:
        event = provider_create(
            summary=claimed.summary,
            datetime_start=claimed.start_datetime.isoformat(),
            datetime_end=claimed.end_datetime.isoformat(),
            description=claimed.description or f"Appointment: {claimed.summary}",
            timezone=claimed.timezone,
            calendar_id=claimed.provider_calendar_id,
            idempotency_key=claimed.idempotency_key,
        )
        event_id = str((event or {}).get("id") or "").strip()
        if not event_id:
            raise RuntimeError("provider returned no event id")
        claimed.google_calendar_event_id = event_id
        claimed.google_calendar_link = (event or {}).get("htmlLink")
        claimed.status = "confirmed"
        _clear_operation(claimed)
        # Stage the durable notification outbox row in the same transaction
        # that finalizes the provider create (P6-V01 #1).
        from app.notifications.service import stage_confirmation_intent

        stage_confirmation_intent(db, claimed)
        db.commit()
        db.refresh(claimed)
        return claimed
    except Exception as exc:
        _record_failure(db, row.id, exc)
        raise


def _perform_reschedule(
    db: Session,
    row: Appointment,
    provider_update: ProviderCall,
) -> Appointment:
    claimed = _claim_attempt(db, row.id)
    if claimed is None:
        db.expire_all()
        return db.get(Appointment, row.id) or row
    payload = dict(claimed.provider_operation_payload or {})
    try:
        provider_update(
            event_id=claimed.google_calendar_event_id,
            datetime_start=payload["start_datetime"],
            datetime_end=payload["end_datetime"],
            timezone=payload["timezone"],
        )
        claimed.start_datetime = datetime.fromisoformat(payload["start_datetime"])
        claimed.end_datetime = datetime.fromisoformat(payload["end_datetime"])
        claimed.timezone = payload["timezone"]
        claimed.status = "confirmed"
        claimed.reminder_sent = False
        claimed.confirmation_sent_at = None
        _clear_operation(claimed)
        # Drop the stale (old-slot) outbox rows and stage a fresh confirmation
        # for the new slot in the same transaction (P6-V01 #1/#3).
        from app.notifications.service import stage_reschedule_notifications

        stage_reschedule_notifications(db, claimed)
        db.commit()
        db.refresh(claimed)
        return claimed
    except Exception as exc:
        _record_failure(db, row.id, exc)
        raise


def _perform_cancel(
    db: Session,
    row: Appointment,
    provider_delete: ProviderCall,
) -> Appointment:
    claimed = _claim_attempt(db, row.id)
    if claimed is None:
        db.expire_all()
        return db.get(Appointment, row.id) or row
    payload = dict(claimed.provider_operation_payload or {})
    try:
        provider_delete(event_id=claimed.google_calendar_event_id)
        claimed.status = "cancelled"
        reason = str(payload.get("reason") or "").strip()
        if reason:
            note = (claimed.notes or "").strip()
            suffix = f"Cancelled: {reason}"
            claimed.notes = f"{note}\n{suffix}".strip() if note else suffix
        _clear_operation(claimed)
        # Cancel not-yet-sent outbox rows in the same transaction (P6-V01 #1).
        from app.notifications.service import stage_cancellation

        stage_cancellation(db, claimed.id)
        db.commit()
        db.refresh(claimed)
        return claimed
    except Exception as exc:
        _record_failure(db, row.id, exc)
        raise


def reschedule_appointment_slot(
    db: Session,
    user_id: int,
    *,
    appointment_id: int | None = None,
    event_id: str | None = None,
    start_datetime: datetime,
    end_datetime: datetime,
    timezone_name: str = "UTC",
    provider_update: ProviderCall | None = None,
    check_provider_availability: Callable[[datetime, datetime], None] | None = None,
) -> Appointment:
    if start_datetime.tzinfo is None:
        start_datetime = start_datetime.replace(tzinfo=timezone.utc)
    if end_datetime.tzinfo is None:
        end_datetime = end_datetime.replace(tzinfo=timezone.utc)
    with tenant_booking_lock(db, user_id):
        row = _find_appointment(db, user_id, appointment_id, event_id)
        if row.provider_operation:
            raise BookingPolicyError("provider operation already in progress")
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
        if provider_update is None or not row.google_calendar_event_id:
            row.start_datetime = start_datetime
            row.end_datetime = end_datetime
            row.timezone = timezone_name
            row.status = "confirmed"
            row.reminder_sent = False
            row.confirmation_sent_at = None
            # Local-only reschedules finalize immediately: stage the new-slot
            # confirmation and drop stale deliveries in the same transaction.
            from app.notifications.service import stage_reschedule_notifications

            stage_reschedule_notifications(db, row)
            db.commit()
            db.refresh(row)
        else:
            row.provider_sync_status = "pending_provider"
            row.provider_operation = "reschedule"
            row.provider_operation_payload = {
                "start_datetime": start_datetime.isoformat(),
                "end_datetime": end_datetime.isoformat(),
                "timezone": timezone_name,
            }
            row.provider_next_retry_at = None
            db.commit()
            db.refresh(row)
    if provider_update is not None and row.provider_operation == "reschedule":
        row = _perform_reschedule(db, row, provider_update)
    if row.provider_sync_status == "confirmed":
        _after_change(db, row, confirmation=True)
    return row


def cancel_appointment(
    db: Session,
    user_id: int,
    *,
    appointment_id: int | None = None,
    event_id: str | None = None,
    reason: str | None = None,
    provider_delete: ProviderCall | None = None,
) -> Appointment:
    with tenant_booking_lock(db, user_id):
        row = _find_appointment(db, user_id, appointment_id, event_id)
        if row.status == "cancelled":
            return row
        if row.provider_operation:
            if row.provider_operation == "cancel":
                return row
            raise BookingPolicyError("provider operation already in progress")
        if provider_delete is None or not row.google_calendar_event_id:
            row.status = "cancelled"
            if reason:
                row.notes = _cancel_note(row.notes, reason)
            # Local-only cancels finalize immediately: stage the outbox
            # cancellation in the same transaction (P6-V01 #1).
            from app.notifications.service import stage_cancellation

            stage_cancellation(db, row.id)
            db.commit()
            db.refresh(row)
        else:
            row.provider_sync_status = "pending_provider"
            row.provider_operation = "cancel"
            row.provider_operation_payload = {"reason": reason or ""}
            row.provider_next_retry_at = None
            db.commit()
            db.refresh(row)
    if provider_delete is not None and row.provider_operation == "cancel":
        row = _perform_cancel(db, row, provider_delete)
    return row


def _find_appointment(
    db: Session,
    user_id: int,
    appointment_id: int | None,
    event_id: str | None,
) -> Appointment:
    row = None
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
    return row


def _cancel_note(current: str | None, reason: str) -> str:
    note = (current or "").strip()
    suffix = f"Cancelled: {reason.strip()}"
    return f"{note}\n{suffix}".strip() if note else suffix


def _after_change(db: Session, row: Appointment, *, confirmation: bool) -> None:
    """Trigger delivery of an already-staged outbox row (cancellation is staged
    transactionally alongside the appointment mutation, so only confirmations
    need a post-commit worker trigger here)."""
    if confirmation:
        from app.notifications.service import enqueue_confirmation

        enqueue_confirmation(db, row)
