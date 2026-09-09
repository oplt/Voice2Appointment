"""Focused contracts for the organization-scoped product HTTP surface."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.api import (
    CategoryIn,
    ItemIn,
    create_category,
    create_item,
)
from app.catalog.api import (
    router as catalog_router,
)
from app.customers.api import (
    CustomerIn,
    create_customer,
    list_customers,
)
from app.customers.api import (
    router as customers_router,
)
from app.db.base import Base
from app.db.models import Organization, User
from app.industries.api import KnowledgeIn, create_knowledge
from app.industries.api import router as industries_router
from app.pricing.api import router as pricing_router
from app.reservations.api import router as reservations_router
from app.resources.api import ResourceIn, create_resource
from app.resources.api import router as resources_router
from app.tenancy.api import LocationIn, create_location
from app.tenancy.api import router as tenancy_router


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _paths(router: object) -> set[str]:
    return {route.path for route in router.routes}  # type: ignore[attr-defined]


def test_product_routers_are_registered_with_required_contracts() -> None:
    assert "/locations" in _paths(tenancy_router)
    assert "/catalog/items" in _paths(catalog_router)
    assert "/price-books" in _paths(pricing_router)
    assert "/resources" in _paths(resources_router)
    assert "/customers" in _paths(customers_router)
    assert "/availability" in _paths(reservations_router)
    assert "/reservations" in _paths(reservations_router)
    assert "/knowledge" in _paths(industries_router)
    assert "/industry-profile" in _paths(industries_router)


def test_product_mutations_and_queries_are_organization_scoped() -> None:
    db = _session()
    first = Organization(name="First", slug="first")
    second = Organization(name="Second", slug="second")
    user = User(username="product-api", email="product-api@example.test", password="unused")
    db.add_all((first, second, user))
    db.flush()
    user.organization_id = first.id
    db.commit()

    location = create_location(LocationIn(name="Main"), organization_id=first.id, db=db)
    category = create_category(CategoryIn(name="Services"), organization_id=first.id, db=db)
    item = create_item(
        ItemIn(name="Consultation", category_id=category.id, duration_minutes=30, bookable=True),
        organization_id=first.id,
        db=db,
    )
    resource = create_resource(
        ResourceIn(name="Room 1", resource_type="room", location_id=location.id),
        organization_id=first.id,
        db=db,
    )
    customer = create_customer(
        CustomerIn(name="Pat", phone="+15550001"), organization_id=first.id, db=db
    )
    knowledge = create_knowledge(
        KnowledgeIn(title="Hours", content="Weekdays"), organization_id=first.id, db=db
    )

    assert item.organization_id == resource.organization_id == customer.organization_id == first.id
    assert knowledge.organization_id == first.id
    assert list_customers(organization_id=second.id, query=None, db=db) == []
