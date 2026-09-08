"""Minor-unit pricing lookup and immutable reservation price snapshots."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import CatalogItem, Price, ReservationLineItem


def active_price(
    db: Session, *, price_book_id: int, catalog_item_id: int, location_id: int | None = None
) -> Price | None:
    now = datetime.now(timezone.utc)
    return db.scalar(
        select(Price)
        .where(
            Price.price_book_id == price_book_id,
            Price.catalog_item_id == catalog_item_id,
            or_(Price.location_id == location_id, Price.location_id.is_(None)),
            or_(Price.effective_from.is_(None), Price.effective_from <= now),
            or_(Price.effective_until.is_(None), Price.effective_until > now),
        )
        .order_by(Price.location_id.desc(), Price.effective_from.desc())
    )


def snapshot_line_item(
    *, reservation_id: int, item: CatalogItem, price: Price, quantity: int = 1
) -> ReservationLineItem:
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    return ReservationLineItem(
        reservation_id=reservation_id,
        catalog_item_id=item.id,
        item_name=item.name,
        quantity=quantity,
        unit_price_minor=price.amount_minor,
        currency=price.currency,
        tax_metadata=dict(price.tax_metadata or {}),
    )
