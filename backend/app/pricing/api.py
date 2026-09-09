"""Organization-scoped price-book management API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require_db
from app.core.feature_flags import require_catalog_domain
from app.db.models import CatalogItem, Location, Price, PriceBook
from app.pricing.service import PriceValidationError, validate_new_price
from app.tenancy.api import OrganizationId, require_domain_permission

router = APIRouter(
    tags=["pricing"],
    dependencies=[
        Depends(require_catalog_domain),
        Depends(require_domain_permission("pricing")),
    ],
)


class PriceBookIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    currency: str = Field(min_length=3, max_length=3)
    active: bool = True


class PriceBookPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    active: bool | None = None


class PriceBookOut(PriceBookIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class PriceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    catalog_item_id: int
    location_id: int | None = None
    amount_minor: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    channel: str | None = Field(default=None, max_length=32)
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    tax_metadata: dict[str, Any] = Field(default_factory=dict)


class PricePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location_id: int | None = None
    amount_minor: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    channel: str | None = Field(default=None, max_length=32)
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    tax_metadata: dict[str, Any] | None = None


class PriceOut(PriceIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    price_book_id: int


def _price_book(db: Session, organization_id: int, price_book_id: int) -> PriceBook:
    row = db.scalar(
        select(PriceBook).where(
            PriceBook.id == price_book_id, PriceBook.organization_id == organization_id
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Price book not found")
    return row


def _price(db: Session, organization_id: int, price_book_id: int, price_id: int) -> Price:
    _price_book(db, organization_id, price_book_id)
    row = db.scalar(
        select(Price).where(Price.id == price_id, Price.price_book_id == price_book_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Price not found")
    return row


def _owned_reference(
    db: Session, organization_id: int, model: type[Any], value: int | None, label: str
) -> None:
    if (
        value is not None
        and db.scalar(
            select(model).where(model.id == value, model.organization_id == organization_id)
        )
        is None
    ):
        raise HTTPException(status_code=404, detail=f"{label} not found")


@router.get("/price-books", response_model=list[PriceBookOut])
def list_price_books(
    organization_id: OrganizationId, db: Session = Depends(require_db)
) -> list[PriceBook]:
    return list(
        db.scalars(
            select(PriceBook)
            .where(PriceBook.organization_id == organization_id)
            .order_by(PriceBook.name)
        ).all()
    )


@router.post("/price-books", response_model=PriceBookOut, status_code=status.HTTP_201_CREATED)
def create_price_book(
    payload: PriceBookIn, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> PriceBook:
    data = payload.model_dump()
    data["currency"] = payload.currency.upper()
    row = PriceBook(organization_id=organization_id, **data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/price-books/{price_book_id}", response_model=PriceBookOut)
def patch_price_book(
    price_book_id: int,
    payload: PriceBookPatch,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> PriceBook:
    row = _price_book(db, organization_id, price_book_id)
    values = payload.model_dump(exclude_unset=True)
    if "currency" in values and values["currency"] is not None:
        values["currency"] = values["currency"].upper()
        if values["currency"] != row.currency.upper() and db.scalar(
            select(Price.id).where(Price.price_book_id == row.id).limit(1)
        ) is not None:
            raise HTTPException(
                status_code=422,
                detail="currency cannot be changed after prices have been created",
            )
    for field, value in values.items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


@router.post("/price-books/{price_book_id}/archive", response_model=PriceBookOut)
def archive_price_book(
    price_book_id: int, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> PriceBook:
    row = _price_book(db, organization_id, price_book_id)
    row.active = False
    db.commit()
    db.refresh(row)
    return row


@router.get("/price-books/{price_book_id}/prices", response_model=list[PriceOut])
def list_prices(
    price_book_id: int, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> list[Price]:
    _price_book(db, organization_id, price_book_id)
    return list(db.scalars(select(Price).where(Price.price_book_id == price_book_id)).all())


@router.post(
    "/price-books/{price_book_id}/prices",
    response_model=PriceOut,
    status_code=status.HTTP_201_CREATED,
)
def create_price(
    price_book_id: int,
    payload: PriceIn,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> Price:
    book = _price_book(db, organization_id, price_book_id)
    _owned_reference(db, organization_id, CatalogItem, payload.catalog_item_id, "Catalog item")
    _owned_reference(db, organization_id, Location, payload.location_id, "Location")
    try:
        channel = validate_new_price(
            db,
            price_book_id=book.id,
            catalog_item_id=payload.catalog_item_id,
            location_id=payload.location_id,
            amount_minor=payload.amount_minor,
            currency=payload.currency,
            channel=payload.channel,
            effective_from=payload.effective_from,
            effective_until=payload.effective_until,
        )
    except PriceValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    data = payload.model_dump()
    data["currency"] = payload.currency.upper()
    data["channel"] = channel
    row = Price(price_book_id=price_book_id, **data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/price-books/{price_book_id}/prices/{price_id}", response_model=PriceOut)
def patch_price(
    price_book_id: int,
    price_id: int,
    payload: PricePatch,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> Price:
    row = _price(db, organization_id, price_book_id, price_id)
    values = payload.model_dump(exclude_unset=True)
    if "location_id" in values:
        _owned_reference(db, organization_id, Location, values["location_id"], "Location")
    next_amount = values.get("amount_minor", row.amount_minor)
    next_currency = values.get("currency", row.currency)
    next_channel = values["channel"] if "channel" in values else row.channel
    next_from = values["effective_from"] if "effective_from" in values else row.effective_from
    next_until = values["effective_until"] if "effective_until" in values else row.effective_until
    next_location = values["location_id"] if "location_id" in values else row.location_id
    try:
        channel = validate_new_price(
            db,
            price_book_id=price_book_id,
            catalog_item_id=row.catalog_item_id,
            location_id=next_location,
            amount_minor=next_amount,
            currency=next_currency,
            channel=next_channel,
            effective_from=next_from,
            effective_until=next_until,
            exclude_price_id=row.id,
        )
    except PriceValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if "currency" in values and values["currency"] is not None:
        values["currency"] = values["currency"].upper()
    if "channel" in values:
        values["channel"] = channel
    for field, value in values.items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


@router.post(
    "/price-books/{price_book_id}/prices/{price_id}/archive", response_model=PriceOut
)
def archive_price(
    price_book_id: int,
    price_id: int,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> Price:
    """Soft-archive by closing the effective window at now."""
    row = _price(db, organization_id, price_book_id, price_id)
    now = datetime.now(timezone.utc)
    if row.effective_until is None or row.effective_until > now:
        row.effective_until = now
    db.commit()
    db.refresh(row)
    return row


@router.delete(
    "/price-books/{price_book_id}/prices/{price_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_price(
    price_book_id: int,
    price_id: int,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> None:
    row = _price(db, organization_id, price_book_id, price_id)
    db.delete(row)
    db.commit()
