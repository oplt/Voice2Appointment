"""Customer phone/email normalization and concurrency-safe dedup."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.customers.service import (
    find_customer,
    get_or_create_customer,
    merge_customers,
    normalize_email,
    normalize_phone,
)
from app.db.base import Base
from app.db.models import (
    Customer,
    Order,
    PaymentIntent,
    Reservation,
    SecureLinkDelivery,
    User,
    WaitlistEntry,
)
from app.tenancy.service import create_organization_for_user


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_normalize_phone_and_email() -> None:
    assert normalize_phone("+1 (555) 010-0200") == "+15550100200"
    assert normalize_email("  Pat@Example.COM ") == "pat@example.com"
    assert normalize_phone("not-a-phone") is None
    assert normalize_phone("0470 12 34 56") is None


def test_get_or_create_dedupes_normalized_phone() -> None:
    db = _session()
    user = User(username="cust", email="cust@example.test", password="x")
    db.add(user)
    db.flush()
    org = create_organization_for_user(db, user)
    db.commit()

    first = get_or_create_customer(
        db, organization_id=org.id, name="Pat", phone="+1 555 010-0200"
    )
    db.commit()
    second = get_or_create_customer(
        db, organization_id=org.id, name="Patricia", phone="+1 555 010-0200"
    )
    db.commit()
    assert first.id == second.id
    assert db.scalar(select(func.count()).select_from(Customer)) == 1


def test_concurrent_creates_same_phone_yield_one_customer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate a lost race: lookup misses, insert hits unique constraint, retry finds row."""
    db = _session()
    user = User(username="race", email="race@example.test", password="x")
    db.add(user)
    db.flush()
    org = create_organization_for_user(db, user)
    first = get_or_create_customer(
        db, organization_id=org.id, name="Pat", phone="+15550100200"
    )
    db.commit()

    calls = {"n": 0}
    real_find = find_customer

    def flaky_find(*args: object, **kwargs: object) -> Customer | None:
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return real_find(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("app.customers.service.find_customer", flaky_find)
    second = get_or_create_customer(
        db, organization_id=org.id, name="Pat", phone="+15550100200"
    )
    db.commit()
    assert second.id == first.id
    assert db.scalar(select(func.count()).select_from(Customer)) == 1
    assert calls["n"] >= 2


def test_merge_reassigns_customer_references() -> None:
    db = _session()
    user = User(username="merge", email="merge@example.test", password="x")
    db.add(user)
    db.flush()
    org = create_organization_for_user(db, user)
    source = get_or_create_customer(
        db, organization_id=org.id, name="A", phone="+15550100001"
    )
    target = get_or_create_customer(
        db, organization_id=org.id, name="B", phone="+15550100002"
    )
    db.flush()
    from datetime import datetime, timezone

    reservation = Reservation(
        organization_id=org.id,
        customer_id=source.id,
        scheduling_mode="single_resource",
        status="confirmed",
        start_datetime=datetime(2030, 1, 1, 12, tzinfo=timezone.utc),
        end_datetime=datetime(2030, 1, 1, 13, tzinfo=timezone.utc),
        party_size=1,
        provider_sync_status="none",
        allocation_json={},
    )
    db.add(reservation)
    db.flush()
    db.add_all(
        (
            Order(organization_id=org.id, external_id="order-1", status="open", customer_id=source.id),
            SecureLinkDelivery(
                organization_id=org.id,
                customer_id=source.id,
                channel="sms",
                recipient="+15550100001",
                token_hash="hash-1",
                token_ciphertext="ciphertext",
                expires_at=datetime(2030, 1, 2, tzinfo=timezone.utc),
                idempotency_key="link-1",
            ),
            PaymentIntent(
                organization_id=org.id,
                reservation_id=reservation.id,
                customer_id=source.id,
                amount_minor=100,
                currency="EUR",
            ),
            WaitlistEntry(organization_id=org.id, customer_id=source.id),
        )
    )
    db.commit()
    merged = merge_customers(
        db,
        organization_id=org.id,
        source_customer_id=source.id,
        target_customer_id=target.id,
    )
    db.commit()
    assert merged.id == target.id
    assert db.get(Customer, source.id) is None
    for model in (Reservation, Order, SecureLinkDelivery, PaymentIntent, WaitlistEntry):
        row = db.scalar(select(model))
        assert row is not None
        assert row.customer_id == target.id
