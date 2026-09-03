"""Consent-aware appointment email confirmations and reminders (P6-01)."""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime, time, timedelta, timezone
from email.message import EmailMessage
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.calendars.service import get_auth_record
from app.core.config import settings
from app.db.models import Appointment, NotificationDelivery, User
from app.users.product_prefs import NotificationPrefs, load_product_prefs

logger = logging.getLogger(__name__)

KIND_CONFIRMATION = "confirmation"
KIND_REMINDER = "reminder"
STATUS_PENDING = "pending"
STATUS_SENT = "sent"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"


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


def _recipient(appointment: Appointment, user: User) -> str | None:
    email = (appointment.client_email or "").strip() or (user.email or "").strip()
    return email or None


def _idem_key(kind: str, appointment_id: int, slot_start: datetime) -> str:
    return f"{kind}:{appointment_id}:{slot_start.astimezone(timezone.utc).isoformat()}"


def _ensure_delivery(
    db: Session,
    *,
    user_id: int,
    appointment_id: int,
    kind: str,
    idempotency_key: str,
) -> NotificationDelivery:
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
        status=STATUS_PENDING,
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


def _send_email(*, to_addr: str, subject: str, body: str) -> None:
    if not settings.mail_username or not settings.mail_password:
        if settings.is_production:
            raise RuntimeError("mail_transport_unavailable")
        logger.info("Appointment notification skipped (mail not configured)")
        return
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.mail_username
    msg["To"] = to_addr
    msg.set_content(body)
    with smtplib.SMTP(settings.mail_server, settings.mail_port, timeout=20) as smtp:
        smtp.starttls()
        smtp.login(settings.mail_username, settings.mail_password)
        smtp.send_message(msg)


def _appointment_email_body(appointment: Appointment, *, kind: str) -> tuple[str, str]:
    when = appointment.start_datetime.astimezone(timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )
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
    if not prefs.consent_at:
        return {"ok": False, "status": STATUS_SKIPPED, "error_code": "no_consent"}
    if kind == KIND_CONFIRMATION and not prefs.confirmations_enabled:
        return {"ok": False, "status": STATUS_SKIPPED, "error_code": "confirmations_off"}
    if kind == KIND_REMINDER and not prefs.reminders_enabled:
        return {"ok": False, "status": STATUS_SKIPPED, "error_code": "reminders_off"}
    if appointment.status in ("cancelled", "canceled", "failed"):
        return {"ok": False, "status": STATUS_SKIPPED, "error_code": "appointment_inactive"}

    zone = _tenant_zone(db, user.id)
    now = datetime.now(timezone.utc)
    if not force and _in_quiet_hours(now.astimezone(zone), prefs):
        return {"ok": False, "status": STATUS_SKIPPED, "error_code": "quiet_hours"}

    to_addr = _recipient(appointment, user)
    if not to_addr:
        return {"ok": False, "status": STATUS_SKIPPED, "error_code": "no_recipient"}

    key = _idem_key(kind, appointment.id, appointment.start_datetime)
    delivery = _ensure_delivery(
        db,
        user_id=user.id,
        appointment_id=appointment.id,
        kind=kind,
        idempotency_key=key,
    )
    if delivery.status == STATUS_SENT:
        return {"ok": True, "status": STATUS_SENT, "idempotent": True}

    subject, body = _appointment_email_body(appointment, kind=kind)
    try:
        _send_email(to_addr=to_addr, subject=subject, body=body)
    except Exception as exc:  # noqa: BLE001
        delivery.status = STATUS_FAILED
        delivery.error_code = type(exc).__name__[:64]
        db.commit()
        logger.warning(
            "notification_failed kind=%s appointment_id=%s code=%s",
            kind,
            appointment.id,
            delivery.error_code,
        )
        return {"ok": False, "status": STATUS_FAILED, "error_code": delivery.error_code}

    delivery.status = STATUS_SENT
    delivery.sent_at = now
    delivery.error_code = None
    if kind == KIND_CONFIRMATION:
        appointment.confirmation_sent_at = now
    if kind == KIND_REMINDER:
        appointment.reminder_sent = True
    db.commit()
    return {"ok": True, "status": STATUS_SENT, "idempotent": False}


def enqueue_confirmation(db: Session, appointment: Appointment) -> None:
    """Best-effort after booking commit — failures are recorded, not raised."""
    try:
        from app.workers.tasks import send_appointment_confirmation

        send_appointment_confirmation.delay(appointment.id)
    except Exception:  # noqa: BLE001
        logger.warning(
            "confirmation_enqueue_failed appointment_id=%s", appointment.id
        )


def cancel_pending_for_appointment(db: Session, appointment_id: int) -> int:
    rows = list(
        db.scalars(
            select(NotificationDelivery).where(
                NotificationDelivery.appointment_id == appointment_id,
                NotificationDelivery.status == STATUS_PENDING,
            )
        ).all()
    )
    for row in rows:
        row.status = STATUS_SKIPPED
        row.error_code = "appointment_cancelled"
    if rows:
        db.commit()
    return len(rows)


def process_due_reminders(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
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
