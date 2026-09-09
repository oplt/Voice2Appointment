"""Salon vertical voice tool handlers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.customers.service import get_or_create_customer
from app.db.models import CatalogItem, Reservation
from app.industries.salon import (
    book_salon_appointment,
    list_staff,
    price_estimate_with_addons,
)
from app.reservations.availability import search_availability
from app.reservations.service import reschedule_reservation
from app.reservations.types import AvailabilityRequest
from app.voice.registry.handlers_industry import _as_bool, _org_context, _parse_dt


def find_salon_services(*, query: str = "", **_: Any) -> dict[str, Any]:
    ctx = _org_context()
    if isinstance(ctx, dict):
        return ctx
    db, organization_id, _user_id = ctx
    stmt = select(CatalogItem).where(
        CatalogItem.organization_id == organization_id,
        CatalogItem.active.is_(True),
        CatalogItem.kind == "service",
    )
    items = list(db.scalars(stmt).all())
    needle = query.strip().casefold()
    if needle:
        items = [item for item in items if needle in (item.name or "").casefold()]
    return {
        "success": True,
        "services": [
            {
                "id": item.id,
                "name": item.name,
                "duration_minutes": item.duration_minutes,
                "bookable": item.bookable,
            }
            for item in items[:25]
        ],
    }


def find_available_staff(
    *,
    skill: str | None = None,
    location_id: int | None = None,
    **_: Any,
) -> dict[str, Any]:
    ctx = _org_context()
    if isinstance(ctx, dict):
        return ctx
    db, organization_id, _user_id = ctx
    rows = list_staff(db, organization_id, skill=skill, location_id=location_id)
    return {
        "success": True,
        "staff": [
            {"id": row.id, "name": row.name, "location_id": row.location_id} for row in rows
        ],
    }


def find_salon_availability(
    *,
    catalog_item_id: int | None = None,
    datetime_start: str | None = None,
    datetime_end: str | None = None,
    location_id: int | None = None,
    preferred_staff_id: int | None = None,
    required_capability: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    ctx = _org_context()
    if isinstance(ctx, dict):
        return ctx
    db, organization_id, _user_id = ctx
    start = _parse_dt(datetime_start)
    if start is None:
        return {"success": False, "error": "datetime_start_required"}
    if catalog_item_id is None:
        return {"success": False, "error": "catalog_item_id_required"}
    preferred = (preferred_staff_id,) if preferred_staff_id is not None else ()
    caps = (required_capability,) if required_capability else ()
    try:
        result = search_availability(
            db,
            AvailabilityRequest(
                organization_id=organization_id,
                catalog_item_id=catalog_item_id,
                start_date=start,
                end_date=_parse_dt(datetime_end),
                location_id=location_id,
                preferred_resource_ids=preferred,
                required_capabilities=caps,
                scheduling_mode="multi_resource",
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": type(exc).__name__, "message": str(exc)}
    return {
        "success": True,
        "slots": [
            {
                "start": slot.start_datetime.isoformat(),
                "end": slot.end_datetime.isoformat(),
                "mode": slot.scheduling_mode,
                "resources": [
                    {
                        "id": alloc.resource_id,
                        "name": alloc.resource_name,
                        "type": alloc.resource_type,
                    }
                    for alloc in slot.allocations
                ],
            }
            for slot in result.slots[:15]
        ],
        "constraints": result.constraints,
    }


def estimate_service_price(
    *,
    catalog_item_id: int | None = None,
    addon_item_ids: list[int] | None = None,
    location_id: int | None = None,
    **_: Any,
) -> dict[str, Any]:
    ctx = _org_context()
    if isinstance(ctx, dict):
        return ctx
    db, organization_id, _user_id = ctx
    if catalog_item_id is None:
        return {"success": False, "error": "catalog_item_id_required"}
    service = db.get(CatalogItem, catalog_item_id)
    if service is None or service.organization_id != organization_id:
        return {"success": False, "error": "service_not_found"}
    addons: list[CatalogItem] = []
    for addon_id in addon_item_ids or []:
        addon = db.get(CatalogItem, int(addon_id))
        if addon is None or addon.organization_id != organization_id or addon.kind != "addon":
            return {"success": False, "error": "addon_not_found", "addon_item_id": addon_id}
        addons.append(addon)
    estimate = price_estimate_with_addons(
        db,
        organization_id=organization_id,
        service=service,
        addons=addons,
        location_id=location_id,
    )
    return {"success": True, **estimate}


def book_salon_service(
    *,
    catalog_item_id: int | None = None,
    datetime_start: str | None = None,
    addon_item_ids: list[int] | None = None,
    preferred_staff_id: int | None = None,
    required_capability: str | None = None,
    location_id: int | None = None,
    client_name: str | None = None,
    client_phone: str | None = None,
    confirmed: Any = False,
    **_: Any,
) -> dict[str, Any]:
    if not _as_bool(confirmed):
        return {
            "success": False,
            "needs_confirmation": True,
            "message": "Confirm service, time, and staff before booking.",
        }
    ctx = _org_context()
    if isinstance(ctx, dict):
        return ctx
    db, organization_id, user_id = ctx
    start = _parse_dt(datetime_start)
    if start is None:
        return {"success": False, "error": "datetime_start_required"}
    if catalog_item_id is None:
        return {"success": False, "error": "catalog_item_id_required"}
    customer = None
    if client_name or client_phone:
        customer = get_or_create_customer(
            db,
            organization_id=organization_id,
            name=client_name,
            phone=client_phone,
        )
        db.flush()
    caps = (required_capability,) if required_capability else ()
    try:
        reservation = book_salon_appointment(
            db,
            organization_id=organization_id,
            catalog_item_id=catalog_item_id,
            start_datetime=start,
            addon_item_ids=tuple(int(x) for x in (addon_item_ids or [])),
            preferred_staff_id=preferred_staff_id,
            required_capabilities=caps,
            location_id=location_id,
            customer_id=customer.id if customer is not None else None,
            owner_user_id=user_id,
            sync_calendar=False,
        )
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": type(exc).__name__, "message": str(exc)}
    return {
        "success": True,
        "reservation_id": reservation.id,
        "status": reservation.status,
        "start": reservation.start_datetime.isoformat(),
        "end": reservation.end_datetime.isoformat(),
        "appointment_id": reservation.appointment_id,
    }


def modify_salon_booking(
    *,
    reservation_id: int | None = None,
    datetime_start: str | None = None,
    preferred_staff_id: int | None = None,
    confirmed: Any = False,
    **_: Any,
) -> dict[str, Any]:
    if not _as_bool(confirmed):
        return {
            "success": False,
            "needs_confirmation": True,
            "message": "Confirm the booking change before applying it.",
        }
    ctx = _org_context()
    if isinstance(ctx, dict):
        return ctx
    db, organization_id, user_id = ctx
    if reservation_id is None:
        return {"success": False, "error": "reservation_id_required"}
    row = db.get(Reservation, reservation_id)
    if row is None or row.organization_id != organization_id:
        return {"success": False, "error": "reservation_not_found"}
    start = _parse_dt(datetime_start)
    if start is None and preferred_staff_id is None:
        return {"success": False, "error": "datetime_start_or_preferred_staff_required"}
    preferred = (preferred_staff_id,) if preferred_staff_id is not None else ()
    try:
        row = reschedule_reservation(
            db,
            row.id,
            start_datetime=start or row.start_datetime,
            preferred_resource_ids=preferred,
            actor_user_id=user_id,
        )
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": type(exc).__name__, "message": str(exc)}
    return {
        "success": True,
        "reservation_id": row.id,
        "status": row.status,
        "start": row.start_datetime.isoformat(),
        "end": row.end_datetime.isoformat(),
    }
