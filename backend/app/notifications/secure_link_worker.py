"""Deliver scheduled SecureLinkDelivery rows via SMS or email."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import SecureLinkDelivery, User
from app.notifications.secure_links import build_secure_link_url
from app.notifications.transports import _send_email

logger = logging.getLogger(__name__)

STATUS_SCHEDULED = "scheduled"
STATUS_PROCESSING = "processing"
STATUS_SENT = "sent"
STATUS_FAILED = "failed"
STATUS_EXPIRED = "expired"

_LEASE_SECONDS = 60
_MAX_ATTEMPTS = 5
_TRANSPORT_UNAVAILABLE = "transport_unavailable"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _mail_configured() -> bool:
    return bool((settings.mail_username or "").strip() and (settings.mail_password or "").strip())


def _resolve_twilio_credentials(
    db: Session, organization_id: int
) -> tuple[str, str, str] | None:
    """Prefer tenant User Twilio credentials; fall back to process-global settings."""
    user = db.scalar(
        select(User)
        .where(
            User.organization_id == organization_id,
            User.twilio_account_sid.is_not(None),
            User.twilio_auth_token.is_not(None),
            or_(
                User.twilio_phone_e164.is_not(None),
                User.twilio_phone_number.is_not(None),
            ),
        )
        .order_by(User.id)
        .limit(1)
    )
    if user is not None:
        phone = (user.twilio_phone_e164 or user.twilio_phone_number or "").strip()
        sid = (user.twilio_account_sid or "").strip()
        token = (user.twilio_auth_token or "").strip()
        if sid and token and phone:
            return sid, token, phone

    sid = (settings.twilio_account_sid or "").strip()
    token = (settings.twilio_auth_token or "").strip()
    phone = (settings.twilio_phone_number or "").strip()
    if sid and token and phone:
        return sid, token, phone
    return None


def _send_sms(
    *,
    to_phone: str,
    body: str,
    account_sid: str,
    auth_token: str,
    from_number: str,
) -> None:
    import twilio.rest

    client = twilio.rest.Client(account_sid, auth_token)
    client.messages.create(to=to_phone, from_=from_number, body=body)


def _message_body(delivery: SecureLinkDelivery, *, raw_token: str) -> str:
    purpose = (delivery.purpose or "link").replace("_", " ")
    url = build_secure_link_url(raw_token=raw_token, purpose=delivery.purpose or "link")
    return f"Your {purpose} link: {url}"


def expire_stale_scheduled(db: Session, *, now: datetime | None = None) -> int:
    """Transition expired scheduled rows to a terminal expired state."""
    moment = now or _utcnow()
    result = db.execute(
        update(SecureLinkDelivery)
        .where(
            SecureLinkDelivery.status == STATUS_SCHEDULED,
            SecureLinkDelivery.expires_at <= moment,
        )
        .values(status=STATUS_EXPIRED, error_code="expired", claim_token=None, leased_until=None)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return int(getattr(result, "rowcount", 0) or 0)


def reclaim_abandoned_claims(db: Session, *, now: datetime | None = None) -> int:
    """Return abandoned processing rows to scheduled after lease expiry."""
    moment = now or _utcnow()
    result = db.execute(
        update(SecureLinkDelivery)
        .where(
            SecureLinkDelivery.status == STATUS_PROCESSING,
            or_(
                SecureLinkDelivery.leased_until.is_(None),
                SecureLinkDelivery.leased_until <= moment,
            ),
        )
        .values(status=STATUS_SCHEDULED, claim_token=None, leased_until=None)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return int(getattr(result, "rowcount", 0) or 0)


def _claim_one(db: Session, *, now: datetime, lease_seconds: int) -> SecureLinkDelivery | None:
    """Atomically claim one eligible scheduled row; commit before caller does I/O."""
    dialect = db.get_bind().dialect.name
    claim = secrets.token_hex(16)
    lease_until = now + timedelta(seconds=lease_seconds)

    if dialect == "postgresql":
        candidate_id = db.scalar(
            select(SecureLinkDelivery.id)
            .where(
                SecureLinkDelivery.status == STATUS_SCHEDULED,
                SecureLinkDelivery.expires_at > now,
                SecureLinkDelivery.attempt_count < _MAX_ATTEMPTS,
            )
            .order_by(SecureLinkDelivery.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if candidate_id is None:
            db.rollback()
            return None
        result = db.execute(
            update(SecureLinkDelivery)
            .where(
                SecureLinkDelivery.id == candidate_id,
                SecureLinkDelivery.status == STATUS_SCHEDULED,
            )
            .values(
                status=STATUS_PROCESSING,
                claim_token=claim,
                leased_until=lease_until,
                attempt_count=SecureLinkDelivery.attempt_count + 1,
                error_code=None,
            )
            .execution_options(synchronize_session=False)
        )
        db.commit()
        if int(getattr(result, "rowcount", 0) or 0) != 1:
            return None
        return db.get(SecureLinkDelivery, candidate_id)

    # SQLite / other: optimistic claim by id without holding locks across I/O.
    candidate = db.scalar(
        select(SecureLinkDelivery)
        .where(
            SecureLinkDelivery.status == STATUS_SCHEDULED,
            SecureLinkDelivery.expires_at > now,
            SecureLinkDelivery.attempt_count < _MAX_ATTEMPTS,
        )
        .order_by(SecureLinkDelivery.id)
        .limit(1)
    )
    if candidate is None:
        return None
    result = db.execute(
        update(SecureLinkDelivery)
        .where(
            SecureLinkDelivery.id == candidate.id,
            SecureLinkDelivery.status == STATUS_SCHEDULED,
        )
        .values(
            status=STATUS_PROCESSING,
            claim_token=claim,
            leased_until=lease_until,
            attempt_count=SecureLinkDelivery.attempt_count + 1,
            error_code=None,
        )
        .execution_options(synchronize_session=False)
    )
    db.commit()
    if int(getattr(result, "rowcount", 0) or 0) != 1:
        return None
    db.expire_all()
    return db.get(SecureLinkDelivery, candidate.id)


def claim_due_deliveries(
    db: Session, *, limit: int = 50, lease_seconds: int = _LEASE_SECONDS
) -> list[SecureLinkDelivery]:
    """Expire stale rows, reclaim abandoned claims, then claim up to `limit` rows."""
    now = _utcnow()
    expire_stale_scheduled(db, now=now)
    reclaim_abandoned_claims(db, now=now)
    claimed: list[SecureLinkDelivery] = []
    for _ in range(max(0, limit)):
        row = _claim_one(db, now=now, lease_seconds=lease_seconds)
        if row is None:
            break
        claimed.append(row)
    return claimed


def _finish_sent(db: Session, delivery_id: int, *, claim_token: str) -> None:
    db.execute(
        update(SecureLinkDelivery)
        .where(
            SecureLinkDelivery.id == delivery_id,
            SecureLinkDelivery.claim_token == claim_token,
            SecureLinkDelivery.status == STATUS_PROCESSING,
        )
        .values(
            status=STATUS_SENT,
            sent_at=_utcnow(),
            error_code=None,
            token_ciphertext=None,
            claim_token=None,
            leased_until=None,
        )
        .execution_options(synchronize_session=False)
    )
    db.commit()


def _finish_failed(
    db: Session,
    delivery_id: int,
    *,
    claim_token: str,
    error_code: str,
    terminal: bool,
) -> None:
    status = STATUS_FAILED if terminal else STATUS_SCHEDULED
    values: dict[str, Any] = {
        "status": status,
        "error_code": error_code[:64],
        "claim_token": None,
        "leased_until": None,
    }
    db.execute(
        update(SecureLinkDelivery)
        .where(
            SecureLinkDelivery.id == delivery_id,
            SecureLinkDelivery.claim_token == claim_token,
            SecureLinkDelivery.status == STATUS_PROCESSING,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    db.commit()


def deliver_one(db: Session, delivery: SecureLinkDelivery) -> dict[str, Any]:
    """Send one already-claimed delivery. Must not be called inside an open write txn needing I/O isolation beyond the claim."""
    if delivery.status == STATUS_SENT:
        return {"ok": True, "status": STATUS_SENT, "idempotent": True}
    if delivery.status == STATUS_EXPIRED or (
        delivery.expires_at is not None and _aware(delivery.expires_at) <= _utcnow()
    ):
        delivery.status = STATUS_EXPIRED
        delivery.error_code = "expired"
        delivery.claim_token = None
        delivery.leased_until = None
        db.commit()
        return {"ok": False, "status": STATUS_EXPIRED, "error_code": "expired"}

    claim_token = delivery.claim_token or ""
    delivery_id = delivery.id
    raw_token = delivery.token_ciphertext
    if not raw_token:
        # Legacy rows may have stored the URL in metadata; prefer fail-closed.
        _finish_failed(
            db,
            delivery_id,
            claim_token=claim_token,
            error_code="token_unavailable",
            terminal=True,
        )
        return {
            "ok": False,
            "status": STATUS_FAILED,
            "id": delivery_id,
            "error_code": "token_unavailable",
        }

    body = _message_body(delivery, raw_token=raw_token)
    subject = f"Your {(delivery.purpose or 'secure').replace('_', ' ')} link"
    channel = (delivery.channel or "").strip().lower()
    organization_id = delivery.organization_id
    recipient = delivery.recipient
    attempt_count = int(delivery.attempt_count or 0)

    try:
        if channel == "sms":
            creds = _resolve_twilio_credentials(db, organization_id)
            if creds is None:
                raise RuntimeError(_TRANSPORT_UNAVAILABLE)
            sid, token, from_number = creds
            # Commit is already done by claim; I/O happens with no write lock held.
            _send_sms(
                to_phone=recipient,
                body=body,
                account_sid=sid,
                auth_token=token,
                from_number=from_number,
            )
        elif channel == "email":
            if not _mail_configured():
                raise RuntimeError(_TRANSPORT_UNAVAILABLE)
            _send_email(to_addr=recipient, subject=subject, body=body)
        else:
            raise RuntimeError(_TRANSPORT_UNAVAILABLE)
    except Exception as exc:  # noqa: BLE001
        code = (
            _TRANSPORT_UNAVAILABLE
            if str(exc) == _TRANSPORT_UNAVAILABLE
            else type(exc).__name__[:64]
        )
        terminal = attempt_count >= _MAX_ATTEMPTS
        logger.warning(
            "secure link delivery failed id=%s code=%s terminal=%s",
            delivery_id,
            code,
            terminal,
        )
        _finish_failed(
            db, delivery_id, claim_token=claim_token, error_code=code, terminal=terminal
        )
        return {
            "ok": False,
            "status": STATUS_FAILED if terminal else STATUS_SCHEDULED,
            "id": delivery_id,
            "error_code": code,
            "terminal": terminal,
        }

    _finish_sent(db, delivery_id, claim_token=claim_token)
    return {"ok": True, "status": STATUS_SENT, "id": delivery_id}


def deliver_scheduled_secure_links(db: Session, *, limit: int = 50) -> dict[str, Any]:
    claimed = claim_due_deliveries(db, limit=limit)
    results = [deliver_one(db, row) for row in claimed]
    return {
        "ok": True,
        "processed": len(results),
        "sent": sum(1 for item in results if item.get("status") == STATUS_SENT),
        "failed": sum(
            1
            for item in results
            if item.get("status") in {STATUS_FAILED, STATUS_EXPIRED}
            or item.get("error_code")
        ),
        "expired": sum(1 for item in results if item.get("status") == STATUS_EXPIRED),
    }
