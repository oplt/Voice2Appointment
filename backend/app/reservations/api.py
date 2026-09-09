"""Organization-scoped availability and reservation HTTP API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_db
from app.calendars.service import booking_provider_hooks
from app.core.errors import map_exception, raise_http
from app.core.feature_flags import require_reservation_domain
from app.db.models import (
    CatalogItem,
    Customer,
    Location,
    PriceBook,
    Reservation,
    ReservationLineItem,
    ReservationResource,
    User,
)
from app.industries.service import sync_calendar_for_org
from app.reservations.schemas import (
    AvailabilityIn,
    CancelIn,
    HoldIn,
    LineItemIn,
    LineItemOut,
    LineItemPatch,
    PartySizeIn,
    RescheduleIn,
    ReservationDetailOut,
    ReservationIn,
    ReservationOut,
    ReservationPageOut,
    ResourceAssignmentIn,
)
from app.reservations.service import (
    add_line_item,
    book_reservation,
    cancel_reservation,
    change_resource_assignment,
    commit_reservation,
    find_availability,
    hold_reservation,
    remove_line_item,
    reschedule_reservation,
    update_line_item_quantity,
    update_party_size,
)
from app.reservations.types import AvailabilityRequest
from app.tenancy.api import OrganizationId, require_domain_permission

router = APIRouter(
    tags=["reservations"],
    dependencies=[
        Depends(require_reservation_domain),
        Depends(require_domain_permission("reservation")),
    ],
)

def _reservation(db: Session, organization_id: int, reservation_id: int) -> Reservation:
    row = db.scalar(
        select(Reservation).where(
            Reservation.id == reservation_id, Reservation.organization_id == organization_id
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return row


def _line_items(db: Session, reservation_id: int) -> list[ReservationLineItem]:
    return list(
        db.scalars(
            select(ReservationLineItem)
            .where(ReservationLineItem.reservation_id == reservation_id)
            .order_by(ReservationLineItem.id)
        ).all()
    )


def _resource_ids(db: Session, reservation_id: int) -> list[int]:
    return list(
        db.scalars(
            select(ReservationResource.resource_id).where(
                ReservationResource.reservation_id == reservation_id
            )
        ).all()
    )


def _reservation_detail(db: Session, row: Reservation) -> ReservationDetailOut:
    return ReservationDetailOut(
        id=row.id,
        location_id=row.location_id,
        customer_id=row.customer_id,
        catalog_item_id=row.catalog_item_id,
        appointment_id=row.appointment_id,
        scheduling_mode=row.scheduling_mode,
        status=row.status,
        start_datetime=row.start_datetime,
        end_datetime=row.end_datetime,
        party_size=row.party_size,
        hold_expires_at=row.hold_expires_at,
        provider_sync_status=row.provider_sync_status,
        allocation_json=dict(row.allocation_json or {}),
        line_items=[LineItemOut.model_validate(line) for line in _line_items(db, row.id)],
        resource_ids=_resource_ids(db, row.id),
    )


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


@router.get("/reservations", response_model=ReservationPageOut)
def list_reservations(
    organization_id: OrganizationId,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(require_db),
) -> ReservationPageOut:
    filters = [Reservation.organization_id == organization_id]
    if status_filter:
        filters.append(Reservation.status == status_filter)
    total = int(db.scalar(select(func.count()).select_from(Reservation).where(*filters)) or 0)
    items = list(
        db.scalars(
            select(Reservation)
            .where(*filters)
            .order_by(Reservation.start_datetime.desc(), Reservation.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return ReservationPageOut(
        items=[ReservationOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/reservations/{reservation_id}", response_model=ReservationDetailOut)
def get_reservation(
    reservation_id: int, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> ReservationDetailOut:
    row = _reservation(db, organization_id, reservation_id)
    return _reservation_detail(db, row)


@router.get("/reservations/{reservation_id}/line-items", response_model=list[LineItemOut])
def list_reservation_line_items(
    reservation_id: int, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> list[ReservationLineItem]:
    _reservation(db, organization_id, reservation_id)
    return _line_items(db, reservation_id)


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


@router.post("/reservations/hold", response_model=ReservationOut, status_code=status.HTTP_201_CREATED)
def hold(
    payload: HoldIn,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> Reservation:
    _owned_reference(db, organization_id, CatalogItem, payload.catalog_item_id, "Catalog item")
    _owned_reference(db, organization_id, Location, payload.location_id, "Location")
    _owned_reference(db, organization_id, Customer, payload.customer_id, "Customer")
    _owned_reference(db, organization_id, PriceBook, payload.price_book_id, "Price book")
    try:
        return hold_reservation(
            db,
            organization_id=organization_id,
            **payload.model_dump(exclude={"preferred_resource_ids", "required_capabilities"}),
            preferred_resource_ids=tuple(payload.preferred_resource_ids),
            required_capabilities=tuple(payload.required_capabilities),
        )
    except Exception as exc:
        raise_http(map_exception(exc))


@router.post("/reservations/{reservation_id}/commit", response_model=ReservationOut)
def commit(
    reservation_id: int,
    organization_id: OrganizationId,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> Reservation:
    _reservation(db, organization_id, reservation_id)
    hooks = booking_provider_hooks(db, current_user.id)
    try:
        return commit_reservation(
            db,
            reservation_id,
            owner_user_id=current_user.id,
            sync_calendar=sync_calendar_for_org(db, organization_id),
            provider_create=hooks.create_event,
            calendar_id=hooks.calendar_id,
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


@router.patch(
    "/reservations/{reservation_id}/line-items/{line_item_id}", response_model=ReservationOut
)
def patch_reservation_line(
    reservation_id: int,
    line_item_id: int,
    payload: LineItemPatch,
    organization_id: OrganizationId,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> Reservation:
    _reservation(db, organization_id, reservation_id)
    try:
        return update_line_item_quantity(
            db,
            reservation_id,
            line_item_id=line_item_id,
            quantity=payload.quantity,
            actor_user_id=current_user.id,
            idempotency_key=payload.idempotency_key,
        )
    except Exception as exc:
        raise_http(map_exception(exc))
