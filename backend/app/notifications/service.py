"""Consent-aware appointment email confirmations and reminders (P6-01)."""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime, time, timedelta, timezone
from email.message import EmailMessage
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.calendars.service import get_auth_record
from app.core.config import settings
from app.db.models import Appointment, NotificationDelivery, User
from app.users.product_prefs import NotificationPrefs, load_product_prefs

logger = logging.getLogger(__name__)

KIND_CONFIRMATION = "confirmation"
KIND_REMINDER = "reminder"
# Legacy alias kept for callers/tests that still seed rows with "pending"; new
# rows are created "scheduled" (P6-V01 outbox states).
STATUS_PENDING = "pending"
STATUS_SCHEDULED = "scheduled"
STATUS_CLAIMED = "claimed"
STATUS_SENT = "sent"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_CANCELLED = "cancelled"

_CLAIMABLE_STATUSES = (STATUS_PENDING, STATUS_SCHEDULED, STATUS_FAILED)
_LEASE_SECONDS = 60
_MAX_ATTEMPTS = 5


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _tenant_zone(db: Session, user_id: int) -> ZoneInfo:
    auth = get_auth_record(db, user_id)
    name = (
        (auth.time_zone if auth and auth.time_zone else None)
        or settings.default_timezone
        or "UTC"
    )
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _appointment_zone(appointment: Appointment, db: Session) -> ZoneInfo:
    """Format times in the appointment's own IANA zone, falling back to tenant zone."""
    name = (appointment.timezone or "").strip() or None
    if not name:
        return _tenant_zone(db, appointment.user_id)
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return _tenant_zone(db, appointment.user_id)


def _in_quiet_hours(now_local: datetime, prefs: NotificationPrefs) -> bool:
    if not prefs.quiet_hours_start or not prefs.quiet_hours_end:
        return False
    start = time.fromisoformat(prefs.quiet_hours_start)
    end = time.fromisoformat(prefs.quiet_hours_end)
    current = now_local.timetz().replace(tzinfo=None)
    if start <= end:
        return start <= current < end
    # Overnight window (e.g. 21:00–08:00)
    return current >= start or current < end


def _next_quiet_hours_end(now_local: datetime, prefs: NotificationPrefs) -> datetime:
    """Next tenant-local instant when quiet hours end (for reschedule)."""
    assert prefs.quiet_hours_end
    end = time.fromisoformat(prefs.quiet_hours_end)
    candidate = now_local.replace(
        hour=end.hour, minute=end.minute, second=0, microsecond=0
    )
    if candidate <= now_local:
        candidate = candidate + timedelta(days=1)
    return candidate


def _recipient(appointment: Appointment, user: User) -> str | None:
    email = (appointment.client_email or "").strip() or (user.email or "").strip()
    return email or None


def _idem_key(kind: str, appointment_id: int, slot_start: datetime) -> str:
    # Treat naive instants as already UTC (SQLite round-trips drop tzinfo);
    # astimezone() on a naive value would otherwise assume the local zone and
    # silently mint a second idempotency key for the same slot.
    if slot_start.tzinfo is None:
        slot_start = slot_start.replace(tzinfo=timezone.utc)
    else:
        slot_start = slot_start.astimezone(timezone.utc)
    return f"{kind}:{appointment_id}:{slot_start.isoformat()}"


