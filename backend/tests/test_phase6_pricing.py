"""Focused pricing precedence and validation coverage."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.service import create_catalog_item
from app.db.base import Base
from app.db.models import Location, Organization, Price, PriceBook
from app.pricing.api import PriceBookPatch, PriceIn, create_price, patch_price_book
from app.pricing.service import active_price


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _catalog(db: Session) -> tuple[Organization, PriceBook, int, Location]:
    organization = Organization(name="Pricing", slug="pricing")
    db.add(organization)
    db.flush()
    item = create_catalog_item(
        db,
        organization_id=organization.id,
        name="Haircut",
        duration_minutes=30,
        bookable=True,
    )
    location = Location(organization_id=organization.id, name="Main", timezone="UTC")
    book = PriceBook(organization_id=organization.id, name="Standard", currency="EUR")
    db.add_all((item, location, book))
    db.commit()
    return organization, book, item.id, location


def test_active_price_uses_location_and_channel_precedence() -> None:
    db = _session()
    _organization, book, item_id, location = _catalog(db)
    db.add_all(
        (
            Price(price_book_id=book.id, catalog_item_id=item_id, amount_minor=4000, currency="EUR"),
            Price(price_book_id=book.id, catalog_item_id=item_id, amount_minor=5000, currency="EUR", channel="phone"),
            Price(price_book_id=book.id, catalog_item_id=item_id, location_id=location.id, amount_minor=4500, currency="EUR"),
            Price(price_book_id=book.id, catalog_item_id=item_id, location_id=location.id, amount_minor=5500, currency="EUR", channel="phone"),
        )
    )
    db.commit()

    assert active_price(db, price_book_id=book.id, catalog_item_id=item_id, location_id=location.id, channel="phone").amount_minor == 5500  # type: ignore[union-attr]
    assert active_price(db, price_book_id=book.id, catalog_item_id=item_id, location_id=location.id, channel="web").amount_minor == 4500  # type: ignore[union-attr]
    assert active_price(db, price_book_id=book.id, catalog_item_id=item_id, location_id=None, channel="phone").amount_minor == 5000  # type: ignore[union-attr]
    assert active_price(db, price_book_id=book.id, catalog_item_id=item_id, location_id=None, channel="web").amount_minor == 4000  # type: ignore[union-attr]
    assert active_price(db, price_book_id=book.id, catalog_item_id=item_id).amount_minor == 4000  # type: ignore[union-attr]


def test_create_price_rejects_mismatched_currency_and_competing_windows() -> None:
    db = _session()
    organization, book, item_id, location = _catalog(db)
    start = datetime.now(timezone.utc)
    payload = PriceIn(
        catalog_item_id=item_id,
        location_id=location.id,
        amount_minor=4500,
        currency="EUR",
        channel="Phone",
        effective_from=start,
        effective_until=start + timedelta(days=1),
    )
    row = create_price(book.id, payload, organization.id, db)
    assert row.channel == "phone"

    with pytest.raises(HTTPException, match="currency must match"):
        create_price(
            book.id,
            PriceIn(catalog_item_id=item_id, amount_minor=1, currency="USD"),
            organization.id,
            db,
        )
    with pytest.raises(HTTPException, match="overlaps"):
        create_price(
            book.id,
            PriceIn(
                catalog_item_id=item_id,
                location_id=location.id,
                amount_minor=4600,
                currency="EUR",
                channel="phone",
                effective_from=start + timedelta(hours=1),
                effective_until=start + timedelta(days=2),
            ),
            organization.id,
            db,
        )


def test_active_price_honors_the_requested_effective_timestamp() -> None:
    db = _session()
    _organization, book, item_id, _location = _catalog(db)
    transition = datetime(2030, 1, 1, tzinfo=timezone.utc)
    db.add_all(
        (
            Price(
                price_book_id=book.id,
                catalog_item_id=item_id,
                amount_minor=4000,
                currency="EUR",
                effective_from=transition - timedelta(days=1),
                effective_until=transition,
            ),
            Price(
                price_book_id=book.id,
                catalog_item_id=item_id,
                amount_minor=4500,
                currency="EUR",
                effective_from=transition,
            ),
        )
    )
    db.commit()

    before = active_price(
        db,
        price_book_id=book.id,
        catalog_item_id=item_id,
        effective_at=transition - timedelta(hours=1),
    )
    after = active_price(
        db,
        price_book_id=book.id,
        catalog_item_id=item_id,
        effective_at=transition,
    )
    assert before is not None and before.amount_minor == 4000
    assert after is not None and after.amount_minor == 4500


def test_price_book_currency_cannot_change_after_prices_exist() -> None:
    db = _session()
    organization, book, item_id, _location = _catalog(db)
    create_price(
        book.id,
        PriceIn(catalog_item_id=item_id, amount_minor=100, currency="EUR"),
        organization.id,
        db,
    )

    with pytest.raises(HTTPException, match="cannot be changed"):
        patch_price_book(book.id, PriceBookPatch(currency="USD"), organization.id, db)
