"""PHASE 8 — salon voice tools + restaurant waitlist/reservation modify."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.calendars.tools import voice_db, voice_user_id
from app.catalog.service import create_catalog_item
from app.db.base import Base
from app.db.models import (
    Location,
    Resource,
    ResourceCapability,
    ServiceResourceRequirement,
    User,
)
from app.industries.restaurant import list_dining_areas
from app.industries.service import assign_industry_profile, enabled_tools
from app.industries.waitlist import cancel_waitlist_entry, join_waitlist, promote_waitlist
from app.tenancy.service import create_organization_for_user
from app.voice.registry.core import get_tool_registry, reset_tool_registry_for_tests
from app.voice.registry.handlers_salon import book_salon_service
from app.voice.session import execute_function_call


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def setup_function() -> None:
    reset_tool_registry_for_tests()


def _org(db: Session, username: str = "phase8") -> tuple[User, object, Location]:
    user = User(username=username, email=f"{username}@example.test", password="unused")
    db.add(user)
    db.flush()
    organization = create_organization_for_user(db, user)
    location = Location(organization_id=organization.id, name="Main", timezone="UTC")
    db.add(location)
    db.flush()
    return user, organization, location


def test_salon_tools_registered_and_entitled() -> None:
    registry = get_tool_registry()
    for name in (
        "find_salon_services",
        "find_available_staff",
        "find_salon_availability",
        "estimate_service_price",
        "book_salon_service",
        "modify_salon_booking",
    ):
        assert registry.get(name) is not None

    db = _session()
    user, organization, _ = _org(db, "salon8")
    assign_industry_profile(db, organization_id=organization.id, industry_type="salon")
    db.commit()

    tools = enabled_tools(db, organization.id)
    assert "find_salon_services" in tools
    assert "book_salon_service" in tools
    assert "request_human_handoff" in tools
    assert "cancel_appointment" in tools

    entitled = {d.name for d in registry.enabled_definitions(db, user_id=user.id)}
    assert "book_salon_service" in entitled
    assert "estimate_service_price" in entitled
    assert "create_reservation" not in entitled


def test_restaurant_promote_and_modify_tools_entitled() -> None:
    registry = get_tool_registry()
    assert registry.get("promote_waitlist") is not None
    assert registry.get("modify_reservation") is not None

    db = _session()
    user, organization, _ = _org(db, "resto8")
    assign_industry_profile(db, organization_id=organization.id, industry_type="restaurant")
    db.commit()

    tools = enabled_tools(db, organization.id)
    assert "promote_waitlist" in tools
    assert "modify_reservation" in tools
    entitled = {d.name for d in registry.enabled_definitions(db, user_id=user.id)}
    assert "promote_waitlist" in entitled
    assert "modify_reservation" in entitled


def test_book_salon_service_voice_path() -> None:
    db = _session()
    user, organization, location = _org(db, "booksalon")
    assign_industry_profile(db, organization_id=organization.id, industry_type="salon")
    cut = create_catalog_item(
        db,
        organization_id=organization.id,
        name="Haircut",
        duration_minutes=30,
        bookable=True,
        kind="service",
    )
    stylist = Resource(
        organization_id=organization.id,
        location_id=location.id,
        resource_type="employee",
        name="Taylor",
        capacity=1,
    )
    chair = Resource(
        organization_id=organization.id,
        location_id=location.id,
        resource_type="chair",
        name="Chair 1",
        capacity=1,
    )
    db.add_all((cut, stylist, chair))
    db.flush()
    db.add(ResourceCapability(resource_id=stylist.id, capability="CUTTING"))
    db.add_all(
        (
            ServiceResourceRequirement(
                catalog_item_id=cut.id,
                resource_type="employee",
                capability="CUTTING",
                quantity=1,
                required=True,
            ),
            ServiceResourceRequirement(
                catalog_item_id=cut.id,
                resource_type="chair",
                quantity=1,
                required=True,
            ),
        )
    )
    db.commit()

    token_db = voice_db.set(db)
    token_user = voice_user_id.set(user.id)
    try:
        denied = book_salon_service(
            catalog_item_id=cut.id,
            datetime_start="2030-05-01T10:00:00+00:00",
            preferred_staff_id=stylist.id,
            location_id=location.id,
            confirmed=False,
        )
        assert denied["needs_confirmation"] is True

        booked = book_salon_service(
            catalog_item_id=cut.id,
            datetime_start="2030-05-01T10:00:00+00:00",
            preferred_staff_id=stylist.id,
            required_capability="CUTTING",
            location_id=location.id,
            client_name="Ada",
            client_phone="+15551212",
            confirmed=True,
        )
        assert booked["success"] is True
        assert booked["reservation_id"] is not None
        assert booked["start"].startswith("2030-05-01T10:00:00")
    finally:
        voice_user_id.reset(token_user)
        voice_db.reset(token_db)


def test_waitlist_promote_and_cancel() -> None:
    db = _session()
    _, organization, location = _org(db, "wait8")
    entry = join_waitlist(
        db,
        organization_id=organization.id,
        location_id=location.id,
        party_size=2,
    )
    db.commit()
    promoted = promote_waitlist(db, entry.id, organization_id=organization.id, actor_user_id=1)
    db.commit()
    assert promoted.status == "promoted"
    assert "promoted_at" in (promoted.metadata_json or {})

    entry2 = join_waitlist(db, organization_id=organization.id, party_size=1)
    db.flush()
    cancelled = cancel_waitlist_entry(db, entry2.id, organization_id=organization.id)
    db.commit()
    assert cancelled.status == "cancelled"


def test_list_dining_areas_soft_helper() -> None:
    db = _session()
    _, organization, location = _org(db, "dining8")
    table = Resource(
        organization_id=organization.id,
        location_id=location.id,
        resource_type="table",
        name="T1",
        capacity=4,
    )
    pool = Resource(
        organization_id=organization.id,
        location_id=location.id,
        resource_type="capacity_pool",
        name="Patio",
        capacity=20,
    )
    employee = Resource(
        organization_id=organization.id,
        location_id=location.id,
        resource_type="employee",
        name="Server",
        capacity=1,
    )
    db.add_all((table, pool, employee))
    db.commit()
    areas = list_dining_areas(db, organization.id, location_id=location.id)
    names = {row.name for row in areas}
    assert names == {"T1", "Patio"}


def test_execute_book_salon_requires_entitlement() -> None:
    db = _session()
    user, organization, _ = _org(db, "deny8")
    assign_industry_profile(db, organization_id=organization.id, industry_type="restaurant")
    db.commit()

    token_db = voice_db.set(db)
    token_user = voice_user_id.set(user.id)
    try:
        result = execute_function_call(
            "book_salon_service",
            {
                "catalog_item_id": 1,
                "datetime_start": datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat(),
                "confirmed": True,
            },
        )
        assert result.get("error") == "tool_not_entitled"
    finally:
        voice_user_id.reset(token_user)
        voice_db.reset(token_db)
