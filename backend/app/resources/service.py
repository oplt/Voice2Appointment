"""Resource requirement queries used by the reservation engine."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Resource, ServiceResourceRequirement


def requirements_for_service(
    db: Session, catalog_item_id: int
) -> list[ServiceResourceRequirement]:
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
        stmt = stmt.where(
            or_(Resource.location_id == location_id, Resource.location_id.is_(None))
        )
    if resource_type is not None:
        stmt = stmt.where(Resource.resource_type == resource_type)
    return list(db.scalars(stmt).all())
