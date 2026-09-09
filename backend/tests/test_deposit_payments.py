"""Deposit payment intent + secure-link capture."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.service import create_catalog_item
from app.customers.service import get_or_create_customer
from app.db.base import Base
from app.db.models import (
    Location,
    PaymentIntent,
    Resource,
    SecureLinkDelivery,
    ServiceResourceRequirement,
    User,
)
from app.industries.restaurant import book_restaurant_reservation
from app.industries.service import assign_industry_profile
from app.payments.service import capture_payment, find_payment_by_token
from app.tenancy.service import create_organization_for_user


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_deposit_book_stages_payment_and_capture_confirms() -> None:
    db = _session()
    user = User(username="deposit", email="deposit@example.test", password="unused")
    db.add(user)
    db.flush()
    organization = create_organization_for_user(db, user)
    assign_industry_profile(
        db,
        organization_id=organization.id,
        industry_type="restaurant",
        overrides={
            "deposit_policy": {
                "enabled": True,
                "amount_minor": 2500,
                "currency": "EUR",
                "no_show_fee_minor": 1000,
            }
        },
    )
    location = Location(organization_id=organization.id, name="Main", timezone="UTC")
    dinner = create_catalog_item(
        db,
        organization_id=organization.id,
        name="Dinner",
        duration_minutes=90,
        bookable=True,
    )
    pool = Resource(
        organization_id=organization.id,
        location_id=location.id,
        resource_type="capacity_pool",
        name="Floor",
        capacity=20,
    )
    db.add_all((location, dinner, pool))
    db.flush()
    db.add(
        ServiceResourceRequirement(
            catalog_item_id=dinner.id,
            resource_type="capacity_pool",
            quantity=1,
            required=True,
        )
    )
    customer = get_or_create_customer(
        db,
        organization_id=organization.id,
        name="Ada",
        phone="+15551234567",
        email="ada@example.test",
    )
    db.commit()

    reservation = book_restaurant_reservation(
        db,
        organization_id=organization.id,
        catalog_item_id=dinner.id,
        location_id=location.id,
        start_datetime=datetime(2030, 7, 1, 19, 0, tzinfo=timezone.utc),
        party_size=2,
        customer_id=customer.id,
    )
    assert reservation.status == "held"
    deposit = (reservation.allocation_json or {}).get("deposit") or {}
    assert deposit.get("status") == "pending"
    assert deposit.get("payment_id") is not None

    payment = db.scalar(
        select(PaymentIntent).where(PaymentIntent.id == int(deposit["payment_id"]))
    )
    assert payment is not None
    assert payment.status == "pending"
    assert payment.purpose == "deposit"
    assert payment.amount_minor == 2500
    assert payment.secure_link_delivery_id is not None

    delivery = db.get(SecureLinkDelivery, payment.secure_link_delivery_id)
    assert delivery is not None
    assert delivery.status == "scheduled"
    assert delivery.purpose == "deposit"
    raw_token = delivery.token_ciphertext
    assert find_payment_by_token(db, raw_token) is not None

    captured = capture_payment(db, payment.id, token=raw_token)
    assert captured.status == "captured"

    db.refresh(reservation)
    assert reservation.status == "confirmed"
    assert ((reservation.allocation_json or {}).get("deposit") or {}).get("status") == (
        "captured"
    )
