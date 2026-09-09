"""Catalog management service contracts."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.service import (
    CatalogConflictError,
    archive_catalog_item,
    bulk_set_catalog_items_active,
    create_catalog_item,
    create_option,
    duplicate_catalog_item,
    list_catalog_items,
    update_catalog_item,
)
from app.db.base import Base
from app.db.models import CatalogCategory, Organization
from app.resources.service import replace_service_requirements, requirements_for_service


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_catalog_lifecycle_uses_atomic_versions_and_copies_options() -> None:
    db = _session()
    organization = Organization(name="Catalog", slug="catalog-management")
    db.add(organization)
    db.flush()
    category = CatalogCategory(organization_id=organization.id, name="Services")
    db.add(category)
    db.flush()
    item = create_catalog_item(
        db,
        organization_id=organization.id,
        category_id=category.id,
        name="Consultation",
        duration_minutes=30,
        bookable=True,
    )
    db.add(item)
    db.flush()
    option = create_option(db, item=item, name="Extended notes", active=True, metadata_json={})
    db.add(option)
    db.commit()
    db.refresh(item)

    updated = update_catalog_item(
        db,
        organization_id=organization.id,
        item_id=item.id,
        expected_version=item.version,
        fields={"name": "Initial consultation"},
    )
    db.commit()
    db.refresh(updated)
    assert updated.version == 2
    with pytest.raises(CatalogConflictError):
        update_catalog_item(
            db,
            organization_id=organization.id,
            item_id=item.id,
            expected_version=1,
            fields={"name": "Stale update"},
        )
    db.rollback()

    duplicate = duplicate_catalog_item(db, organization_id=organization.id, item_id=item.id)
    db.commit()
    db.refresh(duplicate)
    assert duplicate.active is False
    assert duplicate.bookable is False
    assert duplicate.name == "Initial consultation (copy)"

    archived = archive_catalog_item(
        db, organization_id=organization.id, item_id=item.id, expected_version=2
    )
    db.commit()
    db.refresh(archived)
    assert archived.active is False
    assert archived.bookable is False
    bulk_set_catalog_items_active(
        db, organization_id=organization.id, item_ids=[item.id], active=True
    )
    db.commit()
    db.refresh(item)
    assert item.active is True

    page, total = list_catalog_items(
        db, organization_id=organization.id, query="consult", kind="service", limit=1
    )
    assert total == 2
    assert len(page) == 1


def test_service_resource_requirements_replace_as_one_catalog_configuration() -> None:
    db = _session()
    organization = Organization(name="Requirements", slug="requirements-management")
    db.add(organization)
    db.flush()
    item = create_catalog_item(
        db, organization_id=organization.id, name="Therapy", duration_minutes=45
    )
    db.add(item)
    db.commit()

    replace_service_requirements(
        db,
        organization_id=organization.id,
        catalog_item_id=item.id,
        requirements=[
            {"resource_type": "room", "quantity": 1, "required": True},
            {"resource_type": "practitioner", "capability": "THERAPY", "quantity": 1},
        ],
    )
    db.commit()
    requirements = requirements_for_service(db, item.id)
    assert [(row.resource_type, row.capability) for row in requirements] == [
        ("room", None),
        ("practitioner", "THERAPY"),
    ]
