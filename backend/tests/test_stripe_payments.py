"""Stripe checkout + webhook capture paths."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.service import create_catalog_item
from app.core.config import settings
from app.customers.service import get_or_create_customer
from app.db.base import Base
from app.db.models import Location, Resource, ServiceResourceRequirement, User
from app.industries.restaurant import book_restaurant_reservation
from app.industries.service import assign_industry_profile
from app.payments.providers import StripeProvider, get_provider
from app.payments.service import capture_payment
from app.tenancy.service import create_organization_for_user


def _session() -> Session:
    if not (settings.fernet_key or "").strip():
        settings.fernet_key = Fernet.generate_key().decode()
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _restaurant_setup(db: Session):
    user = User(username="stripepay", email="stripepay@example.test", password="unused")
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
                "amount_minor": 1500,
                "currency": "EUR",
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
        name="Bea",
        email="bea@example.test",
    )
    db.commit()
    reservation = book_restaurant_reservation(
        db,
        organization_id=organization.id,
        catalog_item_id=dinner.id,
        location_id=location.id,
        start_datetime=datetime(2030, 8, 1, 19, 0, tzinfo=timezone.utc),
        party_size=2,
        customer_id=customer.id,
    )
    return reservation


def test_stripe_provider_requires_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", None)
    provider = StripeProvider()
    intent = SimpleNamespace(
        id=1,
        currency="EUR",
        amount_minor=1000,
        purpose="deposit",
        organization_id=1,
        reservation_id=2,
    )
    with pytest.raises(RuntimeError, match="STRIPE_SECRET_KEY"):
        provider.create_checkout(
            intent,  # type: ignore[arg-type]
            success_url="https://example.test/ok",
            cancel_url="https://example.test/cancel",
        )


def test_stripe_checkout_retains_session_id_and_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_x")
    fake_session = SimpleNamespace(id="cs_test_123", url="https://checkout.stripe.test/pay")
    fake_stripe = MagicMock()
    fake_stripe.checkout.Session.create.return_value = fake_session
    with patch.dict("sys.modules", {"stripe": fake_stripe}):
        result = StripeProvider().create_checkout(
            SimpleNamespace(
                id=9,
                currency="EUR",
                amount_minor=2500,
                purpose="deposit",
                organization_id=1,
                reservation_id=3,
            ),  # type: ignore[arg-type]
            success_url="https://app.test/secure/deposit?t=abc&status=return",
            cancel_url="https://app.test/secure/deposit?t=abc&status=cancel",
        )
    assert result.provider_ref == "cs_test_123"
    assert result.checkout_url == "https://checkout.stripe.test/pay"


def test_webhook_capture_confirms_stripe_deposit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_x")
    db = _session()
    reservation = _restaurant_setup(db)
    deposit = (reservation.allocation_json or {}).get("deposit") or {}
    # Replace provider with stripe after booking created a manual deposit.
    from app.db.models import PaymentIntent

    payment = db.get(PaymentIntent, int(deposit["payment_id"]))
    assert payment is not None
    payment.provider = "stripe"
    payment.provider_ref = "cs_old"
    payment.metadata_json = {
        **dict(payment.metadata_json or {}),
        "checkout_url": "https://checkout.stripe.test/pay",
    }
    db.commit()

    captured = capture_payment(db, payment.id, provider_ref="cs_test_webhook")
    assert captured.status == "captured"
    assert captured.provider_ref == "cs_test_webhook"
    db.refresh(reservation)
    assert reservation.status == "confirmed"


def test_get_provider_stripe() -> None:
    assert get_provider("stripe").name == "stripe"
