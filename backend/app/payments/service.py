"""Deposit and payment capture service."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Customer, PaymentIntent, Reservation, SecureLinkDelivery
from app.notifications.secure_links import stage_secure_link
from app.payments.providers import ManualProvider, get_provider


class PaymentError(ValueError):
    """Payment domain error."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _hash_token(raw: str) -> str:
    return sha256(raw.encode("utf-8")).hexdigest()


def _payment_by_id(db: Session, payment_id: int) -> PaymentIntent:
    row = db.get(PaymentIntent, payment_id)
    if row is None:
        raise PaymentError("payment not found")
    return row


def find_payment_by_token(db: Session, raw_token: str) -> PaymentIntent | None:
    token = (raw_token or "").strip()
    if not token:
        return None
    delivery = db.scalar(
        select(SecureLinkDelivery).where(
            SecureLinkDelivery.token_hash == _hash_token(token)
        )
    )
    if delivery is None:
        return None
    payment_id = (delivery.metadata_json or {}).get("payment_id")
    if payment_id is None:
        row = db.scalar(
            select(PaymentIntent).where(
                PaymentIntent.secure_link_delivery_id == delivery.id
            )
        )
        return row
    return db.get(PaymentIntent, int(payment_id))


def create_deposit_payment_for_reservation(
    db: Session,
    *,
    reservation: Reservation,
    amount_minor: int,
    currency: str,
    provider: str = "manual",
) -> PaymentIntent:
    """Create a deposit PaymentIntent and stage a secure payment link when possible."""
    if amount_minor < 0:
        raise PaymentError("amount_minor must be non-negative")
    customer: Customer | None = None
    if reservation.customer_id is not None:
        customer = db.get(Customer, reservation.customer_id)

    intent = PaymentIntent(
        organization_id=reservation.organization_id,
        reservation_id=reservation.id,
        customer_id=reservation.customer_id,
        amount_minor=int(amount_minor),
        currency=(currency or "EUR").upper()[:3],
        purpose="deposit",
        provider=(provider or "manual").strip().lower() or "manual",
        status="pending",
        metadata_json={
            "reservation_id": reservation.id,
            "party_size": reservation.party_size,
        },
    )
    db.add(intent)
    db.flush()

    phone = (customer.phone if customer else None) or None
    email = (customer.email if customer else None) or None
    name = (customer.name if customer else None) or None
    if phone or email:
        delivery = stage_secure_link(
            db,
            organization_id=reservation.organization_id,
            purpose="deposit",
            client_phone=phone,
            client_email=email,
            client_name=name,
            metadata={
                "payment_id": intent.id,
                "reservation_id": reservation.id,
                "amount_minor": intent.amount_minor,
                "currency": intent.currency,
            },
        )
        intent.secure_link_delivery_id = delivery.id
        intent.metadata_json = {
            **dict(intent.metadata_json or {}),
            "secure_link_delivery_id": delivery.id,
        }

    if intent.provider == "stripe":
        adapter = get_provider("stripe")
        base = ""
        try:
            from app.core.config import settings

            base = (settings.frontend_base_url or settings.public_base_url or "").rstrip("/")
        except Exception:  # noqa: BLE001
            base = ""
        success = f"{base}/secure/deposit?payment_id={intent.id}&status=success"
        cancel = f"{base}/secure/deposit?payment_id={intent.id}&status=cancel"
        intent.provider_ref = adapter.create_checkout(
            intent, success_url=success, cancel_url=cancel
        )

    db.flush()
    return intent


def _apply_deposit_captured(db: Session, intent: PaymentIntent) -> Reservation | None:
    if intent.reservation_id is None:
        return None
    reservation = db.get(Reservation, intent.reservation_id)
    if reservation is None:
        return None
    allocation = dict(reservation.allocation_json or {})
    deposit = dict(allocation.get("deposit") or {})
    deposit["status"] = "captured"
    deposit["payment_id"] = intent.id
    deposit["captured_at"] = _utcnow().isoformat()
    allocation["deposit"] = deposit
    reservation.allocation_json = allocation

    held_for_deposit = reservation.status == "held" and bool(deposit.get("required"))
    if held_for_deposit:
        from app.reservations.service import commit_reservation

        # Clear hold expiry so commit does not treat the deposit hold as expired.
        reservation.hold_expires_at = None
        db.flush()
        return commit_reservation(db, reservation.id, sync_calendar=False)
    db.flush()
    return reservation


def capture_payment(
    db: Session,
    payment_id: int,
    *,
    token: str | None = None,
    provider_ref: str | None = None,
) -> PaymentIntent:
    intent = _payment_by_id(db, payment_id)
    if intent.status == "captured":
        return intent
    if intent.status in {"cancelled", "expired", "failed"}:
        raise PaymentError(f"payment is {intent.status}")

    adapter = get_provider(intent.provider)
    if isinstance(adapter, ManualProvider) or intent.provider in {
        "manual",
        "twilio_sms_link",
    }:
        if not token:
            raise PaymentError("token required")
        matched = find_payment_by_token(db, token)
        if matched is None or matched.id != intent.id:
            raise PaymentError("invalid payment token")
        delivery = (
            db.get(SecureLinkDelivery, intent.secure_link_delivery_id)
            if intent.secure_link_delivery_id
            else None
        )
        if delivery is not None and _aware(delivery.expires_at) <= _utcnow():
            intent.status = "expired"
            db.commit()
            raise PaymentError("payment link expired")
        adapter.capture(intent, token=token)
    else:
        adapter.capture(intent, token=token)
        if provider_ref:
            intent.provider_ref = provider_ref

    intent.status = "captured"
    intent.metadata_json = {
        **dict(intent.metadata_json or {}),
        "captured_at": _utcnow().isoformat(),
    }
    _apply_deposit_captured(db, intent)
    db.commit()
    db.refresh(intent)
    return intent


def mark_failed(
    db: Session, payment_id: int, *, error_code: str | None = None
) -> PaymentIntent:
    intent = _payment_by_id(db, payment_id)
    if intent.status == "captured":
        raise PaymentError("captured payment cannot fail")
    intent.status = "failed"
    meta = dict(intent.metadata_json or {})
    if error_code:
        meta["error_code"] = error_code
    meta["failed_at"] = _utcnow().isoformat()
    intent.metadata_json = meta
    db.commit()
    db.refresh(intent)
    return intent


def payment_public_view(intent: PaymentIntent) -> dict[str, Any]:
    return {
        "id": intent.id,
        "organization_id": intent.organization_id,
        "reservation_id": intent.reservation_id,
        "amount_minor": intent.amount_minor,
        "currency": intent.currency,
        "purpose": intent.purpose,
        "provider": intent.provider,
        "status": intent.status,
    }
