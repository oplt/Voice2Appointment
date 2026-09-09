"""Stage tokenized secure-link deliveries for SMS/email workers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.customers.service import get_or_create_customer
from app.db.models import SecureLinkDelivery

STATUS_SCHEDULED = "scheduled"
_DEFAULT_TTL_HOURS = 48


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(raw: str) -> str:
    return sha256(raw.encode("utf-8")).hexdigest()


def _mask_recipient(value: str, *, channel: str) -> str:
    text = value.strip()
    if channel == "email":
        if "@" not in text:
            return "***"
        local, _, domain = text.partition("@")
        if len(local) <= 2:
            return f"*@{domain}"
        return f"{local[0]}***{local[-1]}@{domain}"
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) < 4:
        return "***"
    return f"***{digits[-4:]}"


def build_secure_link_url(*, raw_token: str, purpose: str) -> str:
    base = (settings.frontend_base_url or settings.public_base_url or "").rstrip("/")
    return f"{base}/secure/{purpose.strip() or 'link'}?t={raw_token}"


def stage_secure_link(
    db: Session,
    *,
    organization_id: int,
    purpose: str = "payment",
    client_phone: str | None = None,
    client_email: str | None = None,
    client_name: str | None = None,
    actor_user_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> SecureLinkDelivery:
    """Persist a tokenized secure-link intent and queue it for delivery.

    Flushes but does not commit — callers own the transaction boundary.
    The raw token is stored for the delivery worker and must never be returned
    on the voice tool response surface.
    """
    phone = (client_phone or "").strip() or None
    email = (client_email or "").strip() or None
    if not phone and not email:
        raise ValueError("client_phone or client_email is required")

    channel = "sms" if phone else "email"
    recipient = phone or email or ""
    customer = get_or_create_customer(
        db,
        organization_id=organization_id,
        name=client_name,
        phone=phone,
        email=email,
    )
    db.flush()

    purpose_key = (purpose or "payment").strip() or "payment"
    idempotency_key = (
        f"secure_link:{organization_id}:{customer.id}:{purpose_key}:{channel}:{recipient}"
    )
    existing = db.scalar(
        select(SecureLinkDelivery).where(
            SecureLinkDelivery.idempotency_key == idempotency_key,
            SecureLinkDelivery.status == STATUS_SCHEDULED,
        )
    )
    if existing is not None and existing.expires_at > _utcnow():
        return existing

    raw_token = token_urlsafe(32)
    expires_at = _utcnow() + timedelta(hours=_DEFAULT_TTL_HOURS)
    secure_url = build_secure_link_url(raw_token=raw_token, purpose=purpose_key)
    meta = dict(metadata or {})
    meta.update(
        {
            "purpose": purpose_key,
            "recipient_masked": _mask_recipient(recipient, channel=channel),
            "actor_user_id": actor_user_id,
            "url_path": f"/secure/{purpose_key}",
            # Delivery worker only — never surface on the voice tool response.
            "secure_url": secure_url,
        }
    )
    row = SecureLinkDelivery(
        organization_id=organization_id,
        customer_id=customer.id,
        purpose=purpose_key,
        channel=channel,
        recipient=recipient,
        token_hash=_hash_token(raw_token),
        token_ciphertext=raw_token,
        status=STATUS_SCHEDULED,
        expires_at=expires_at,
        idempotency_key=idempotency_key,
        metadata_json=meta,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.expire_all()
        existing = db.scalar(
            select(SecureLinkDelivery).where(
                SecureLinkDelivery.idempotency_key == idempotency_key
            )
        )
        if existing is None:
            raise
        return existing
    return row
