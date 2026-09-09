"""PHASE 5 — generalized availability / reservation engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.service import create_catalog_item
from app.customers.service import get_or_create_customer
from app.db.base import Base
from app.db.models import (
    Appointment,
    AvailabilityRule,
    Location,
    Price,
    PriceBook,
    ReservationLineItem,
    ReservationResource,
    Resource,
    ResourceCapability,
    ServiceResourceRequirement,
    User,
)
from app.reservations.service import (
    ReservationConflictError,
    add_line_item,
    book_reservation,
    cancel_reservation,
    change_resource_assignment,
    commit_reservation,
    expire_stale_holds,
    find_availability,
    hold_reservation,
    remove_line_item,
    reschedule_reservation,
    update_line_item_quantity,
    update_party_size,
)
from app.reservations.types import AvailabilityRequest
from app.tenancy.service import create_organization_for_user


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_org(db: Session) -> tuple[User, object, Location]:
    user = User(username="phase5", email="phase5@example.test", password="unused")
    db.add(user)
    db.flush()
    organization = create_organization_for_user(db, user)
    location = Location(
        organization_id=organization.id,
        name="Main",
        timezone="UTC",
        business_hours={
            "monday": [{"start": "09:00", "end": "17:00"}],
            "tuesday": [{"start": "09:00", "end": "17:00"}],
            "wednesday": [{"start": "09:00", "end": "17:00"}],
            "thursday": [{"start": "09:00", "end": "17:00"}],
            "friday": [{"start": "09:00", "end": "17:00"}],
            "saturday": [{"start": "09:00", "end": "17:00"}],
            "sunday": [{"start": "09:00", "end": "17:00"}],
        },
    )
    db.add(location)
    db.flush()
    return user, organization, location


def test_single_resource_availability_and_booking() -> None:
    db = _session()
    user, organization, location = _seed_org(db)
    item = create_catalog_item(
        db,
        organization_id=organization.id,
        name="Haircut",
        duration_minutes=30,
        bookable=True,
    )
    chair = Resource(
        organization_id=organization.id,
        location_id=location.id,
        resource_type="chair",
        name="Chair 1",
        capacity=1,
    )
    db.add_all((item, chair))
    db.flush()
    db.add(
        ServiceResourceRequirement(
            catalog_item_id=item.id, resource_type="chair", quantity=1, required=True
        )
    )
    book = PriceBook(organization_id=organization.id, name="Standard", currency="EUR")
    db.add(book)
    db.flush()
    db.add(
        Price(
            price_book_id=book.id,
            catalog_item_id=item.id,
            amount_minor=2500,
            currency="EUR",
        )
    )
    start_day = datetime(2030, 1, 7, 0, 0, tzinfo=timezone.utc)  # Monday
    db.add(
        AvailabilityRule(
            organization_id=organization.id,
            location_id=location.id,
            weekday=0,
            start_time="09:00",
            end_time="17:00",
        )
    )
    db.commit()

    result = find_availability(
        db,
        AvailabilityRequest(
            organization_id=organization.id,
            catalog_item_id=item.id,
            location_id=location.id,
            start_date=start_day,
            end_date=start_day + timedelta(days=1),
            price_book_id=book.id,
        ),
    )
    assert result.slots
    slot = result.slots[0]
    assert slot.scheduling_mode == "single_resource"
    assert slot.allocations[0].resource_id == chair.id
    assert slot.price_estimate is not None
    assert slot.price_estimate.amount_minor == 2500

    reservation = book_reservation(
        db,
        organization_id=organization.id,
        catalog_item_id=item.id,
        location_id=location.id,
        start_datetime=slot.start_datetime,
        price_book_id=book.id,
        owner_user_id=user.id,
        sync_calendar=True,
    )
    assert reservation.status == "confirmed"
    assert reservation.appointment_id is not None
    assert reservation.scheduling_mode == "single_resource"
    resources = list(
        db.scalars(
            select(ReservationResource).where(
                ReservationResource.reservation_id == reservation.id
            )
        ).all()
    )
    assert len(resources) == 1
    lines = list(
        db.scalars(
            select(ReservationLineItem).where(
                ReservationLineItem.reservation_id == reservation.id
            )
        ).all()
    )
    assert len(lines) == 1
    assert lines[0].unit_price_minor == 2500

    try:
        book_reservation(
            db,
            organization_id=organization.id,
            catalog_item_id=item.id,
            location_id=location.id,
            start_datetime=slot.start_datetime,
            price_book_id=book.id,
            idempotency_key="other-key",
        )
        raised = False
    except ReservationConflictError:
        raised = True
    assert raised


def test_multi_resource_and_capacity_modes() -> None:
    db = _session()
    user, organization, location = _seed_org(db)
    coloring = create_catalog_item(
        db,
        organization_id=organization.id,
        name="Hair coloring",
        duration_minutes=90,
        bookable=True,
        buffer_after_minutes=10,
    )
    staff = Resource(
        organization_id=organization.id,
        location_id=location.id,
        resource_type="employee",
        name="Alex",
        capacity=1,
    )
    chair = Resource(
        organization_id=organization.id,
        location_id=location.id,
        resource_type="chair",
        name="Chair A",
        capacity=1,
    )
    pool = Resource(
        organization_id=organization.id,
        location_id=location.id,
        resource_type="capacity_pool",
        name="Dining",
        capacity=10,
    )
    db.add_all((coloring, staff, chair, pool))
    db.flush()
    db.add(ResourceCapability(resource_id=staff.id, capability="COLORING"))
    db.add_all(
        (
            ServiceResourceRequirement(
                catalog_item_id=coloring.id,
                resource_type="employee",
                capability="COLORING",
                quantity=1,
                required=True,
            ),
            ServiceResourceRequirement(
                catalog_item_id=coloring.id,
                resource_type="chair",
                quantity=1,
                required=True,
            ),
        )
    )
    dinner = create_catalog_item(
        db,
        organization_id=organization.id,
        name="Dinner",
        duration_minutes=90,
        bookable=True,
    )
    db.add(dinner)
    db.flush()
    db.add(
        ServiceResourceRequirement(
            catalog_item_id=dinner.id,
            resource_type="capacity_pool",
            quantity=1,
            required=True,
        )
    )
    start = datetime(2030, 1, 7, 10, 0, tzinfo=timezone.utc)
    db.commit()

    multi = book_reservation(
        db,
        organization_id=organization.id,
        catalog_item_id=coloring.id,
        location_id=location.id,
        start_datetime=start,
        required_capabilities=("COLORING",),
    )
    assert multi.scheduling_mode == "multi_resource"
    assert len(multi.allocation_json["resources"]) == 2

    capacity = book_reservation(
        db,
        organization_id=organization.id,
        catalog_item_id=dinner.id,
        location_id=location.id,
        start_datetime=start,
        party_size=4,
        scheduling_mode="capacity",
    )
    assert capacity.scheduling_mode == "capacity"
    assert capacity.allocation_json["resources"][0]["quantity"] == 4

    try:
        book_reservation(
            db,
            organization_id=organization.id,
            catalog_item_id=dinner.id,
            location_id=location.id,
            start_datetime=start,
            party_size=7,
            scheduling_mode="capacity",
            idempotency_key="too-big",
        )
        ok = True
    except ReservationConflictError:
        ok = False
    assert ok is False


def test_hold_expiry_releases_capacity() -> None:
    db = _session()
    _, organization, location = _seed_org(db)
    item = create_catalog_item(
        db,
        organization_id=organization.id,
        name="Consult",
        duration_minutes=30,
        bookable=True,
    )
    room = Resource(
        organization_id=organization.id,
        location_id=location.id,
        resource_type="room",
        name="Room 1",
        capacity=1,
    )
    db.add_all((item, room))
    db.flush()
    db.add(
        ServiceResourceRequirement(
            catalog_item_id=item.id, resource_type="room", quantity=1, required=True
        )
    )
    start = datetime(2030, 1, 8, 11, 0, tzinfo=timezone.utc)
    db.commit()

    held = hold_reservation(
        db,
        organization_id=organization.id,
        catalog_item_id=item.id,
        location_id=location.id,
        start_datetime=start,
        hold_ttl_seconds=1,
    )
    assert held.status == "held"
    held.hold_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    expired = expire_stale_holds(db)
    assert expired == 1

    booked = book_reservation(
        db,
        organization_id=organization.id,
        catalog_item_id=item.id,
        location_id=location.id,
        start_datetime=start,
        idempotency_key="after-expire",
    )
    assert booked.status == "confirmed"


def test_commit_verifies_hold_and_snapshots_once() -> None:
    db = _session()
    user, organization, location = _seed_org(db)
    item = create_catalog_item(
        db,
        organization_id=organization.id,
        name="Therapy",
        duration_minutes=45,
        bookable=True,
    )
    practitioner = Resource(
        organization_id=organization.id,
        location_id=location.id,
        resource_type="practitioner",
        name="Dr Lee",
        capacity=1,
    )
    customer = get_or_create_customer(
        db, organization_id=organization.id, name="Pat", phone="+15551212"
    )
    db.add_all((item, practitioner))
    db.flush()
    db.add(
        ServiceResourceRequirement(
            catalog_item_id=item.id,
            resource_type="practitioner",
            quantity=1,
            required=True,
        )
    )
    book = PriceBook(organization_id=organization.id, name="Clinic", currency="USD")
    db.add(book)
    db.flush()
    db.add(
        Price(
            price_book_id=book.id,
            catalog_item_id=item.id,
            amount_minor=9000,
            currency="USD",
            tax_metadata={"rate": "0"},
        )
    )
    start = datetime(2030, 2, 4, 13, 0, tzinfo=timezone.utc)
    db.commit()

    held = hold_reservation(
        db,
        organization_id=organization.id,
        catalog_item_id=item.id,
        location_id=location.id,
        customer_id=customer.id,
        start_datetime=start,
        price_book_id=book.id,
    )
    assert held.status == "held"
    lines_before = len(
        list(
            db.scalars(
                select(ReservationLineItem).where(
                    ReservationLineItem.reservation_id == held.id
                )
            ).all()
        )
    )
    assert lines_before == 1

    committed = commit_reservation(
        db, held.id, owner_user_id=user.id, sync_calendar=True
    )
    assert committed.status == "confirmed"
    assert committed.appointment_id is not None
    assert committed.hold_expires_at is None
    again = commit_reservation(db, held.id, owner_user_id=user.id, sync_calendar=True)
    assert again.id == committed.id
    assert again.status == "confirmed"


def test_reservation_lifecycle_mutations_are_idempotent() -> None:
    db = _session()
    user, organization, location = _seed_org(db)
    dinner = create_catalog_item(
        db,
        organization_id=organization.id,
        name="Dinner",
        duration_minutes=60,
        bookable=True,
    )
    dessert = create_catalog_item(
        db,
        organization_id=organization.id,
        name="Dessert",
        duration_minutes=15,
        bookable=True,
    )
    first_table = Resource(
        organization_id=organization.id,
        location_id=location.id,
        resource_type="capacity_pool",
        name="Main dining room",
        capacity=4,
    )
    second_table = Resource(
        organization_id=organization.id,
        location_id=location.id,
        resource_type="capacity_pool",
        name="Patio",
        capacity=4,
    )
    db.add_all((dinner, dessert, first_table, second_table))
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
    db.add_all(
        (
            Price(
                price_book_id=book.id,
                catalog_item_id=dinner.id,
                amount_minor=2500,
                currency="EUR",
            ),
            Price(
                price_book_id=book.id,
                catalog_item_id=dessert.id,
                amount_minor=700,
                currency="EUR",
            ),
        )
    )
    db.commit()

    reservation = book_reservation(
        db,
        organization_id=organization.id,
        catalog_item_id=dinner.id,
        location_id=location.id,
        start_datetime=datetime(2030, 1, 8, 12, 0, tzinfo=timezone.utc),
        party_size=1,
        scheduling_mode="capacity",
        price_book_id=book.id,
        owner_user_id=user.id,
        sync_calendar=True,
    )
    resized = update_party_size(
        db, reservation.id, party_size=2, idempotency_key="party-2"
    )
    assert resized.party_size == 2
    moved = reschedule_reservation(
        db,
        reservation.id,
        start_datetime=datetime(2030, 1, 8, 14, 0, tzinfo=timezone.utc),
        idempotency_key="move-14",
    )
    assert moved.start_datetime.hour == 14
    assigned = change_resource_assignment(
        db,
        reservation.id,
        resource_ids=(second_table.id,),
        idempotency_key="patio",
    )
    assert assigned.allocation_json["resources"][0]["resource_id"] == second_table.id
    addon = add_line_item(
        db,
        reservation.id,
        catalog_item_id=dessert.id,
        price_book_id=book.id,
        idempotency_key="dessert",
    )
    assert addon.unit_price_minor == 700
    updated_addon = update_line_item_quantity(
        db, reservation.id, line_item_id=addon.id, quantity=2, idempotency_key="dessert-2"
    )
    assert updated_addon.id == reservation.id
    assert db.get(ReservationLineItem, addon.id).quantity == 2  # type: ignore[union-attr]
    remove_line_item(db, reservation.id, line_item_id=addon.id, idempotency_key="no-dessert")
    cancelled = cancel_reservation(db, reservation.id, idempotency_key="cancel")
    retried = cancel_reservation(db, reservation.id, idempotency_key="cancel")
    assert cancelled.status == retried.status == "cancelled"
    appointment = db.get(Appointment, reservation.appointment_id)
    assert appointment is not None
    assert appointment.status == "cancelled"
