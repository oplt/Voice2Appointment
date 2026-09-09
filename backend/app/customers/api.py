"""Organization-scoped customer API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.deps import require_db
from app.customers.service import (
    CustomerError,
    get_customer,
    get_or_create_customer,
    list_customer_reservations,
    merge_customers,
    normalize_email,
    normalize_phone,
)
from app.db.models import Customer, Reservation
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


class CustomerMergeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_customer_id: int
    target_customer_id: int


class CustomerReservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    start_datetime: datetime
    end_datetime: datetime
    party_size: int
    catalog_item_id: int | None
    appointment_id: int | None


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


@router.post("/merge", response_model=CustomerOut)
def merge_customer(
    payload: CustomerMergeIn, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> Customer:
    try:
        row = merge_customers(
            db,
            organization_id=organization_id,
            source_customer_id=payload.source_customer_id,
            target_customer_id=payload.target_customer_id,
        )
        db.commit()
        db.refresh(row)
        return row
    except CustomerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer_detail(
    customer_id: int, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> Customer:
    row = get_customer(db, organization_id=organization_id, customer_id=customer_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return row


@router.patch("/{customer_id}", response_model=CustomerOut)
def patch_customer(
    customer_id: int,
    payload: CustomerPatch,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> Customer:
    row = get_customer(db, organization_id=organization_id, customer_id=customer_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    values = payload.model_dump(exclude_unset=True)
    if "phone" in values:
        values["phone"] = normalize_phone(values["phone"])
    if "email" in values:
        values["email"] = normalize_email(values["email"])
    for field, value in values.items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


@router.get("/{customer_id}/reservations", response_model=list[CustomerReservationOut])
def customer_reservation_history(
    customer_id: int, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> list[Reservation]:
    row = get_customer(db, organization_id=organization_id, customer_id=customer_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return list_customer_reservations(db, organization_id=organization_id, customer_id=customer_id)
