"""Minimal customer lookup/create without vertical-specific metadata semantics."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Customer


def find_customer(
    db: Session, *, organization_id: int, phone: str | None, email: str | None
) -> Customer | None:
    identifiers = []
    if phone:
        identifiers.append(Customer.phone == phone)
    if email:
        identifiers.append(Customer.email == email)
    if not identifiers:
        return None
    return db.scalar(
        select(Customer).where(Customer.organization_id == organization_id, or_(*identifiers))
    )


def get_or_create_customer(
    db: Session,
    *,
    organization_id: int,
    name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    language: str | None = None,
) -> Customer:
    existing = find_customer(db, organization_id=organization_id, phone=phone, email=email)
    if existing is not None:
        return existing
    customer = Customer(
        organization_id=organization_id,
        name=name,
        phone=phone,
        email=email,
        language=language,
    )
    db.add(customer)
    return customer
