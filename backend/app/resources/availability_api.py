"""Resource availability rule and exception HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require_db
from app.db.models import AvailabilityException, AvailabilityRule
from app.resources.helpers import get_resource
from app.resources.schemas import (
    AvailabilityExceptionIn,
    AvailabilityExceptionOut,
    AvailabilityExceptionPatch,
    AvailabilityRuleIn,
    AvailabilityRuleOut,
    AvailabilityRulePatch,
)
from app.tenancy.api import OrganizationId

router = APIRouter()

@router.get("/resources/{resource_id}/availability", response_model=list[AvailabilityRuleOut])
def list_availability(
    resource_id: int, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> list[AvailabilityRule]:
    get_resource(db, organization_id, resource_id)
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
    resource = get_resource(db, organization_id, resource_id)
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


@router.patch(
    "/resources/{resource_id}/availability/{rule_id}", response_model=AvailabilityRuleOut
)
def patch_availability(
    resource_id: int,
    rule_id: int,
    payload: AvailabilityRulePatch,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> AvailabilityRule:
    get_resource(db, organization_id, resource_id)
    row = db.scalar(
        select(AvailabilityRule).where(
            AvailabilityRule.id == rule_id,
            AvailabilityRule.organization_id == organization_id,
            AvailabilityRule.resource_id == resource_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Availability rule not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


@router.delete(
    "/resources/{resource_id}/availability/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_availability(
    resource_id: int,
    rule_id: int,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> None:
    get_resource(db, organization_id, resource_id)
    row = db.scalar(
        select(AvailabilityRule).where(
            AvailabilityRule.id == rule_id,
            AvailabilityRule.organization_id == organization_id,
            AvailabilityRule.resource_id == resource_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Availability rule not found")
    db.delete(row)
    db.commit()


@router.get(
    "/resources/{resource_id}/availability-exceptions",
    response_model=list[AvailabilityExceptionOut],
)
def list_availability_exceptions(
    resource_id: int, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> list[AvailabilityException]:
    get_resource(db, organization_id, resource_id)
    return list(
        db.scalars(
            select(AvailabilityException)
            .where(
                AvailabilityException.organization_id == organization_id,
                AvailabilityException.resource_id == resource_id,
            )
            .order_by(AvailabilityException.starts_at.desc())
        ).all()
    )


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
    resource = get_resource(db, organization_id, resource_id)
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


@router.patch(
    "/resources/{resource_id}/availability-exceptions/{exception_id}",
    response_model=AvailabilityExceptionOut,
)
def patch_availability_exception(
    resource_id: int,
    exception_id: int,
    payload: AvailabilityExceptionPatch,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> AvailabilityException:
    get_resource(db, organization_id, resource_id)
    row = db.scalar(
        select(AvailabilityException).where(
            AvailabilityException.id == exception_id,
            AvailabilityException.organization_id == organization_id,
            AvailabilityException.resource_id == resource_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Availability exception not found")
    values = payload.model_dump(exclude_unset=True)
    starts = values.get("starts_at", row.starts_at)
    ends = values.get("ends_at", row.ends_at)
    if ends <= starts:
        raise HTTPException(status_code=422, detail="ends_at must be after starts_at")
    for field, value in values.items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


@router.delete(
    "/resources/{resource_id}/availability-exceptions/{exception_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_availability_exception(
    resource_id: int,
    exception_id: int,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> None:
    get_resource(db, organization_id, resource_id)
    row = db.scalar(
        select(AvailabilityException).where(
            AvailabilityException.id == exception_id,
            AvailabilityException.organization_id == organization_id,
            AvailabilityException.resource_id == resource_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Availability exception not found")
    db.delete(row)
    db.commit()
