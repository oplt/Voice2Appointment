"""Organization-scoped availability and reservation HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_db
from app.calendars.service import booking_provider_hooks
from app.core.errors import map_exception, raise_http
from app.db.models import CatalogItem, Customer, Location, PriceBook, Reservation, User
from app.industries.service import sync_calendar_for_org
from app.reservations.service import (
    add_line_item,
    book_reservation,
    cancel_reservation,
    change_resource_assignment,
    find_availability,
    remove_line_item,
    reschedule_reservation,
    update_party_size,
)
from app.reservations.types import AvailabilityRequest
from app.tenancy.api import OrganizationId, require_domain_permission

router = APIRouter(
    tags=["reservations"], dependencies=[Depends(require_domain_permission("reservation"))]
)


class AvailabilityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    catalog_item_id: int
    start_date: datetime
    end_date: datetime | None = None
    location_id: int | None = None
    party_size: int = Field(default=1, gt=0)
    preferred_resource_ids: list[int] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    price_book_id: int | None = None
    channel: str | None = Field(default=None, max_length=32)
    slot_step_minutes: int = Field(default=15, ge=5, le=120)
    scheduling_mode: Literal["single_resource", "multi_resource", "capacity"] | None = None


class ReservationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    catalog_item_id: int
    start_datetime: datetime
    end_datetime: datetime | None = None
    location_id: int | None = None
    customer_id: int | None = None
    party_size: int = Field(default=1, gt=0)
    preferred_resource_ids: list[int] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    price_book_id: int | None = None
    channel: str | None = Field(default=None, max_length=32)
    scheduling_mode: Literal["single_resource", "multi_resource", "capacity"] | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


class ReservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    location_id: int | None
    customer_id: int | None
    catalog_item_id: int | None
    appointment_id: int | None
    scheduling_mode: str
    status: str
    start_datetime: datetime
    end_datetime: datetime
    party_size: int
    hold_expires_at: datetime | None
    provider_sync_status: str
    allocation_json: dict[str, Any]


class CancelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=1000)
    idempotency_key: str | None = Field(default=None, max_length=128)


class RescheduleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_datetime: datetime
    end_datetime: datetime | None = None
    catalog_item_id: int | None = None
    party_size: int | None = Field(default=None, gt=0)
    price_book_id: int | None = None
    channel: str | None = Field(default=None, max_length=32)
    preferred_resource_ids: list[int] = Field(default_factory=list)
    idempotency_key: str | None = Field(default=None, max_length=128)


class PartySizeIn(BaseModel):
    party_size: int = Field(gt=0)
    idempotency_key: str | None = Field(default=None, max_length=128)


class ResourceAssignmentIn(BaseModel):
    resource_ids: list[int] = Field(min_length=1)
    idempotency_key: str | None = Field(default=None, max_length=128)


class LineItemIn(BaseModel):
    catalog_item_id: int
    quantity: int = Field(default=1, gt=0)
    price_book_id: int | None = None
    channel: str | None = Field(default=None, max_length=32)
    idempotency_key: str | None = Field(default=None, max_length=128)


def _reservation(db: Session, organization_id: int, reservation_id: int) -> Reservation:
    row = db.scalar(
        select(Reservation).where(
            Reservation.id == reservation_id, Reservation.organization_id == organization_id
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return row


def _owned_reference(
    db: Session, organization_id: int, model: type[Any], value: int | None, label: str
) -> None:
    if value is None:
        return
    if (
        db.scalar(select(model).where(model.id == value, model.organization_id == organization_id))
        is None
    ):
        raise HTTPException(status_code=404, detail=f"{label} not found")


@router.post("/availability")
def availability(
    payload: AvailabilityIn, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> dict[str, Any]:
    _owned_reference(db, organization_id, CatalogItem, payload.catalog_item_id, "Catalog item")
    _owned_reference(db, organization_id, Location, payload.location_id, "Location")
    _owned_reference(db, organization_id, PriceBook, payload.price_book_id, "Price book")
    try:
        result = find_availability(
            db,
            AvailabilityRequest(
                organization_id=organization_id,
                **payload.model_dump(exclude={"preferred_resource_ids", "required_capabilities"}),
                preferred_resource_ids=tuple(payload.preferred_resource_ids),
                required_capabilities=tuple(payload.required_capabilities),
            ),
        )
    except Exception as exc:
        raise_http(map_exception(exc))
    return {
        "slots": [
            {
                "start_datetime": slot.start_datetime,
                "end_datetime": slot.end_datetime,
                "scheduling_mode": slot.scheduling_mode,
                "allocations": [allocation.__dict__ for allocation in slot.allocations],
                "price_estimate": slot.price_estimate.__dict__ if slot.price_estimate else None,
                "constraints": slot.constraints,
            }
            for slot in result.slots
        ],
        "constraints": result.constraints,
    }


@router.get("/reservations", response_model=list[ReservationOut])
def list_reservations(
    organization_id: OrganizationId,
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(require_db),
) -> list[Reservation]:
    statement = select(Reservation).where(Reservation.organization_id == organization_id)
    if status_filter:
        statement = statement.where(Reservation.status == status_filter)
    return list(db.scalars(statement.order_by(Reservation.start_datetime.desc()).limit(200)).all())


@router.post("/reservations", response_model=ReservationOut, status_code=status.HTTP_201_CREATED)
def create_reservation(
    payload: ReservationIn,
    organization_id: OrganizationId,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> Reservation:
    _owned_reference(db, organization_id, CatalogItem, payload.catalog_item_id, "Catalog item")
    _owned_reference(db, organization_id, Location, payload.location_id, "Location")
    _owned_reference(db, organization_id, Customer, payload.customer_id, "Customer")
    _owned_reference(db, organization_id, PriceBook, payload.price_book_id, "Price book")
    hooks = booking_provider_hooks(db, current_user.id)
    try:
        return book_reservation(
            db,
            organization_id=organization_id,
            owner_user_id=current_user.id,
            sync_calendar=sync_calendar_for_org(db, organization_id),
            provider_create=hooks.create_event,
            calendar_id=hooks.calendar_id,
            **payload.model_dump(exclude={"preferred_resource_ids", "required_capabilities"}),
            preferred_resource_ids=tuple(payload.preferred_resource_ids),
            required_capabilities=tuple(payload.required_capabilities),
        )
    except Exception as exc:
        raise_http(map_exception(exc))


@router.post("/reservations/{reservation_id}/cancel", response_model=ReservationOut)
def cancel(
    reservation_id: int,
    payload: CancelIn,
    organization_id: OrganizationId,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> Reservation:
    _reservation(db, organization_id, reservation_id)
    hooks = booking_provider_hooks(db, current_user.id)
    try:
        return cancel_reservation(
            db,
            reservation_id,
            actor_user_id=current_user.id,
            provider_delete=hooks.delete_event,
            **payload.model_dump(),
        )
    except Exception as exc:
        raise_http(map_exception(exc))


@router.post("/reservations/{reservation_id}/reschedule", response_model=ReservationOut)
def reschedule(
    reservation_id: int,
    payload: RescheduleIn,
    organization_id: OrganizationId,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> Reservation:
    _reservation(db, organization_id, reservation_id)
    _owned_reference(db, organization_id, CatalogItem, payload.catalog_item_id, "Catalog item")
    _owned_reference(db, organization_id, PriceBook, payload.price_book_id, "Price book")
    hooks = booking_provider_hooks(db, current_user.id)
    try:
        return reschedule_reservation(
            db,
            reservation_id,
            actor_user_id=current_user.id,
            provider_update=hooks.update_event,
            **payload.model_dump(exclude={"preferred_resource_ids"}),
            preferred_resource_ids=tuple(payload.preferred_resource_ids),
        )
    except Exception as exc:
        raise_http(map_exception(exc))


@router.post("/reservations/{reservation_id}/party-size", response_model=ReservationOut)
def change_party_size(
    reservation_id: int,
    payload: PartySizeIn,
    organization_id: OrganizationId,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> Reservation:
    _reservation(db, organization_id, reservation_id)
    try:
        return update_party_size(
            db, reservation_id, actor_user_id=current_user.id, **payload.model_dump()
        )
    except Exception as exc:
        raise_http(map_exception(exc))


@router.post("/reservations/{reservation_id}/resources", response_model=ReservationOut)
def change_resources(
    reservation_id: int,
    payload: ResourceAssignmentIn,
    organization_id: OrganizationId,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> Reservation:
    _reservation(db, organization_id, reservation_id)
    try:
        return change_resource_assignment(
            db,
            reservation_id,
            actor_user_id=current_user.id,
            resource_ids=tuple(payload.resource_ids),
            idempotency_key=payload.idempotency_key,
        )
    except Exception as exc:
        raise_http(map_exception(exc))


@router.post("/reservations/{reservation_id}/line-items", status_code=status.HTTP_201_CREATED)
def add_reservation_line(
    reservation_id: int,
    payload: LineItemIn,
    organization_id: OrganizationId,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> dict[str, Any]:
    _reservation(db, organization_id, reservation_id)
    _owned_reference(db, organization_id, CatalogItem, payload.catalog_item_id, "Catalog item")
    _owned_reference(db, organization_id, PriceBook, payload.price_book_id, "Price book")
    try:
        line = add_line_item(
            db, reservation_id, actor_user_id=current_user.id, **payload.model_dump()
        )
        return {
            "id": line.id,
            "catalog_item_id": line.catalog_item_id,
            "item_name": line.item_name,
            "quantity": line.quantity,
            "unit_price_minor": line.unit_price_minor,
            "currency": line.currency,
        }
    except Exception as exc:
        raise_http(map_exception(exc))


@router.delete(
    "/reservations/{reservation_id}/line-items/{line_item_id}", response_model=ReservationOut
)
def delete_reservation_line(
    reservation_id: int,
    line_item_id: int,
    organization_id: OrganizationId,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> Reservation:
    _reservation(db, organization_id, reservation_id)
    try:
        return remove_line_item(
            db, reservation_id, line_item_id=line_item_id, actor_user_id=current_user.id
        )
    except Exception as exc:
        raise_http(map_exception(exc))
