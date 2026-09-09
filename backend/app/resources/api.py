"""Organization-scoped resources and availability-rule API."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.deps import require_db
from app.db.models import (
    AvailabilityException,
    AvailabilityRule,
    Location,
    Resource,
    ResourceAdjacency,
    ResourceCapability,
)
from app.resources.service import active_resources
from app.tenancy.api import OrganizationId, require_org_permission

router = APIRouter(
    tags=["resources"], dependencies=[Depends(require_org_permission("organization.manage"))]
)


class ResourceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    resource_type: str = Field(min_length=1, max_length=64)
    location_id: int | None = None
    active: bool = True
    capacity: int = Field(default=1, ge=1)


class ResourcePatch(ResourceIn):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    resource_type: str | None = Field(default=None, min_length=1, max_length=64)


class ResourceOut(ResourceIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class CapabilityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capability: str = Field(min_length=1, max_length=100)


class CapabilityOut(CapabilityIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    resource_id: int


class AvailabilityRuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weekday: int = Field(ge=0, le=6)
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")


class AvailabilityRuleOut(AvailabilityRuleIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    resource_id: int | None
    location_id: int | None


class AvailabilityExceptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    starts_at: datetime
    ends_at: datetime
    available: bool = False
    reason: str | None = Field(default=None, max_length=255)


class AvailabilityExceptionOut(AvailabilityExceptionIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    resource_id: int | None
    location_id: int | None


def _resource(db: Session, organization_id: int, resource_id: int) -> Resource:
    row = db.scalar(
        select(Resource).where(
            Resource.id == resource_id, Resource.organization_id == organization_id
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return row


def _owned_location(db: Session, organization_id: int, location_id: int | None) -> None:
    if (
        location_id is not None
        and db.scalar(
            select(Location).where(
                Location.id == location_id, Location.organization_id == organization_id
            )
        )
        is None
    ):
        raise HTTPException(status_code=404, detail="Location not found")


@router.get("/resources", response_model=list[ResourceOut])
def list_resources(
    organization_id: OrganizationId,
    location_id: int | None = None,
    resource_type: str | None = None,
    db: Session = Depends(require_db),
) -> list[Resource]:
    return active_resources(
        db, organization_id=organization_id, location_id=location_id, resource_type=resource_type
    )


@router.post("/resources", response_model=ResourceOut, status_code=status.HTTP_201_CREATED)
def create_resource(
    payload: ResourceIn, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> Resource:
    _owned_location(db, organization_id, payload.location_id)
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
    db: Session = Depends(require_db),
) -> Resource:
    row = _resource(db, organization_id, resource_id)
    values = payload.model_dump(exclude_unset=True)
    _owned_location(db, organization_id, values.get("location_id"))
    for field, value in values.items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


class AdjacentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    resource_id: int
    name: str
    resource_type: str
    capacity: int
    active: bool


def _normalize_pair(left: int, right: int) -> tuple[int, int]:
    if left == right:
        raise HTTPException(status_code=422, detail="resource cannot be adjacent to itself")
    return (left, right) if left < right else (right, left)


@router.get("/resources/{resource_id}/adjacent", response_model=list[AdjacentOut])
def list_adjacent(
    resource_id: int, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> list[AdjacentOut]:
    _resource(db, organization_id, resource_id)
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
    _resource(db, organization_id, resource_id)
    other = _resource(db, organization_id, other_id)
    a_id, b_id = _normalize_pair(resource_id, other_id)
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
    _resource(db, organization_id, resource_id)
    _resource(db, organization_id, other_id)
    a_id, b_id = _normalize_pair(resource_id, other_id)
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
    _resource(db, organization_id, resource_id)
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
    _resource(db, organization_id, resource_id)
    row = ResourceCapability(resource_id=resource_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/resources/{resource_id}/availability", response_model=list[AvailabilityRuleOut])
def list_availability(
    resource_id: int, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> list[AvailabilityRule]:
    _resource(db, organization_id, resource_id)
    return list(
        db.scalars(
            select(AvailabilityRule).where(
                AvailabilityRule.organization_id == organization_id,
                AvailabilityRule.resource_id == resource_id,
            )
        ).all()
    )


@router.post(
    "/resources/{resource_id}/availability",
    response_model=AvailabilityRuleOut,
    status_code=status.HTTP_201_CREATED,
)
def create_availability(
    resource_id: int,
    payload: AvailabilityRuleIn,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> AvailabilityRule:
    resource = _resource(db, organization_id, resource_id)
    row = AvailabilityRule(
        organization_id=organization_id,
        location_id=resource.location_id,
        resource_id=resource.id,
        **payload.model_dump(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post(
    "/resources/{resource_id}/availability-exceptions",
    response_model=AvailabilityExceptionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_availability_exception(
    resource_id: int,
    payload: AvailabilityExceptionIn,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> AvailabilityException:
    if payload.ends_at <= payload.starts_at:
        raise HTTPException(status_code=422, detail="ends_at must be after starts_at")
    resource = _resource(db, organization_id, resource_id)
    row = AvailabilityException(
        organization_id=organization_id,
        location_id=resource.location_id,
        resource_id=resource.id,
        **payload.model_dump(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
