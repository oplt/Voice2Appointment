"""SMTP/email transport helpers for notification delivery."""

from __future__ import annotations

import smtplib
from datetime import timezone
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.db.models import Appointment

KIND_CONFIRMATION = "confirmation"


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


