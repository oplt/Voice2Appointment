"""Organization-scoped customer API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.deps import require_db
from app.customers.service import get_or_create_customer
from app.db.models import Customer
from app.tenancy.api import OrganizationId, require_domain_permission

router = APIRouter(
    prefix="/customers",
    tags=["customers"],
    dependencies=[Depends(require_domain_permission("customer"))],
)


class CustomerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    language: str | None = Field(default=None, max_length=16)
    consent_preferences: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CustomerPatch(CustomerIn):
    pass


class CustomerOut(CustomerIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


@router.get("", response_model=list[CustomerOut])
def list_customers(
    organization_id: OrganizationId,
    query: str | None = Query(None, max_length=255),
    db: Session = Depends(require_db),
) -> list[Customer]:
    statement = select(Customer).where(Customer.organization_id == organization_id)
    if query:
        pattern = f"%{query.strip()}%"
        statement = statement.where(
            or_(
                Customer.name.ilike(pattern),
                Customer.phone.ilike(pattern),
                Customer.email.ilike(pattern),
            )
        )
    return list(db.scalars(statement.order_by(Customer.name, Customer.id)).all())


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: CustomerIn, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> Customer:
    row = get_or_create_customer(
        db,
        organization_id=organization_id,
        name=payload.name,
        phone=payload.phone,
        email=payload.email,
        language=payload.language,
    )
    row.consent_preferences = payload.consent_preferences
    row.metadata_json = payload.metadata_json
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{customer_id}", response_model=CustomerOut)
def patch_customer(
    customer_id: int,
    payload: CustomerPatch,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> Customer:
    row = db.scalar(
        select(Customer).where(
            Customer.id == customer_id, Customer.organization_id == organization_id
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row
