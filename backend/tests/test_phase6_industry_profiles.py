"""PHASE 6 — industry capability/policy profiles."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.service import create_catalog_item
from app.customers.service import get_or_create_customer
from app.db.base import Base
from app.db.models import (
    CatalogCategory,
    FeatureEntitlement,
    KnowledgeEntry,
    Location,
    Price,
    PriceBook,
    Resource,
    ResourceCapability,
    ServiceResourceRequirement,
    User,
)
from app.industries.clinic import (
    ClinicSafetyError,
    emergency_safety_gate,
    list_practitioners,
    list_visit_types,
    redact_clinic_payload,
    requires_referral,
)
from app.industries.ehr import NullEHRAdapter, set_ehr_adapter
from app.industries.general import answer_faq, get_price, search_catalog, take_message
from app.industries.restaurant import book_restaurant_reservation
from app.industries.salon import book_salon_appointment, list_addons, service_duration_with_addons
from app.industries.service import (
    assign_industry_profile,
    enabled_tools,
    has_capability,
    sync_calendar_for_org,
    tool_enabled,
    validate_booking_fields,
    validate_customer_fields,
)
from app.tenancy.service import create_organization_for_user


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _org(db: Session, username: str = "phase6") -> tuple[User, object, Location]:
    user = User(username=username, email=f"{username}@example.test", password="unused")
    db.add(user)
    db.flush()
    organization = create_organization_for_user(db, user)
    location = Location(organization_id=organization.id, name="Main", timezone="UTC")
    db.add(location)
    db.flush()
    return user, organization, location


def test_assign_profiles_seed_tools_and_capabilities() -> None:
    db = _session()
    _, organization, _ = _org(db)
    profile = assign_industry_profile(
        db, organization_id=organization.id, industry_type="clinic"
    )
    db.commit()
    assert profile.industry_type == "clinic"
    assert profile.scheduling_mode == "multi_resource"
    assert "emergency_safety_gate" in profile.flow_steps
    assert tool_enabled(db, organization.id, "create_appointment")
    assert has_capability(db, organization.id, "ehr_port")
    assert "find_practitioners" in enabled_tools(db, organization.id)
    entitlements = list(
        db.scalars(
            select(FeatureEntitlement).where(
                FeatureEntitlement.organization_id == organization.id,
                FeatureEntitlement.enabled.is_(True),
            )
        ).all()
    )
    assert any(row.feature == "industry:clinic" for row in entitlements)


def test_clinic_safety_gate_and_privacy() -> None:
    assert emergency_safety_gate("I'd like to book a checkup")["allowed"] is True
    emergency = emergency_safety_gate("I have chest pain")
    assert emergency["allowed"] is False
    assert emergency["action"] == "request_human_handoff"
    try:
        emergency_safety_gate("Can you diagnose my rash?")
        raised = False
    except ClinicSafetyError:
        raised = True
    assert raised
    redacted = redact_clinic_payload(
        {"client_name": "Ada", "diagnosis": "secret", "visit_type": "checkup"}
    )
    assert "diagnosis" not in redacted
    assert redacted["visit_type"] == "checkup"
    assert isinstance(NullEHRAdapter().lookup_patient(
        organization_id=1, phone=None, email=None
    ), type(None))
    set_ehr_adapter(NullEHRAdapter())


def test_clinic_visit_types_and_practitioners() -> None:
    db = _session()
    _, organization, location = _org(db, "clinic")
    assign_industry_profile(db, organization_id=organization.id, industry_type="clinic")
    category = CatalogCategory(organization_id=organization.id, name="Dermatology")
    db.add(category)
    db.flush()
    visit = create_catalog_item(
        db,
        organization_id=organization.id,
        name="New patient derm",
        duration_minutes=30,
        bookable=True,
        category_id=category.id,
        metadata_json={"specialty": "Dermatology", "requires_referral": True},
    )
    practitioner = Resource(
        organization_id=organization.id,
        location_id=location.id,
        resource_type="practitioner",
        name="Dr Kim",
        capacity=1,
    )
    db.add_all((visit, practitioner))
    db.flush()
    db.add(ResourceCapability(resource_id=practitioner.id, capability="DERM"))
    db.commit()

    assert requires_referral(visit)
    assert list_visit_types(db, organization.id, specialty="Dermatology")[0].id == visit.id
    assert list_practitioners(db, organization.id, capability="DERM")[0].id == practitioner.id
    missing = validate_customer_fields(db, organization.id, {"name": "Ada"})
    assert "phone" in missing


def test_restaurant_uses_capacity_not_calendar() -> None:
    db = _session()
    _, organization, location = _org(db, "resto")
    assign_industry_profile(db, organization_id=organization.id, industry_type="restaurant")
    assert sync_calendar_for_org(db, organization.id) is False
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
        name="Main floor",
        capacity=8,
    )
    db.add_all((dinner, pool))
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
        db, organization_id=organization.id, name="Sam", phone="+15550001"
    )
    db.commit()
    start = datetime(2030, 3, 1, 19, 0, tzinfo=timezone.utc)
    reservation = book_restaurant_reservation(
        db,
        organization_id=organization.id,
        catalog_item_id=dinner.id,
        start_datetime=start,
        party_size=4,
        location_id=location.id,
        customer_id=customer.id,
        seating_preference="window",
        dietary_notes="vegan",
    )
    assert reservation.scheduling_mode == "capacity"
    assert reservation.appointment_id is None
    assert reservation.allocation_json["guest_preferences"]["seating_preference"] == "window"
    assert reservation.provider_sync_status == "none"
    assert validate_booking_fields(
        db, organization.id, {"date": "2030-03-01", "time": "19:00", "party_size": 4}
    ) == ["location"]


def test_salon_addons_and_skills() -> None:
    db = _session()
    user, organization, location = _org(db, "salon")
    assign_industry_profile(db, organization_id=organization.id, industry_type="salon")
    cut = create_catalog_item(
        db,
        organization_id=organization.id,
        name="Haircut",
        duration_minutes=30,
        bookable=True,
    )
    blowout = create_catalog_item(
        db,
        organization_id=organization.id,
        name="Blowout",
        kind="addon",
        duration_minutes=15,
        bookable=False,
        metadata_json={"parent_catalog_item_id": None},
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
    db.add_all((cut, blowout, stylist, chair))
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
    book = PriceBook(organization_id=organization.id, name="Salon", currency="EUR")
    db.add(book)
    db.flush()
    db.add_all(
        (
            Price(price_book_id=book.id, catalog_item_id=cut.id, amount_minor=3000, currency="EUR"),
            Price(
                price_book_id=book.id, catalog_item_id=blowout.id, amount_minor=1000, currency="EUR"
            ),
        )
    )
    db.commit()

    assert service_duration_with_addons(cut, [blowout]) == 45
    assert list_addons(db, organization.id)[0].id == blowout.id
    start = datetime(2030, 4, 2, 11, 0, tzinfo=timezone.utc)
    reservation = book_salon_appointment(
        db,
        organization_id=organization.id,
        catalog_item_id=cut.id,
        start_datetime=start,
        addon_item_ids=(blowout.id,),
        preferred_staff_id=stylist.id,
        required_capabilities=("CUTTING",),
        location_id=location.id,
        price_book_id=book.id,
        owner_user_id=user.id,
        sync_calendar=False,
    )
    assert reservation.scheduling_mode == "multi_resource"
    assert reservation.end_datetime - reservation.start_datetime
    from datetime import timedelta

    assert reservation.end_datetime - reservation.start_datetime == timedelta(minutes=45)
    assert reservation.allocation_json["addons"][0]["name"] == "Blowout"


def test_general_company_capabilities() -> None:
    db = _session()
    _, organization, _ = _org(db, "general")
    assign_industry_profile(db, organization_id=organization.id, industry_type="general")
    item = create_catalog_item(
        db,
        organization_id=organization.id,
        name="Widget",
        kind="product",
        sellable=True,
    )
    book = PriceBook(organization_id=organization.id, name="List", currency="USD")
    db.add_all((item, book))
    db.flush()
    db.add(
        Price(price_book_id=book.id, catalog_item_id=item.id, amount_minor=499, currency="USD")
    )
    db.add(
        KnowledgeEntry(
            organization_id=organization.id,
            title="Shipping FAQ",
            content="We ship worldwide within 5 days.",
        )
    )
    db.commit()

    assert has_capability(db, organization.id, "answer_faq")
    assert tool_enabled(db, organization.id, "take_message")
    assert search_catalog(db, organization.id, query="widget")[0].id == item.id
    assert get_price(db, organization_id=organization.id, catalog_item_id=item.id).amount_minor == 499
    assert answer_faq(db, organization.id, query="shipping")[0].title == "Shipping FAQ"
    message = take_message(
        db, organization_id=organization.id, message="Call me back", customer_name="Lee"
    )
    assert message.action == "take_message"
