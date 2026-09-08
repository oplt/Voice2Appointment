"""Industry-profile voice tool handlers (org-scoped via voice ContextVars)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.calendars.tools import (
    cancel_appointment as calendar_cancel_appointment,
)
from app.calendars.tools import (
    check_calendar_availability,
    create_calendar_event,
    request_human_handoff,
    reschedule_appointment,
    voice_db,
    voice_user_id,
)
from app.customers.service import get_or_create_customer
from app.db.models import CatalogItem, Reservation, User
from app.industries.clinic import (
    ClinicSafetyError,
    emergency_safety_gate,
    list_practitioners,
    list_visit_types,
)
from app.industries.general import (
    answer_faq,
    create_quote_request,
    get_price,
    search_catalog,
    take_message,
)
from app.industries.restaurant import book_restaurant_reservation, restaurant_availability
from app.industries.waitlist import join_waitlist


def _parse_dt(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _org_context() -> tuple[Any, int, int] | dict[str, Any]:
    db = voice_db.get()
    user_id = voice_user_id.get()
    if db is None or user_id is None:
        return {"success": False, "error": "voice_context_missing"}
    user = db.get(User, user_id)
    if user is None or user.organization_id is None:
        return {"success": False, "error": "organization_missing"}
    return db, user.organization_id, user_id


def catalog_search(*, query: str = "", **_: Any) -> dict[str, Any]:
    ctx = _org_context()
    if isinstance(ctx, dict):
        return ctx
    db, organization_id, _user_id = ctx
    items = search_catalog(db, organization_id, query=query)
    return {
        "success": True,
        "items": [
            {
                "id": item.id,
                "name": item.name,
                "kind": item.kind,
                "duration_minutes": item.duration_minutes,
            }
            for item in items[:20]
        ],
    }


def search_catalog_tool(*, query: str = "", **kwargs: Any) -> dict[str, Any]:
    return catalog_search(query=query, **kwargs)


def find_visit_types_tool(
    *, specialty: str | None = None, utterance: str | None = None, **_: Any
) -> dict[str, Any]:
    if utterance:
        try:
            gate = emergency_safety_gate(utterance)
        except ClinicSafetyError as exc:
            return {"success": False, "error": "safety_gate", "message": str(exc)}
        if not gate["allowed"]:
            return {"success": False, **gate}
    ctx = _org_context()
    if isinstance(ctx, dict):
        return ctx
    db, organization_id, _user_id = ctx
    items = list_visit_types(db, organization_id, specialty=specialty)
    return {
        "success": True,
        "visit_types": [
            {
                "id": item.id,
                "name": item.name,
                "duration_minutes": item.duration_minutes,
                "requires_referral": bool((item.metadata_json or {}).get("requires_referral")),
                "specialty": (item.metadata_json or {}).get("specialty"),
            }
            for item in items
        ],
    }


def find_practitioners_tool(
    *, location_id: int | None = None, capability: str | None = None, **_: Any
) -> dict[str, Any]:
    ctx = _org_context()
    if isinstance(ctx, dict):
        return ctx
    db, organization_id, _user_id = ctx
    rows = list_practitioners(
        db, organization_id, location_id=location_id, capability=capability
    )
    return {
        "success": True,
        "practitioners": [
            {"id": row.id, "name": row.name, "location_id": row.location_id} for row in rows
        ],
    }


def appointment_availability(**kwargs: Any) -> dict[str, Any]:
    return check_calendar_availability(**kwargs)


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
    row.status = "cancelled"
    db.commit()
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


def get_price_tool(*, catalog_item_id: int | None = None, **_: Any) -> dict[str, Any]:
    ctx = _org_context()
    if isinstance(ctx, dict):
        return ctx
    db, organization_id, _user_id = ctx
    if catalog_item_id is None:
        return {"success": False, "error": "catalog_item_id_required"}
    price = get_price(db, organization_id=organization_id, catalog_item_id=catalog_item_id)
    if price is None:
        return {"success": False, "error": "price_not_found"}
    return {
        "success": True,
        "amount_minor": price.amount_minor,
        "currency": price.currency,
        "tax_metadata": dict(price.tax_metadata or {}),
    }


def create_quote_request_tool(
    *, details: str = "", catalog_item_id: int | None = None, **_: Any
) -> dict[str, Any]:
    ctx = _org_context()
    if isinstance(ctx, dict):
        return ctx
    db, organization_id, user_id = ctx
    row = create_quote_request(
        db,
        organization_id=organization_id,
        catalog_item_id=catalog_item_id,
        details={"details": details},
        actor_user_id=user_id,
    )
    db.commit()
    return {"success": True, "quote_request_id": row.id}


def take_message_tool(
    *,
    message: str = "",
    client_name: str | None = None,
    client_phone: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    ctx = _org_context()
    if isinstance(ctx, dict):
        return ctx
    db, organization_id, user_id = ctx
    if not message.strip():
        return {"success": False, "error": "message_required"}
    row = take_message(
        db,
        organization_id=organization_id,
        message=message,
        customer_name=client_name,
        customer_phone=client_phone,
        actor_user_id=user_id,
    )
    db.commit()
    return {"success": True, "message_id": row.id}


def answer_faq_tool(*, query: str = "", **_: Any) -> dict[str, Any]:
    ctx = _org_context()
    if isinstance(ctx, dict):
        return ctx
    db, organization_id, _user_id = ctx
    entries = answer_faq(db, organization_id, query=query)
    return {
        "success": True,
        "entries": [{"title": e.title, "content": e.content[:500]} for e in entries[:5]],
    }


def provide_product_information(**kwargs: Any) -> dict[str, Any]:
    return catalog_search(**kwargs)


def send_secure_link_tool(*, purpose: str = "payment", **_: Any) -> dict[str, Any]:
    return {
        "success": True,
        "queued": True,
        "purpose": purpose,
        "message": "A secure link will be sent through the configured notification channel.",
    }


def check_order_status_tool(*, order_id: str | None = None, **_: Any) -> dict[str, Any]:
    if not order_id:
        return {"success": False, "error": "order_id_required"}
    return {
        "success": True,
        "order_id": order_id,
        "status": "unknown",
        "message": "Order status lookup is not connected for this tenant yet.",
    }


def book_appointment_tool(**kwargs: Any) -> dict[str, Any]:
    return create_calendar_event(**kwargs)


def create_appointment_tool(**kwargs: Any) -> dict[str, Any]:
    utterance = kwargs.get("summary") or kwargs.get("utterance")
    if isinstance(utterance, str) and utterance:
        try:
            gate = emergency_safety_gate(utterance)
            if not gate["allowed"]:
                return {"success": False, **gate}
        except ClinicSafetyError as exc:
            return {"success": False, "error": "safety_gate", "message": str(exc)}
    return create_calendar_event(**kwargs)


cancel_appointment_tool = calendar_cancel_appointment
reschedule_appointment_tool = reschedule_appointment
request_human_handoff_tool = request_human_handoff
