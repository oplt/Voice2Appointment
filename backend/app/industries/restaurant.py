"""Restaurant profile — capacity allocation, not calendar events."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Reservation
from app.industries.waitlist import join_waitlist
from app.reservations.availability import search_availability
from app.reservations.service import book_reservation
from app.reservations.types import AvailabilityRequest


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
    notes: dict[str, Any] = {}
    if seating_preference:
        notes["seating_preference"] = seating_preference
    if dietary_notes:
        notes["dietary_notes"] = dietary_notes
    if accessibility_notes:
        notes["accessibility_notes"] = accessibility_notes
    if notes:
        allocation = dict(reservation.allocation_json or {})
        allocation["guest_preferences"] = notes
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
