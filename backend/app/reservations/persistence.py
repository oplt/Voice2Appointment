"""Reservation allocation and pricing persistence helpers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    CatalogItem,
    PriceBook,
    Reservation,
    ReservationLineItem,
    ReservationResource,
)
from app.pricing.service import active_price, snapshot_line_item
from app.reservations.types import ResourceAllocation


def persist_allocations(
    db: Session, reservation: Reservation, allocations: list[ResourceAllocation]
) -> None:
    snapshot = dict(reservation.allocation_json or {})
    snapshot["resources"] = [
        {
            "resource_id": item.resource_id,
            "resource_name": item.resource_name,
            "resource_type": item.resource_type,
            "quantity": item.quantity,
        }
        for item in allocations
    ]
    reservation.allocation_json = snapshot
    for item in allocations:
        db.add(
            ReservationResource(
                reservation_id=reservation.id,
                resource_id=item.resource_id,
                quantity=item.quantity,
            )
        )


def snapshot_prices(
    db: Session,
    *,
    reservation: Reservation,
    catalog_item: CatalogItem,
    price_book_id: int | None,
    channel: str | None = None,
) -> ReservationLineItem | None:
    book_id = price_book_id
    if book_id is None:
        book = db.scalar(
            select(PriceBook).where(
                PriceBook.organization_id == reservation.organization_id,
                PriceBook.active.is_(True),
            )
        )
        book_id = book.id if book is not None else None
    if book_id is None:
        return None
    price = active_price(
        db,
        price_book_id=book_id,
        catalog_item_id=catalog_item.id,
        location_id=reservation.location_id,
        channel=channel,
    )
    if price is None:
        return None
    line = snapshot_line_item(
        reservation_id=reservation.id, item=catalog_item, price=price, quantity=1
    )
    db.add(line)
    return line
