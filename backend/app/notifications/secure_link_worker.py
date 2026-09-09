"""Deliver scheduled SecureLinkDelivery rows via SMS or email."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import SecureLinkDelivery
from app.notifications.service import _send_email

logger = logging.getLogger(__name__)

STATUS_SCHEDULED = "scheduled"
STATUS_SENT = "sent"
STATUS_FAILED = "failed"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _twilio_configured() -> bool:
    return bool(
        (settings.twilio_account_sid or "").strip()
        and (settings.twilio_auth_token or "").strip()
        and (settings.twilio_phone_number or "").strip()
    )


def _mail_configured() -> bool:
    return bool((settings.mail_username or "").strip() and (settings.mail_password or "").strip())


def _send_sms(*, to_phone: str, body: str) -> None:
    import twilio.rest

    client = twilio.rest.Client(settings.twilio_account_sid, settings.twilio_auth_token)
    client.messages.create(
        to=to_phone,
        from_=settings.twilio_phone_number,
        body=body,
    )


def _message_body(delivery: SecureLinkDelivery) -> str:
    meta = dict(delivery.metadata_json or {})
    url = str(meta.get("secure_url") or "").strip()
    purpose = (delivery.purpose or "link").replace("_", " ")
    if url:
        return f"Your {purpose} link: {url}"
    return f"Your {purpose} link is ready. Open the app to continue."


def deliver_one(db: Session, delivery: SecureLinkDelivery) -> dict[str, Any]:
    if delivery.status == STATUS_SENT:
        return {"ok": True, "status": STATUS_SENT, "idempotent": True}
    if delivery.expires_at is not None and _aware(delivery.expires_at) <= _utcnow():
        delivery.status = STATUS_FAILED
        delivery.error_code = "expired"
        delivery.attempt_count = int(delivery.attempt_count or 0) + 1
        db.commit()
        return {"ok": False, "status": STATUS_FAILED, "error_code": "expired"}

    delivery.attempt_count = int(delivery.attempt_count or 0) + 1
    body = _message_body(delivery)
    subject = f"Your {(delivery.purpose or 'secure').replace('_', ' ')} link"
    try:
        if delivery.channel == "sms" and _twilio_configured():
            _send_sms(to_phone=delivery.recipient, body=body)
        elif _mail_configured():
            _send_email(to_addr=delivery.recipient, subject=subject, body=body)
        else:
            raise RuntimeError("transport_unavailable")
        delivery.status = STATUS_SENT
        delivery.sent_at = _utcnow()
        delivery.error_code = None
        db.commit()
        return {"ok": True, "status": STATUS_SENT, "id": delivery.id}
    except Exception as exc:  # noqa: BLE001
        logger.warning("secure link delivery failed id=%s: %s", delivery.id, type(exc).__name__)
        delivery.status = STATUS_FAILED
        delivery.error_code = type(exc).__name__[:64]
        db.commit()
        return {
            "ok": False,
            "status": STATUS_FAILED,
            "id": delivery.id,
            "error_code": delivery.error_code,
        }


def deliver_scheduled_secure_links(db: Session, *, limit: int = 50) -> dict[str, Any]:
    now = _utcnow()
    rows = list(
        db.scalars(
            select(SecureLinkDelivery)
            .where(SecureLinkDelivery.status == STATUS_SCHEDULED)
            .order_by(SecureLinkDelivery.id)
            .limit(limit)
        ).all()
    )
    results = [deliver_one(db, row) for row in rows if _aware(row.expires_at) > now]
    return {
        "ok": True,
        "processed": len(results),
        "sent": sum(1 for item in results if item.get("status") == STATUS_SENT),
        "failed": sum(1 for item in results if item.get("status") == STATUS_FAILED),
    }
