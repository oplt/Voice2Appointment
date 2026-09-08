from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.appointments.booking import book_appointment
from app.catalog.service import create_catalog_item
from app.customers.service import get_or_create_customer
from app.db.base import Base
from app.db.models import Price, PriceBook, User
from app.pricing.service import snapshot_line_item
from app.tenancy.service import create_organization_for_user


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_catalog_service_duration_overrides_legacy_policy(monkeypatch) -> None:
    db = _session()
    user = User(username="phase4", email="phase4@example.test", password="unused")
    db.add(user)
    db.flush()
    organization = create_organization_for_user(db, user)
    item = create_catalog_item(
        db,
        organization_id=organization.id,
        name="Extended consultation",
        duration_minutes=45,
        bookable=True,
    )
    db.add(item)
    db.commit()
    monkeypatch.setattr("app.notifications.service.enqueue_confirmation", lambda *_args: None)

    start = datetime.now(timezone.utc) + timedelta(days=2)
    appointment = book_appointment(
        db,
        user.id,
        summary="Extended consultation",
        start_datetime=start,
    )

    assert appointment.organization_id == organization.id
    assert appointment.end_datetime - appointment.start_datetime == timedelta(minutes=45)


def test_customer_and_reservation_price_snapshot_are_organization_scoped() -> None:
    db = _session()
    user = User(username="pricing", email="pricing@example.test", password="unused")
    db.add(user)
    db.flush()
    organization = create_organization_for_user(db, user)
    item = create_catalog_item(
        db,
        organization_id=organization.id,
        name="Service",
        duration_minutes=30,
        bookable=True,
    )
    book = PriceBook(organization_id=organization.id, name="Standard", currency="EUR")
    db.add_all((item, book))
    db.flush()
    price = Price(
        price_book_id=book.id,
        catalog_item_id=item.id,
        amount_minor=1250,
        currency="EUR",
        tax_metadata={"rate": "21"},
    )
    customer = get_or_create_customer(
        db, organization_id=organization.id, name="Ada", email="ada@example.test"
    )
    db.add(price)
    db.flush()

    line = snapshot_line_item(reservation_id=99, item=item, price=price, quantity=2)

    assert customer.organization_id == organization.id
    assert line.item_name == "Service"
    assert line.unit_price_minor == 1250
    assert line.currency == "EUR"
    assert line.tax_metadata == {"rate": "21"}
