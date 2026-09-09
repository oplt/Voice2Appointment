"""Reservation lifecycle mutations stage notification intents."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.service import create_catalog_item
from app.db.base import Base
from app.db.models import (
    Appointment,
    Location,
    NotificationDelivery,
    Price,
    PriceBook,
    Resource,
    ServiceResourceRequirement,
    User,
)
from app.reservations.service import book_reservation, update_party_size
from app.tenancy.service import create_organization_for_user


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_party_size_change_stages_lifecycle_notification() -> None:
    db = _session()
    user = User(username="notify", email="notify@example.test", password="x")
    db.add(user)
    db.flush()
    organization = create_organization_for_user(db, user)
    location = Location(
        organization_id=organization.id,
        name="Main",
        timezone="UTC",
        business_hours={
            day: [{"start": "09:00", "end": "17:00"}]
            for day in (
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            )
        },
    )
    dinner = create_catalog_item(
        db,
        organization_id=organization.id,
        name="Dinner",
        duration_minutes=60,
        bookable=True,
    )
    table = Resource(
        organization_id=organization.id,
        location_id=location.id,
        resource_type="capacity_pool",
        name="Hall",
        capacity=4,
    )
    db.add_all((location, dinner, table))
    db.flush()
    db.add(
        ServiceResourceRequirement(
            catalog_item_id=dinner.id,
            resource_type="capacity_pool",
            quantity=1,
            required=True,
        )
    )
    book = PriceBook(organization_id=organization.id, name="Menu", currency="EUR")
    db.add(book)
    db.flush()
    db.add(
        Price(
            price_book_id=book.id,
            catalog_item_id=dinner.id,
            amount_minor=2500,
            currency="EUR",
        )
    )
    db.commit()

    reservation = book_reservation(
        db,
        organization_id=organization.id,
        catalog_item_id=dinner.id,
        location_id=location.id,
        start_datetime=datetime(2030, 2, 1, 12, 0, tzinfo=timezone.utc),
        party_size=1,
        scheduling_mode="capacity",
        price_book_id=book.id,
        owner_user_id=user.id,
        sync_calendar=True,
    )
    assert reservation.appointment_id is not None
    appointment = db.get(Appointment, reservation.appointment_id)
    assert appointment is not None

    update_party_size(db, reservation.id, party_size=2, idempotency_key="party-notify")
    update_party_size(db, reservation.id, party_size=2, idempotency_key="party-notify")

    rows = list(
        db.scalars(
            select(NotificationDelivery).where(
                NotificationDelivery.appointment_id == appointment.id
            )
        ).all()
    )
    lifecycle = [row for row in rows if row.idempotency_key.startswith("lc:party_size:")]
    assert len(lifecycle) == 1
