"""Canonical customer lookup/create with org-scoped phone/email dedup."""

from __future__ import annotations

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Customer, Reservation
from app.telephony.phones import canonical_e164


class CustomerError(ValueError):
    """Safe customer domain violation."""


def normalize_phone(phone: str | None, *, default_region: str | None = "US") -> str | None:
    """Normalize to E.164 when possible; otherwise digits with a leading +."""
    if phone is None:
        return None
    raw = phone.strip()
    if not raw:
        return None
    e164 = canonical_e164(raw, default_region=default_region)
    if e164:
        return e164
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return None
    if raw.startswith("+"):
        return f"+{digits}"
    # Require an explicit country code when phonenumbers cannot validate.
    if len(digits) >= 10:
        return f"+{digits}"
    return None


def normalize_email(email: str | None) -> str | None:
    if email is None:
        return None
    cleaned = email.strip().lower()
    return cleaned or None


def find_customer(
    db: Session,
    *,
    organization_id: int,
    phone: str | None,
    email: str | None,
    for_update: bool = False,
) -> Customer | None:
    phone_n = normalize_phone(phone)
    email_n = normalize_email(email)
    identifiers = []
    if phone_n:
        identifiers.append(Customer.phone == phone_n)
    if email_n:
        identifiers.append(Customer.email == email_n)
    if not identifiers:
        return None
    statement = select(Customer).where(
        Customer.organization_id == organization_id, or_(*identifiers)
    )
    if for_update:
        statement = statement.with_for_update()
    return db.scalar(statement)


def get_or_create_customer(
    db: Session,
    *,
    organization_id: int,
    name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    language: str | None = None,
) -> Customer:
    phone_n = normalize_phone(phone)
    email_n = normalize_email(email)
    existing = find_customer(
        db, organization_id=organization_id, phone=phone_n, email=email_n, for_update=True
    )
    if existing is not None:
        if name and not existing.name:
            existing.name = name
        if language and not existing.language:
            existing.language = language
        return existing
    customer = Customer(
        organization_id=organization_id,
        name=name,
        phone=phone_n,
        email=email_n,
        language=language,
    )
    try:
        with db.begin_nested():
            db.add(customer)
            db.flush()
    except IntegrityError:
        existing = find_customer(
            db, organization_id=organization_id, phone=phone_n, email=email_n, for_update=True
        )
        if existing is not None:
            return existing
        raise
    return customer


def get_customer(db: Session, *, organization_id: int, customer_id: int) -> Customer | None:
    return db.scalar(
        select(Customer).where(
            Customer.id == customer_id, Customer.organization_id == organization_id
        )
    )


def list_customer_reservations(
    db: Session, *, organization_id: int, customer_id: int
) -> list[Reservation]:
    return list(
        db.scalars(
            select(Reservation)
            .where(
                Reservation.organization_id == organization_id,
                Reservation.customer_id == customer_id,
            )
            .order_by(Reservation.start_datetime.desc(), Reservation.id.desc())
        ).all()
    )


def merge_customers(
    db: Session,
    *,
    organization_id: int,
    source_customer_id: int,
    target_customer_id: int,
) -> Customer:
    if source_customer_id == target_customer_id:
        raise CustomerError("source and target must differ")
    source = get_customer(db, organization_id=organization_id, customer_id=source_customer_id)
    target = get_customer(db, organization_id=organization_id, customer_id=target_customer_id)
    if source is None or target is None:
        raise CustomerError("customer not found")
    db.execute(
        update(Reservation)
        .where(
            Reservation.organization_id == organization_id,
            Reservation.customer_id == source.id,
        )
        .values(customer_id=target.id)
    )
    if not target.name and source.name:
        target.name = source.name
    if not target.phone and source.phone:
        target.phone = source.phone
    if not target.email and source.email:
        target.email = source.email
    if not target.language and source.language:
        target.language = source.language
    if source.consent_preferences:
        merged = dict(target.consent_preferences or {})
        merged.update(source.consent_preferences)
        target.consent_preferences = merged
    if source.metadata_json:
        merged_meta = dict(target.metadata_json or {})
        merged_meta.update(source.metadata_json)
        target.metadata_json = merged_meta
    db.delete(source)
    db.flush()
    return target
