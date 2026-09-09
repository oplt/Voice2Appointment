"""Resource requirement queries used by the reservation engine."""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import CatalogItem, Resource, ServiceResourceRequirement


def requirements_for_service(db: Session, catalog_item_id: int) -> list[ServiceResourceRequirement]:
    return list(
        db.scalars(
            select(ServiceResourceRequirement).where(
                ServiceResourceRequirement.catalog_item_id == catalog_item_id
            )
        ).all()
    )


def active_resources(
    db: Session,
    *,
    organization_id: int,
    location_id: int | None = None,
    resource_type: str | None = None,
) -> list[Resource]:
    stmt = select(Resource).where(
        Resource.organization_id == organization_id,
        Resource.active.is_(True),
    )
    if location_id is not None:
        stmt = stmt.where(or_(Resource.location_id == location_id, Resource.location_id.is_(None)))
    if resource_type is not None:
        stmt = stmt.where(Resource.resource_type == resource_type)
    return list(db.scalars(stmt).all())


def _requirement_quantity(requirement: dict[str, Any]) -> int:
    raw = requirement.get("quantity", 1)
    if isinstance(raw, bool):
        raise ValueError("requirement quantity must be positive")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    if isinstance(raw, str) and raw.strip():
        return int(raw)
    return 1


def replace_service_requirements(
    db: Session,
    *,
    organization_id: int,
    catalog_item_id: int,
    requirements: list[dict[str, Any]],
) -> list[ServiceResourceRequirement]:
    item = db.scalar(
        select(CatalogItem).where(
            CatalogItem.id == catalog_item_id, CatalogItem.organization_id == organization_id
        )
    )
    if item is None:
        raise ValueError("catalog item not found")
    for requirement in requirements:
        quantity = _requirement_quantity(requirement)
        if quantity <= 0:
            raise ValueError("requirement quantity must be positive")
    for row in requirements_for_service(db, catalog_item_id):
        db.delete(row)
    db.flush()
    rows = [
        ServiceResourceRequirement(
            catalog_item_id=catalog_item_id,
            resource_type=(str(req["resource_type"]) if req.get("resource_type") else None),
            capability=(str(req["capability"]) if req.get("capability") else None),
            quantity=_requirement_quantity(req),
            required=bool(req.get("required", True)),
        )
        for req in requirements
    ]
    db.add_all(rows)
    return rows
