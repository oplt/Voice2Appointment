"""Organization-scoped resources HTTP API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.deps import require_db
from app.db.models import Resource, ResourceAdjacency, ResourceCapability
from app.resources.availability_api import router as availability_router
from app.resources.helpers import (
    future_reservation_count,
    get_resource,
    normalize_pair,
    owned_location,
)
from app.resources.schemas import (
    AdjacentOut,
    CapabilityIn,
    CapabilityOut,
    ResourceIn,
    ResourceOut,
    ResourcePatch,
)
from app.resources.service import active_resources
from app.tenancy.api import OrganizationId, require_resources_permission

router = APIRouter(
    tags=["resources"], dependencies=[Depends(require_resources_permission())]
)


@router.get("/resources", response_model=list[ResourceOut])
def list_resources(
    organization_id: OrganizationId,
    location_id: int | None = None,
    resource_type: str | None = None,
    include_inactive: bool = False,
    db: Session = Depends(require_db),
) -> list[Resource]:
    if include_inactive:
        statement = select(Resource).where(Resource.organization_id == organization_id)
        if location_id is not None:
            statement = statement.where(
                or_(Resource.location_id == location_id, Resource.location_id.is_(None))
            )
        if resource_type is not None:
            statement = statement.where(Resource.resource_type == resource_type)
        return list(db.scalars(statement.order_by(Resource.name, Resource.id)).all())
    return active_resources(
        db, organization_id=organization_id, location_id=location_id, resource_type=resource_type
    )


@router.post("/resources", response_model=ResourceOut, status_code=status.HTTP_201_CREATED)
def create_resource(
    payload: ResourceIn, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> Resource:
    owned_location(db, organization_id, payload.location_id)
    row = Resource(organization_id=organization_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/resources/{resource_id}", response_model=ResourceOut)
def patch_resource(
    resource_id: int,
    payload: ResourcePatch,
    organization_id: OrganizationId,
    force: bool = Query(False),
    db: Session = Depends(require_db),
) -> Resource:
    row = get_resource(db, organization_id, resource_id)
    values = payload.model_dump(exclude_unset=True)
    owned_location(db, organization_id, values.get("location_id"))
    if values.get("active") is False and row.active:
        warning_count = future_reservation_count(
            db, organization_id=organization_id, resource_id=resource_id
        )
        if warning_count > 0 and not force:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": (
                        f"Resource has {warning_count} future confirmed/held reservation(s). "
                        "Pass force=true to deactivate anyway."
                    ),
                    "future_reservation_count": warning_count,
                    "requires_force": True,
                },
            )
    for field, value in values.items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


@router.get("/resources/{resource_id}/adjacent", response_model=list[AdjacentOut])
def list_adjacent(
    resource_id: int, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> list[AdjacentOut]:
    get_resource(db, organization_id, resource_id)
    edges = list(
        db.scalars(
            select(ResourceAdjacency).where(
                ResourceAdjacency.organization_id == organization_id,
                ResourceAdjacency.active.is_(True),
                or_(
                    ResourceAdjacency.resource_a_id == resource_id,
                    ResourceAdjacency.resource_b_id == resource_id,
                ),
            )
        ).all()
    )
    neighbor_ids = [
        edge.resource_b_id if edge.resource_a_id == resource_id else edge.resource_a_id
        for edge in edges
    ]
    if not neighbor_ids:
        return []
    neighbors = {
        row.id: row
        for row in db.scalars(select(Resource).where(Resource.id.in_(neighbor_ids))).all()
    }
    return [
        AdjacentOut(
            id=neighbors[nid].id,
            resource_id=neighbors[nid].id,
            name=neighbors[nid].name,
            resource_type=neighbors[nid].resource_type,
            capacity=neighbors[nid].capacity,
            active=neighbors[nid].active,
        )
        for nid in neighbor_ids
        if nid in neighbors
    ]


@router.post(
    "/resources/{resource_id}/adjacent/{other_id}",
    response_model=AdjacentOut,
    status_code=status.HTTP_201_CREATED,
)
def add_adjacent(
    resource_id: int,
    other_id: int,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> AdjacentOut:
    get_resource(db, organization_id, resource_id)
    other = get_resource(db, organization_id, other_id)
    a_id, b_id = normalize_pair(resource_id, other_id)
    existing = db.scalar(
        select(ResourceAdjacency).where(
            ResourceAdjacency.resource_a_id == a_id,
            ResourceAdjacency.resource_b_id == b_id,
        )
    )
    if existing is None:
        db.add(
            ResourceAdjacency(
                organization_id=organization_id,
                resource_a_id=a_id,
                resource_b_id=b_id,
                active=True,
            )
        )
    else:
        existing.active = True
        existing.organization_id = organization_id
    db.commit()
    return AdjacentOut(
        id=other.id,
        resource_id=other.id,
        name=other.name,
        resource_type=other.resource_type,
        capacity=other.capacity,
        active=other.active,
    )


@router.delete(
    "/resources/{resource_id}/adjacent/{other_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def remove_adjacent(
    resource_id: int,
    other_id: int,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> None:
    get_resource(db, organization_id, resource_id)
    get_resource(db, organization_id, other_id)
    a_id, b_id = normalize_pair(resource_id, other_id)
    row = db.scalar(
        select(ResourceAdjacency).where(
            ResourceAdjacency.resource_a_id == a_id,
            ResourceAdjacency.resource_b_id == b_id,
            ResourceAdjacency.organization_id == organization_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Adjacency not found")
    row.active = False
    db.commit()


@router.get("/resources/{resource_id}/capabilities", response_model=list[CapabilityOut])
def list_capabilities(
    resource_id: int, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> list[ResourceCapability]:
    get_resource(db, organization_id, resource_id)
    return list(
        db.scalars(
            select(ResourceCapability).where(ResourceCapability.resource_id == resource_id)
        ).all()
    )


@router.post(
    "/resources/{resource_id}/capabilities",
    response_model=CapabilityOut,
    status_code=status.HTTP_201_CREATED,
)
def create_capability(
    resource_id: int,
    payload: CapabilityIn,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> ResourceCapability:
    get_resource(db, organization_id, resource_id)
    row = ResourceCapability(resource_id=resource_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch(
    "/resources/{resource_id}/capabilities/{capability_id}", response_model=CapabilityOut
)
def patch_capability(
    resource_id: int,
    capability_id: int,
    payload: CapabilityIn,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> ResourceCapability:
    get_resource(db, organization_id, resource_id)
    row = db.scalar(
        select(ResourceCapability).where(
            ResourceCapability.id == capability_id,
            ResourceCapability.resource_id == resource_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Capability not found")
    row.capability = payload.capability
    db.commit()
    db.refresh(row)
    return row


@router.delete(
    "/resources/{resource_id}/capabilities/{capability_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_capability(
    resource_id: int,
    capability_id: int,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> None:
    get_resource(db, organization_id, resource_id)
    row = db.scalar(
        select(ResourceCapability).where(
            ResourceCapability.id == capability_id,
            ResourceCapability.resource_id == resource_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Capability not found")
    db.delete(row)
    db.commit()


router.include_router(availability_router)
