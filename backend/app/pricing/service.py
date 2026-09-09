"""Minor-unit pricing lookup and immutable reservation price snapshots."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import case, func, literal, or_, select, true
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import CatalogItem, Price, PriceBook, ReservationLineItem


class PriceValidationError(ValueError):
    """Raised when a price cannot safely be added to a price book."""


def normalize_channel(channel: str | None) -> str | None:
    if channel is None:
        return None
    normalized = channel.strip().casefold()
    if not normalized:
        raise PriceValidationError("channel must not be blank")
    return normalized


def active_price(
    db: Session,
    *,
    price_book_id: int,
    catalog_item_id: int,
    location_id: int | None = None,
    channel: str | None = None,
    effective_at: datetime | None = None,
) -> Price | None:
    """Return the most specific effective price for a booking channel.

    A channel-specific price never leaks into a generic request.  For a named
    channel, location and channel specificity are resolved in this order:
    exact location + exact channel, exact location + generic channel,
    generic location + exact channel, generic location + generic channel.
    """
    now = effective_at or datetime.now(timezone.utc)
    normalized_channel = normalize_channel(channel)
    location_filter = (
        Price.location_id.is_(None)
        if location_id is None
        else or_(Price.location_id == location_id, Price.location_id.is_(None))
    )
    channel_filter = (
        Price.channel.is_(None)
        if normalized_channel is None
        else or_(func.lower(Price.channel) == normalized_channel, Price.channel.is_(None))
    )
    location_rank = (
        literal(0)
        if location_id is None
        else case((Price.location_id == location_id, 0), else_=1)
    )
    channel_rank = (
        literal(0)
        if normalized_channel is None
        else case((func.lower(Price.channel) == normalized_channel, 0), else_=1)
    )
    return db.scalar(
        select(Price)
        .where(
            Price.price_book_id == price_book_id,
            Price.catalog_item_id == catalog_item_id,
            location_filter,
            channel_filter,
            or_(Price.effective_from.is_(None), Price.effective_from <= now),
            or_(Price.effective_until.is_(None), Price.effective_until > now),
        )
        .order_by(
            location_rank,
            channel_rank,
            case((Price.effective_from.is_(None), 1), else_=0),
            Price.effective_from.desc(),
            Price.id.desc(),
        )
    )


def validate_new_price(
    db: Session,
    *,
    price_book_id: int,
    catalog_item_id: int,
    location_id: int | None,
    amount_minor: int,
    currency: str,
    channel: str | None,
    effective_from: datetime | None,
    effective_until: datetime | None,
    exclude_price_id: int | None = None,
) -> str | None:
    """Validate a new price and return its canonical channel value."""
    if amount_minor < 0:
        raise PriceValidationError("amount_minor must be non-negative")
    if effective_from is not None and effective_until is not None:
        if effective_until <= effective_from:
            raise PriceValidationError("effective_until must be after effective_from")

    price_book_currency = db.scalar(
        select(PriceBook.currency).where(PriceBook.id == price_book_id)
    )
    if price_book_currency is None:
        raise PriceValidationError("price book not found")
    if currency.upper() != price_book_currency.upper():
        raise PriceValidationError("price currency must match the price book currency")

    normalized_channel = normalize_channel(channel)
    target_location = (
        Price.location_id.is_(None)
        if location_id is None
        else Price.location_id == location_id
    )
    target_channel = (
        Price.channel.is_(None)
        if normalized_channel is None
        else func.lower(Price.channel) == normalized_channel
    )
    starts_before_new_end: ColumnElement[bool] = (
        true()
        if effective_until is None
        else or_(Price.effective_from.is_(None), Price.effective_from < effective_until)
    )
    ends_after_new_start: ColumnElement[bool] = (
        true()
        if effective_from is None
        else or_(Price.effective_until.is_(None), Price.effective_until > effective_from)
    )
    conflict_stmt = select(Price.id).where(
        Price.price_book_id == price_book_id,
        Price.catalog_item_id == catalog_item_id,
        target_location,
        target_channel,
        starts_before_new_end,
        ends_after_new_start,
    )
    if exclude_price_id is not None:
        conflict_stmt = conflict_stmt.where(Price.id != exclude_price_id)
    conflict = db.scalar(conflict_stmt)
    if conflict is not None:
        raise PriceValidationError("price overlaps an existing price with the same scope")
    return normalized_channel


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
