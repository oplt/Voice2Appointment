"""Restaurant vertical voice tool handlers (waitlist + reservation modify)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.customers.service import get_or_create_customer
from app.db.models import CatalogItem, Reservation
from app.industries.restaurant import book_restaurant_reservation, restaurant_availability
from app.industries.waitlist import cancel_waitlist_entry, join_waitlist, promote_waitlist
from app.reservations.service import cancel_reservation, reschedule_reservation, update_party_size
from app.voice.registry.handlers_common import _as_bool, _org_context, _parse_dt


def create_reservation_tool(
    *,
    catalog_item_id: int | None = None,
    datetime_start: str | None = None,
    party_size: int = 2,
    location_id: int | None = None,
    client_name: str | None = None,
    client_phone: str | None = None,
    seating_preference: str | None = None,
    dietary_notes: str | None = None,
    accessibility_notes: str | None = None,
    special_occasion: str | None = None,
    confirmed: Any = False,
    **_: Any,
) -> dict[str, Any]:
    if not _as_bool(confirmed):
        return {
            "success": False,
            "needs_confirmation": True,
            "message": "Confirm party size, time, and seating before booking.",
        }
    ctx = _org_context()
    if isinstance(ctx, dict):
        return ctx
    db, organization_id, _user_id = ctx
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
    try:
        reservation = book_restaurant_reservation(
            db,
            organization_id=organization_id,
            catalog_item_id=catalog_item_id,
            start_datetime=start,
            party_size=party_size,
            location_id=location_id,
            customer_id=customer.id if customer is not None else None,
            seating_preference=seating_preference,
            dietary_notes=dietary_notes,
            accessibility_notes=accessibility_notes,
            special_occasion=special_occasion,
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


def promote_waitlist_tool(
    *,
    waitlist_id: int | None = None,
    confirmed: Any = False,
    **_: Any,
) -> dict[str, Any]:
    if not _as_bool(confirmed):
        return {
            "success": False,
            "needs_confirmation": True,
            "message": "Confirm promoting this waitlist entry.",
        }
    ctx = _org_context()
    if isinstance(ctx, dict):
        return ctx
    db, organization_id, user_id = ctx
    if waitlist_id is None:
        return {"success": False, "error": "waitlist_id_required"}
    try:
        entry = promote_waitlist(
            db,
            waitlist_id,
            organization_id=organization_id,
            actor_user_id=user_id,
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": type(exc).__name__, "message": str(exc)}
    return {
        "success": True,
        "waitlist_id": entry.id,
        "status": entry.status,
        "promoted_at": (entry.metadata_json or {}).get("promoted_at"),
    }


def cancel_waitlist_tool(
    *,
    waitlist_id: int | None = None,
    confirmed: Any = False,
    **_: Any,
) -> dict[str, Any]:
    if not _as_bool(confirmed):
        return {
            "success": False,
            "needs_confirmation": True,
            "message": "Confirm cancelling this waitlist entry.",
        }
    ctx = _org_context()
    if isinstance(ctx, dict):
        return ctx
    db, organization_id, user_id = ctx
    if waitlist_id is None:
        return {"success": False, "error": "waitlist_id_required"}
    try:
        entry = cancel_waitlist_entry(
            db,
            waitlist_id,
            organization_id=organization_id,
            actor_user_id=user_id,
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": type(exc).__name__, "message": str(exc)}
    return {"success": True, "waitlist_id": entry.id, "status": entry.status}


def modify_reservation_tool(
    *,
    reservation_id: int | None = None,
    party_size: int | None = None,
    datetime_start: str | None = None,
    confirmed: Any = False,
    **_: Any,
) -> dict[str, Any]:
    if not _as_bool(confirmed):
        return {
            "success": False,
            "needs_confirmation": True,
            "message": "Confirm the reservation change before applying it.",
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
    if start is None and party_size is None:
        return {"success": False, "error": "party_size_or_datetime_start_required"}
    try:
        if start is not None:
            row = reschedule_reservation(
                db,
                row.id,
                start_datetime=start,
                party_size=party_size,
                actor_user_id=user_id,
            )
        elif party_size is not None:
            row = update_party_size(
                db, row.id, party_size=party_size, actor_user_id=user_id
            )
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": type(exc).__name__, "message": str(exc)}
    return {
        "success": True,
        "reservation_id": row.id,
        "status": row.status,
        "party_size": row.party_size,
        "start": row.start_datetime.isoformat(),
        "end": row.end_datetime.isoformat(),
    }

def restaurant_availability_tool(
    *,
    catalog_item_id: int | None = None,
    datetime_start: str | None = None,
    datetime_end: str | None = None,
    party_size: int = 2,
    location_id: int | None = None,
    seating_preference: str | None = None,
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
        item = db.scalar(
            select(CatalogItem).where(
                CatalogItem.organization_id == organization_id,
                CatalogItem.bookable.is_(True),
                CatalogItem.active.is_(True),
            )
        )
        if item is None:
            return {"success": False, "error": "catalog_item_required"}
        catalog_item_id = item.id
    end = _parse_dt(datetime_end) or start.replace(hour=23, minute=59)
    result = restaurant_availability(
        db,
        organization_id=organization_id,
        catalog_item_id=catalog_item_id,
        start_date=start,
        end_date=end,
        location_id=location_id,
        party_size=party_size,
        seating_preference=seating_preference,
    )
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
                        "quantity": alloc.quantity,
                    }
                    for alloc in slot.allocations
                ],
            }
            for slot in result.slots[:15]
        ],
        "constraints": result.constraints,
    }

def cancel_reservation_tool(
    *, reservation_id: int | None = None, confirmed: Any = False, **_: Any
) -> dict[str, Any]:
    if not _as_bool(confirmed):
        return {
            "success": False,
            "needs_confirmation": True,
            "message": "Confirm cancellation of this reservation.",
        }
    ctx = _org_context()
    if isinstance(ctx, dict):
        return ctx
    db, organization_id, _user_id = ctx
    if reservation_id is None:
        return {"success": False, "error": "reservation_id_required"}
    row = db.get(Reservation, reservation_id)
    if row is None or row.organization_id != organization_id:
        return {"success": False, "error": "reservation_not_found"}
    try:
        row = cancel_reservation(db, row.id, actor_user_id=_user_id)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": type(exc).__name__, "message": str(exc)}
    return {"success": True, "reservation_id": row.id, "status": row.status}

def join_waitlist_tool(
    *,
    party_size: int = 1,
    location_id: int | None = None,
    catalog_item_id: int | None = None,
    client_name: str | None = None,
    client_phone: str | None = None,
    preferred_start: str | None = None,
    seating_preference: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    ctx = _org_context()
    if isinstance(ctx, dict):
        return ctx
    db, organization_id, _user_id = ctx
    customer = None
    if client_name or client_phone:
        customer = get_or_create_customer(
            db, organization_id=organization_id, name=client_name, phone=client_phone
        )
        db.flush()
    metadata = {}
    if seating_preference:
        metadata["seating_preference"] = seating_preference
    entry = join_waitlist(
        db,
        organization_id=organization_id,
        location_id=location_id,
        customer_id=customer.id if customer is not None else None,
        catalog_item_id=catalog_item_id,
        party_size=party_size,
        preferred_start=_parse_dt(preferred_start),
        metadata=metadata,
    )
    db.commit()
    return {"success": True, "waitlist_id": entry.id, "status": entry.status}