def _ensure_delivery(
    db: Session,
    *,
    user_id: int,
    appointment_id: int,
    kind: str,
    idempotency_key: str,
) -> NotificationDelivery:
    """Add (or return) the durable outbox row. Flushes but never commits.

    Callers that must land the intent in the same transaction as an
    appointment mutation call this before their own commit; callers that only
    need a best-effort row commit afterward themselves.
    """
    existing = db.scalar(
        select(NotificationDelivery).where(
            NotificationDelivery.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        return existing
    row = NotificationDelivery(
        user_id=user_id,
        appointment_id=appointment_id,
        kind=kind,
        channel="email",
        status=STATUS_SCHEDULED,
        idempotency_key=idempotency_key,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.expire_all()
        existing = db.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.idempotency_key == idempotency_key
            )
        )
        if existing is None:
            raise
        return existing
    return row


def stage_confirmation_intent(
    db: Session, appointment: Appointment
) -> NotificationDelivery:
    """Stage the durable confirmation outbox row for the caller's open transaction.

    Must be called before the appointment mutation's own commit so the intent
    and the appointment state change persist atomically (P6-V01 #1).
    """
    key = _idem_key(KIND_CONFIRMATION, appointment.id, appointment.start_datetime)
    return _ensure_delivery(
        db,
        user_id=appointment.user_id,
        appointment_id=appointment.id,
        kind=KIND_CONFIRMATION,
        idempotency_key=key,
    )


def _cancel_pending_rows(db: Session, appointment_id: int) -> int:
    """Cancel not-yet-terminal deliveries in the caller's open transaction (no commit)."""
    rows = list(
        db.scalars(
            select(NotificationDelivery).where(
                NotificationDelivery.appointment_id == appointment_id,
                NotificationDelivery.status.in_(
                    (STATUS_PENDING, STATUS_SCHEDULED, STATUS_FAILED, STATUS_CLAIMED)
                ),
            )
        ).all()
    )
    for row in rows:
        row.status = STATUS_CANCELLED
        row.error_code = "appointment_cancelled"
    return len(rows)


def stage_cancellation(db: Session, appointment_id: int) -> int:
    """Stage cancellation of pending deliveries for the caller's open transaction."""
    return _cancel_pending_rows(db, appointment_id)


def stage_reschedule_notifications(
    db: Session, appointment: Appointment
) -> NotificationDelivery:
    """Drop stale (old-slot) deliveries and stage a fresh confirmation for the new slot.

    Covers reminders scheduled against the previous start time as well as any
    unset confirmation for the old slot (P6-V01 #3).
    """
    _cancel_pending_rows(db, appointment.id)
    return stage_confirmation_intent(db, appointment)


def cancel_pending_for_appointment(db: Session, appointment_id: int) -> int:
    """Self-committing wrapper for standalone callers outside a booking transaction."""
    count = _cancel_pending_rows(db, appointment_id)
    if count:
        db.commit()
    return count


def _appointment_email_body(
    appointment: Appointment, *, kind: str, zone: ZoneInfo
) -> tuple[str, str]:
    local_start = appointment.start_datetime
    if local_start.tzinfo is None:
        local_start = local_start.replace(tzinfo=timezone.utc)
    when = local_start.astimezone(zone).strftime("%Y-%m-%d %H:%M %Z")
    if kind == KIND_CONFIRMATION:
        subject = "Appointment confirmation"
        body = (
            f"Your appointment “{appointment.summary}” is confirmed for {when}.\n"
            "If you need to change it, reply to the business or call again.\n"
        )
    else:
        subject = "Appointment reminder"
        body = (
            f"Reminder: “{appointment.summary}” starts at {when}.\n"
            "If you need to reschedule, contact the business.\n"
        )
    return subject, body


def _send_email(*, to_addr: str, subject: str, body: str) -> None:
    if not settings.mail_username or not settings.mail_password:
        # Never report an unconfigured transport as sent, in any environment.
        raise RuntimeError("mail_transport_unavailable")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.mail_username
    msg["To"] = to_addr
    msg.set_content(body)
    with smtplib.SMTP(settings.mail_server, settings.mail_port, timeout=20) as smtp:
        smtp.starttls()
        smtp.login(settings.mail_username, settings.mail_password)
        smtp.send_message(msg)


def _claim_delivery(db: Session, delivery_id: int, *, now: datetime) -> bool:
    """Atomically move one row to claimed with a lease + incremented attempt counter.

    Returns True only for the single caller that won the claim (P6-V01 #2).
    """
    result = db.execute(
        update(NotificationDelivery)
        .where(
            NotificationDelivery.id == delivery_id,
            NotificationDelivery.attempt_count < _MAX_ATTEMPTS,
            or_(
                NotificationDelivery.status.in_(_CLAIMABLE_STATUSES),
                (
                    (NotificationDelivery.status == STATUS_CLAIMED)
                    & (
                        NotificationDelivery.leased_until.is_(None)
                        | (NotificationDelivery.leased_until <= now)
                    )
                ),
            ),
        )
        .values(
            status=STATUS_CLAIMED,
            attempt_count=NotificationDelivery.attempt_count + 1,
            leased_until=now + timedelta(seconds=_LEASE_SECONDS),
        )
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return result.rowcount == 1


def deliver_notification(
    db: Session,
    appointment: Appointment,
    *,
    kind: str,
    force: bool = False,
) -> dict[str, Any]:
    user = db.get(User, appointment.user_id)
    if user is None:
        return {"ok": False, "status": STATUS_SKIPPED, "error_code": "user_missing"}

    prefs = load_product_prefs(user.config_json).notifications
    zone = _appointment_zone(appointment, db)
    now = _utcnow()
    key = _idem_key(kind, appointment.id, appointment.start_datetime)
    delivery = _ensure_delivery(
        db,
        user_id=user.id,
        appointment_id=appointment.id,
        kind=kind,
        idempotency_key=key,
    )
    db.commit()

    if delivery.status == STATUS_SENT:
        return {"ok": True, "status": STATUS_SENT, "idempotent": True}
    if delivery.status == STATUS_CANCELLED:
        return {"ok": False, "status": STATUS_CANCELLED, "error_code": "cancelled"}

    def _record_decision(status: str, code: str) -> dict[str, Any]:
        db.execute(
            update(NotificationDelivery)
            .where(
                NotificationDelivery.id == delivery.id,
                NotificationDelivery.status.notin_((STATUS_SENT, STATUS_CANCELLED)),
            )
            .values(status=status, error_code=code[:64])
        )
        db.commit()
        return {"ok": False, "status": status, "error_code": code}

    if not prefs.consent_at:
        return _record_decision(STATUS_SKIPPED, "no_consent")
    if kind == KIND_CONFIRMATION and not prefs.confirmations_enabled:
        return _record_decision(STATUS_SKIPPED, "confirmations_off")
    if kind == KIND_REMINDER and not prefs.reminders_enabled:
        return _record_decision(STATUS_SKIPPED, "reminders_off")
    if appointment.status in ("cancelled", "canceled", "failed"):
        return _record_decision(STATUS_SKIPPED, "appointment_inactive")

    if not force and _in_quiet_hours(now.astimezone(zone), prefs):
        nxt = _next_quiet_hours_end(now.astimezone(zone), prefs)
        db.execute(
            update(NotificationDelivery)
            .where(
                NotificationDelivery.id == delivery.id,
                NotificationDelivery.status.notin_((STATUS_SENT, STATUS_CANCELLED)),
            )
            .values(
                status=STATUS_SCHEDULED,
                error_code=f"quiet_until:{nxt.isoformat()}"[:64],
            )
        )
        db.commit()
        return {
            "ok": False,
            "status": STATUS_SCHEDULED,
            "error_code": "quiet_hours",
            "reschedule_at": nxt.astimezone(timezone.utc).isoformat(),
        }

    to_addr = _recipient(appointment, user)
    if not to_addr:
        return _record_decision(STATUS_SKIPPED, "no_recipient")

    if not _claim_delivery(db, delivery.id, now=now):
        db.expire_all()
        current = db.get(NotificationDelivery, delivery.id)
        status = current.status if current else delivery.status
        return {"ok": False, "status": status, "error_code": "not_claimable"}
    db.expire_all()
    delivery = db.get(NotificationDelivery, delivery.id) or delivery

    subject, body = _appointment_email_body(appointment, kind=kind, zone=zone)
    try:
        _send_email(to_addr=to_addr, subject=subject, body=body)
    except Exception as exc:  # noqa: BLE001
        code = "mail_transport_unavailable" if str(exc) == "mail_transport_unavailable" else type(exc).__name__[:64]
        delivery.status = STATUS_FAILED
        delivery.error_code = code
        delivery.leased_until = None
        db.commit()
        terminal = delivery.attempt_count >= _MAX_ATTEMPTS
        logger.warning(
            "notification_failed kind=%s appointment_id=%s code=%s terminal=%s",
            kind,
            appointment.id,
            delivery.error_code,
            terminal,
        )
        if terminal:
            _alert_terminal_failure(kind, appointment.id, delivery.error_code)
        return {
            "ok": False,
            "status": STATUS_FAILED,
            "error_code": delivery.error_code,
            "terminal": terminal,
        }

    delivery.status = STATUS_SENT
    delivery.sent_at = now
    delivery.error_code = None
    delivery.leased_until = None
    if kind == KIND_CONFIRMATION:
        appointment.confirmation_sent_at = now
    if kind == KIND_REMINDER:
        appointment.reminder_sent = True
    try:
        db.commit()
    except Exception:
        # SMTP delivery succeeded but the DB commit failed: the send cannot be
        # proven idempotent, so stop automatic retry rather than risk a
        # duplicate email and surface it for manual reconciliation.
        db.rollback()
        row = db.get(NotificationDelivery, delivery.id)
        if row is not None:
            row.status = STATUS_FAILED
            row.error_code = "ambiguous_send_commit_failed"
            row.attempt_count = _MAX_ATTEMPTS
            row.leased_until = None
            db.commit()
            _alert_terminal_failure(kind, appointment.id, row.error_code)
        raise
    return {"ok": True, "status": STATUS_SENT, "idempotent": False}


def _alert_terminal_failure(kind: str, appointment_id: int, error_code: str | None) -> None:
    """Surface a terminal (no-more-retries) delivery failure for operators."""
    try:
        from app.core.metrics import metrics

        metrics.incr("notifications", labels={"result": "terminal_failure"})
    except Exception:  # noqa: BLE001
        pass
    logger.error(
        "notification_terminal_failure kind=%s appointment_id=%s error_code=%s",
        kind,
        appointment_id,
        error_code,
    )


def enqueue_confirmation(db: Session, appointment: Appointment) -> None:
    """Ensure the outbox row is durable, then best-effort trigger the worker."""
    delivery = stage_confirmation_intent(db, appointment)
    if delivery.status == STATUS_CANCELLED:
        delivery.status = STATUS_SCHEDULED
        delivery.error_code = None
    if delivery.status == STATUS_SENT:
        db.commit()
        return
    db.commit()
    try:
        from app.workers.tasks import send_appointment_confirmation

        send_appointment_confirmation.delay(appointment.id)
    except Exception:  # noqa: BLE001
        delivery.status = STATUS_FAILED
        delivery.error_code = "enqueue_failed"
        db.commit()
        try:
            from app.core.metrics import metrics

            metrics.incr("notifications", labels={"result": "enqueue_failed"})
        except Exception:  # noqa: BLE001
            pass
        logger.warning(
            "confirmation_enqueue_failed appointment_id=%s", appointment.id
        )


def list_delivery_status(
    db: Session, user_id: int, *, appointment_id: int | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    """Bounded delivery status without recipient or message body."""
    stmt = (
        select(NotificationDelivery)
        .where(NotificationDelivery.user_id == user_id)
        .order_by(NotificationDelivery.id.desc())
        .limit(min(limit, 100))
    )
    if appointment_id is not None:
        stmt = stmt.where(NotificationDelivery.appointment_id == appointment_id)
    rows = list(db.scalars(stmt).all())
    return [
        {
            "id": row.id,
            "appointment_id": row.appointment_id,
            "kind": row.kind,
            "channel": row.channel,
            "status": row.status,
            "error_code": row.error_code,
            "sent_at": row.sent_at.isoformat() if row.sent_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def process_due_reminders(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or _utcnow()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    # Look ahead up to 7 days; per-tenant hours_before filters inside.
    horizon = now + timedelta(days=7)
    rows = list(
        db.scalars(
            select(Appointment).where(
                Appointment.reminder_sent.is_(False),
                Appointment.status.notin_(("cancelled", "canceled", "failed")),
                Appointment.start_datetime >= now,
                Appointment.start_datetime <= horizon,
            )
        ).all()
    )
    sent = skipped = failed = 0
    for appt in rows:
        user = db.get(User, appt.user_id)
        if user is None:
            skipped += 1
            continue
        prefs = load_product_prefs(user.config_json).notifications
        lead = timedelta(hours=prefs.reminder_hours_before)
        start = appt.start_datetime
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if start > now + lead:
            continue
        result = deliver_notification(db, appt, kind=KIND_REMINDER)
        if result.get("status") == STATUS_SENT:
            sent += 1
        elif result.get("status") == STATUS_FAILED:
            failed += 1
        else:
            skipped += 1
    return {"ok": True, "sent": sent, "skipped": skipped, "failed": failed}


def retry_pending_notifications(
    db: Session, *, limit: int = 200, now: datetime | None = None
) -> dict[str, Any]:
    """Sweep scheduled/failed outbox rows: retries failed sends and quiet-hours
    reschedules, and recovers from broker/enqueue outages (P6-V01 #2/#3).
    """
    now = now or _utcnow()
    rows = list(
        db.scalars(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.status.in_((STATUS_SCHEDULED, STATUS_FAILED)),
                NotificationDelivery.attempt_count < _MAX_ATTEMPTS,
            )
            .order_by(NotificationDelivery.id)
            .limit(limit)
        ).all()
    )
    sent = skipped = failed = 0
    for delivery in rows:
        appt = db.get(Appointment, delivery.appointment_id)
        if appt is None:
            delivery.status = STATUS_SKIPPED
            delivery.error_code = "appointment_missing"
            db.commit()
            skipped += 1
            continue
        result = deliver_notification(db, appt, kind=delivery.kind)
        status = result.get("status")
        if status == STATUS_SENT:
            sent += 1
        elif status == STATUS_FAILED:
            failed += 1
        else:
            skipped += 1
    return {"ok": True, "sent": sent, "skipped": skipped, "failed": failed}
