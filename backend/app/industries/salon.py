"""Salon / professional-services profile helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CatalogItem, PriceBook, Reservation, Resource, ResourceCapability
from app.pricing.service import active_price
from app.reservations.service import book_reservation


def list_staff(
    db: Session,
    organization_id: int,
    *,
    skill: str | None = None,
    location_id: int | None = None,
) -> list[Resource]:
    stmt = select(Resource).where(
        Resource.organization_id == organization_id,
        Resource.active.is_(True),
        Resource.resource_type == "employee",
    )
    if location_id is not None:
        stmt = stmt.where(Resource.location_id == location_id)
    staff = list(db.scalars(stmt).all())
    if skill is None:
        return staff
    wanted = skill.casefold()
    rows = db.execute(
        select(ResourceCapability.resource_id, ResourceCapability.capability).where(
            ResourceCapability.resource_id.in_([r.id for r in staff] or [-1])
        )
    )
    by_resource: dict[int, set[str]] = {}
    for resource_id, capability in rows:
        by_resource.setdefault(int(resource_id), set()).add(str(capability).casefold())
    return [r for r in staff if wanted in by_resource.get(r.id, set())]


def list_addons(db: Session, organization_id: int, *, parent_item_id: int | None = None) -> list[CatalogItem]:
    stmt = select(CatalogItem).where(
        CatalogItem.organization_id == organization_id,
        CatalogItem.active.is_(True),
        CatalogItem.kind == "addon",
    )
    items = list(db.scalars(stmt).all())
    if parent_item_id is None:
        return items
    return [
        item
        for item in items
        if (item.metadata_json or {}).get("parent_catalog_item_id") in (None, parent_item_id)
    ]


def service_duration_with_addons(
    service: CatalogItem, addons: list[CatalogItem]
) -> int:
    base = service.duration_minutes or 30
    extra = sum(int(addon.duration_minutes or 0) for addon in addons)
    return base + extra


def price_estimate_with_addons(
    db: Session,
    *,
    organization_id: int,
    service: CatalogItem,
    addons: list[CatalogItem],
    location_id: int | None = None,
    price_book_id: int | None = None,
) -> dict[str, Any]:
    book_id = price_book_id
    if book_id is None:
        book = db.scalar(
            select(PriceBook).where(
                PriceBook.organization_id == organization_id,
                PriceBook.active.is_(True),
            )
        )
        book_id = book.id if book is not None else None
    if book_id is None:
        return {"currency": None, "amount_minor": None, "lines": []}
    lines = []
    total = 0
    currency = None
    for item in [service, *addons]:
        price = active_price(
            db, price_book_id=book_id, catalog_item_id=item.id, location_id=location_id
        )
        if price is None:
            continue
        currency = price.currency
        total += price.amount_minor
        lines.append(
            {
                "catalog_item_id": item.id,
                "item_name": item.name,
                "unit_price_minor": price.amount_minor,
                "currency": price.currency,
            }
        )
    return {"currency": currency, "amount_minor": total, "lines": lines}


def book_salon_appointment(
    db: Session,
    *,
    organization_id: int,
    catalog_item_id: int,
    start_datetime: datetime,
    addon_item_ids: tuple[int, ...] = (),
    preferred_staff_id: int | None = None,
    required_capabilities: tuple[str, ...] = (),
    location_id: int | None = None,
    customer_id: int | None = None,
    price_book_id: int | None = None,
    owner_user_id: int | None = None,
    sync_calendar: bool = True,
) -> Reservation:
    service = db.get(CatalogItem, catalog_item_id)
    if service is None or service.organization_id != organization_id:
        raise ValueError("service not found")
    addons = []
    for addon_id in addon_item_ids:
        addon = db.get(CatalogItem, addon_id)
        if addon is None or addon.organization_id != organization_id or addon.kind != "addon":
            raise ValueError("addon not found")
        addons.append(addon)
    duration = service_duration_with_addons(service, addons)
    preferred = (preferred_staff_id,) if preferred_staff_id is not None else ()
    reservation = book_reservation(
        db,
        organization_id=organization_id,
        catalog_item_id=catalog_item_id,
        start_datetime=start_datetime,
        location_id=location_id,
        customer_id=customer_id,
        preferred_resource_ids=preferred,
        required_capabilities=required_capabilities,
        price_book_id=price_book_id,
        scheduling_mode="multi_resource",
        duration_minutes=duration,
        owner_user_id=owner_user_id,
        sync_calendar=sync_calendar,
    )
    if addons:
        allocation = dict(reservation.allocation_json or {})
        allocation["addons"] = [
            {
                "catalog_item_id": addon.id,
                "name": addon.name,
                "duration_minutes": addon.duration_minutes,
            }
            for addon in addons
        ]
        reservation.allocation_json = allocation
        db.commit()
        db.refresh(reservation)
    return reservation
