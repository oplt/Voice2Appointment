"""Restaurant profile — capacity allocation, not calendar events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import IndustryProfile, Reservation, Resource
from app.industries.types import DepositPolicy
from app.industries.waitlist import join_waitlist
from app.reservations.availability import search_availability
from app.reservations.service import book_reservation
from app.reservations.types import AvailabilityRequest

_DINING_AREA_TYPES = frozenset({"dining_area", "table", "capacity_pool"})


def restaurant_availability(
    db: Session,
    *,
    organization_id: int,
    catalog_item_id: int,
    start_date: datetime,
    end_date: datetime | None = None,
    location_id: int | None = None,
    party_size: int = 2,
    seating_preference: str | None = None,
):
    preferred: tuple[int, ...] = ()
    result = search_availability(
        db,
        AvailabilityRequest(
            organization_id=organization_id,
            catalog_item_id=catalog_item_id,
            start_date=start_date,
            end_date=end_date,
            location_id=location_id,
            party_size=party_size,
            preferred_resource_ids=preferred,
            scheduling_mode="capacity",
        ),
    )
    if seating_preference:
        # Soft filter: prefer allocations whose resource_type/name match preference.
        wanted = seating_preference.casefold()
        ranked = sorted(
            result.slots,
            key=lambda slot: (
                0
                if any(
                    wanted in alloc.resource_name.casefold()
                    or wanted in alloc.resource_type.casefold()
                    for alloc in slot.allocations
                )
                else 1
            ),
        )
        from app.reservations.types import AvailabilityResult

        return AvailabilityResult(
            slots=tuple(ranked),
            constraints={**result.constraints, "seating_preference": seating_preference},
        )
    return result


def list_dining_areas(
    db: Session,
    organization_id: int,
    *,
    location_id: int | None = None,
) -> list[Resource]:
    """Soft DiningArea helper — resources that act as seating/capacity pools."""
    stmt = select(Resource).where(
        Resource.organization_id == organization_id,
        Resource.active.is_(True),
        Resource.resource_type.in_(tuple(_DINING_AREA_TYPES)),
    )
    if location_id is not None:
        stmt = stmt.where(Resource.location_id == location_id)
    return list(db.scalars(stmt).all())


def book_restaurant_reservation(
    db: Session,
    *,
    organization_id: int,
    catalog_item_id: int,
    start_datetime: datetime,
    party_size: int,
    location_id: int | None = None,
    customer_id: int | None = None,
    seating_preference: str | None = None,
    dietary_notes: str | None = None,
    accessibility_notes: str | None = None,
    special_occasion: str | None = None,
    price_book_id: int | None = None,
    idempotency_key: str | None = None,
) -> Reservation:
    """Capacity-engine booking; never syncs as a generic Google Calendar event."""
    reservation = book_reservation(
        db,
        organization_id=organization_id,
        catalog_item_id=catalog_item_id,
        start_datetime=start_datetime,
        location_id=location_id,
        customer_id=customer_id,
        party_size=party_size,
        price_book_id=price_book_id,
        scheduling_mode="capacity",
        idempotency_key=idempotency_key,
        sync_calendar=False,
        provider_create=None,
    )
    allocation = dict(reservation.allocation_json or {})
    notes: dict[str, Any] = {}
    if seating_preference:
        notes["seating_preference"] = seating_preference
    if dietary_notes:
        notes["dietary_notes"] = dietary_notes
    if accessibility_notes:
        notes["accessibility_notes"] = accessibility_notes
    if special_occasion:
        notes["special_occasion"] = special_occasion
    if notes:
        allocation["guest_preferences"] = notes
    deposit = resolve_deposit_policy(db, organization_id)
    if deposit.enabled:
        allocation["deposit"] = {
            "required": True,
            "amount_minor": deposit.amount_minor,
            "currency": deposit.currency,
            "no_show_fee_minor": deposit.no_show_fee_minor,
            "status": "pending",
        }
        if reservation.status == "confirmed":
            reservation.status = "held"
        reservation.allocation_json = allocation
        db.flush()
        from app.payments.service import create_deposit_payment_for_reservation

        amount = int(deposit.amount_minor or 0)
        currency = (deposit.currency or "EUR").upper()[:3]
        payment = create_deposit_payment_for_reservation(
            db,
            reservation=reservation,
            amount_minor=amount,
            currency=currency,
            provider="manual",
        )
        allocation = dict(reservation.allocation_json or {})
        deposit_meta = dict(allocation.get("deposit") or {})
        deposit_meta["payment_id"] = payment.id
        allocation["deposit"] = deposit_meta
        reservation.allocation_json = allocation
        db.commit()
        db.refresh(reservation)
        return reservation
    if notes:
        reservation.allocation_json = allocation
        db.commit()
        db.refresh(reservation)
    return reservation


def resolve_deposit_policy(db: Session, organization_id: int) -> DepositPolicy:
    row = db.scalar(
        select(IndustryProfile).where(IndustryProfile.organization_id == organization_id)
    )
    if row is None:
        return DepositPolicy()
    try:
        return DepositPolicy.model_validate(row.deposit_policy or {})
    except Exception:  # noqa: BLE001
        return DepositPolicy()


def mark_no_show(db: Session, reservation_id: int, *, organization_id: int) -> Reservation:
    """Apply no-show status + fee metadata from deposit policy (ledger TBD)."""
    reservation = db.get(Reservation, reservation_id)
    if reservation is None or reservation.organization_id != organization_id:
        raise ValueError("reservation not found")
    if reservation.status in {"cancelled", "no_show"}:
        return reservation
    deposit = resolve_deposit_policy(db, organization_id)
    allocation = dict(reservation.allocation_json or {})
    allocation["no_show"] = {
        "marked_at": datetime.now(timezone.utc).isoformat(),
        "fee_minor": deposit.no_show_fee_minor,
        "currency": deposit.currency,
    }
    reservation.status = "no_show"
    reservation.allocation_json = allocation
    db.commit()
    db.refresh(reservation)
    return reservation


def join_restaurant_waitlist(
    db: Session,
    *,
    organization_id: int,
    party_size: int,
    location_id: int | None = None,
    customer_id: int | None = None,
    seating_preference: str | None = None,
    preferred_start: datetime | None = None,
):
    metadata = {}
    if seating_preference:
        metadata["seating_preference"] = seating_preference
    return join_waitlist(
        db,
        organization_id=organization_id,
        location_id=location_id,
        customer_id=customer_id,
        party_size=party_size,
        preferred_start=preferred_start,
        metadata=metadata,
    )
