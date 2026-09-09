"""Table adjacency graphs + combo allocation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.service import create_catalog_item
from app.db.base import Base
from app.db.models import (
    Location,
    ReservationResource,
    Resource,
    ResourceAdjacency,
    ServiceResourceRequirement,
    User,
)
from app.reservations.service import ReservationConflictError, book_reservation
from app.tenancy.service import create_organization_for_user


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(db: Session) -> tuple[object, Location, object, Resource, Resource]:
    user = User(username="combo", email="combo@example.test", password="unused")
    db.add(user)
    db.flush()
    organization = create_organization_for_user(db, user)
    location = Location(organization_id=organization.id, name="Main", timezone="UTC")
    dinner = create_catalog_item(
        db,
        organization_id=organization.id,
        name="Dinner",
        duration_minutes=90,
        bookable=True,
    )
    t1 = Resource(
        organization_id=organization.id,
        location_id=location.id,
        resource_type="table",
        name="T1",
        capacity=4,
    )
    t2 = Resource(
        organization_id=organization.id,
        location_id=location.id,
        resource_type="table",
        name="T2",
        capacity=4,
    )
    db.add_all((location, dinner, t1, t2))
    db.flush()
    db.add(
        ServiceResourceRequirement(
            catalog_item_id=dinner.id,
            resource_type="table",
            quantity=1,
            required=True,
        )
    )
    a_id, b_id = (t1.id, t2.id) if t1.id < t2.id else (t2.id, t1.id)
    db.add(
        ResourceAdjacency(
            organization_id=organization.id,
            resource_a_id=a_id,
            resource_b_id=b_id,
            active=True,
        )
    )
    db.commit()
    return organization, location, dinner, t1, t2


def test_party_of_six_books_two_adjacent_four_tops() -> None:
    db = _session()
    organization, location, dinner, t1, t2 = _seed(db)
    start = datetime(2030, 6, 1, 19, 0, tzinfo=timezone.utc)

    reservation = book_reservation(
        db,
        organization_id=organization.id,
        catalog_item_id=dinner.id,
        location_id=location.id,
        start_datetime=start,
        party_size=6,
        scheduling_mode="capacity",
        sync_calendar=False,
    )
    assert reservation.status == "confirmed"
    assigned = {
        row.resource_id: row.quantity
        for row in db.scalars(
            select(ReservationResource).where(
                ReservationResource.reservation_id == reservation.id
            )
        ).all()
    }
    assert set(assigned) == {t1.id, t2.id}
    assert assigned[t1.id] == 4
    assert assigned[t2.id] == 4


def test_overlap_blocks_both_combined_tables() -> None:
    db = _session()
    organization, location, dinner, t1, t2 = _seed(db)
    start = datetime(2030, 6, 1, 19, 0, tzinfo=timezone.utc)

    book_reservation(
        db,
        organization_id=organization.id,
        catalog_item_id=dinner.id,
        location_id=location.id,
        start_datetime=start,
        party_size=6,
        scheduling_mode="capacity",
        sync_calendar=False,
        idempotency_key="first-combo",
    )

    with pytest.raises(ReservationConflictError):
        book_reservation(
            db,
            organization_id=organization.id,
            catalog_item_id=dinner.id,
            location_id=location.id,
            start_datetime=start,
            party_size=6,
            scheduling_mode="capacity",
            sync_calendar=False,
            idempotency_key="second-combo",
        )

    # A smaller party that would need either table alone is also blocked.
    with pytest.raises(ReservationConflictError):
        book_reservation(
            db,
            organization_id=organization.id,
            catalog_item_id=dinner.id,
            location_id=location.id,
            start_datetime=start,
            party_size=2,
            scheduling_mode="capacity",
            sync_calendar=False,
            idempotency_key="party-two",
        )
