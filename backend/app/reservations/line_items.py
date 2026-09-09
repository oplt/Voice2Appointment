"""Reservation line-item mutations and service-change wrapper."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.feature_flags import require_reservation_domain
from app.db.models import CatalogItem, PriceBook, Reservation, ReservationLineItem
from app.pricing.service import active_price, snapshot_line_item
from app.reservations.lifecycle import (
    ReservationError,
    _begin_lifecycle_operation,
    _finish_lifecycle_operation,
    _require_mutable,
)


def add_line_item(
    db: Session, reservation_id: int, *, catalog_item_id: int, quantity: int = 1,
    price_book_id: int | None = None, channel: str | None = None, actor_user_id: int | None = None,
    idempotency_key: str | None = None,
) -> ReservationLineItem:
    require_reservation_domain()
    if quantity <= 0:
        raise ReservationError("quantity must be positive")
    reservation = db.get(Reservation, reservation_id)
    item = db.get(CatalogItem, catalog_item_id)
    if reservation is None or item is None or item.organization_id != reservation.organization_id:
        raise ReservationError("reservation or catalog item not found")
    payload = {"catalog_item_id": catalog_item_id, "quantity": quantity, "channel": channel}
    record, started = _begin_lifecycle_operation(db, reservation, operation="add_line_item", idempotency_key=idempotency_key, payload=payload)
    if not started:
        line_id = (record.result or {}).get("line_item_id")
        line = db.get(ReservationLineItem, line_id) if line_id is not None else None
        if line is None:
            raise ReservationError("line item not found")
        return line
    _require_mutable(reservation)
    book_id = price_book_id
    if book_id is None:
        book = db.scalar(select(PriceBook).where(PriceBook.organization_id == reservation.organization_id, PriceBook.active.is_(True)))
        book_id = book.id if book is not None else None
    price = active_price(
        db,
        price_book_id=book_id,
        catalog_item_id=item.id,
        location_id=reservation.location_id,
        channel=channel,
    ) if book_id else None
    if price is None:
        raise ReservationError("no active price for catalog item")
    line = snapshot_line_item(reservation_id=reservation.id, item=item, price=price, quantity=quantity)
    db.add(line)
    db.flush()
    record.result = {"line_item_id": line.id}
    _finish_lifecycle_operation(db, reservation, record, actor_user_id=actor_user_id)
    db.commit()
    db.refresh(line)
    return line


def remove_line_item(
    db: Session, reservation_id: int, *, line_item_id: int, actor_user_id: int | None = None,
    idempotency_key: str | None = None,
) -> Reservation:
    require_reservation_domain()
    reservation = db.get(Reservation, reservation_id)
    line = db.get(ReservationLineItem, line_item_id)
    if reservation is None or line is None or line.reservation_id != reservation.id:
        raise ReservationError("line item not found")
    payload = {"line_item_id": line_item_id}
    record, started = _begin_lifecycle_operation(db, reservation, operation="remove_line_item", idempotency_key=idempotency_key, payload=payload)
    if not started:
        return reservation
    _require_mutable(reservation)
    if line.catalog_item_id == reservation.catalog_item_id:
        raise ReservationError("cannot remove the reservation service line item")
    db.delete(line)
    _finish_lifecycle_operation(db, reservation, record, actor_user_id=actor_user_id)
    db.commit()
    db.refresh(reservation)
    return reservation


def update_line_item_quantity(
    db: Session,
    reservation_id: int,
    *,
    line_item_id: int,
    quantity: int,
    actor_user_id: int | None = None,
    idempotency_key: str | None = None,
) -> Reservation:
    require_reservation_domain()
    if quantity <= 0:
        raise ReservationError("quantity must be positive")
    reservation = db.get(Reservation, reservation_id)
    line = db.get(ReservationLineItem, line_item_id)
    if reservation is None or line is None or line.reservation_id != reservation.id:
        raise ReservationError("line item not found")
    if line.catalog_item_id == reservation.catalog_item_id:
        raise ReservationError("cannot change the reservation service line item")
    payload = {"line_item_id": line_item_id, "quantity": quantity}
    record, started = _begin_lifecycle_operation(
        db,
        reservation,
        operation="update_line_item_quantity",
        idempotency_key=idempotency_key,
        payload=payload,
    )
    if not started:
        return reservation
    _require_mutable(reservation)
    line.quantity = quantity
    _finish_lifecycle_operation(db, reservation, record, actor_user_id=actor_user_id)
    db.commit()
    db.refresh(reservation)
    return reservation


def change_service(
    db: Session, reservation_id: int, *, catalog_item_id: int, **kwargs: Any
) -> Reservation:
    """Compatibility wrapper for a service change at the existing time."""
    from app.reservations.service import reschedule_reservation

    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise ReservationError("reservation not found")
    return reschedule_reservation(
        db, reservation_id, start_datetime=reservation.start_datetime,
        catalog_item_id=catalog_item_id, **kwargs,
    )

