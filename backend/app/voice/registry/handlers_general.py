"""General-business voice tool handlers."""

from __future__ import annotations

from typing import Any

from app.industries.general import (
    answer_faq,
    create_quote_request,
    get_price,
    search_catalog,
    take_message,
)
from app.notifications.secure_links import stage_secure_link
from app.orders.service import get_order_status
from app.voice.registry.handlers_common import _org_context


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

def send_secure_link_tool(
    *,
    purpose: str = "payment",
    client_phone: str | None = None,
    client_email: str | None = None,
    client_name: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    ctx = _org_context()
    if isinstance(ctx, dict):
        return ctx
    db, organization_id, user_id = ctx
    try:
        delivery = stage_secure_link(
            db,
            organization_id=organization_id,
            purpose=purpose,
            client_phone=client_phone,
            client_email=client_email,
            client_name=client_name,
            actor_user_id=user_id,
        )
        db.commit()
    except ValueError as exc:
        return {"success": False, "error": "invalid_recipient", "message": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": type(exc).__name__, "message": str(exc)}
    masked = (delivery.metadata_json or {}).get("recipient_masked")
    return {
        "success": True,
        "queued": True,
        "purpose": delivery.purpose,
        "channel": delivery.channel,
        "delivery_id": delivery.id,
        "link_id": delivery.id,
        "recipient_masked": masked,
        "message": "A secure link has been queued for delivery.",
    }

def check_order_status_tool(*, order_id: str | None = None, **_: Any) -> dict[str, Any]:
    if not order_id:
        return {"success": False, "error": "order_id_required"}
    ctx = _org_context()
    if isinstance(ctx, dict):
        return ctx
    db, organization_id, _user_id = ctx
    row = get_order_status(db, organization_id, order_id)
    if row is None:
        return {
            "success": False,
            "error": "not_found",
            "order_id": order_id,
            "message": "No order found for that id.",
        }
    return {
        "success": True,
        "order_id": row.external_id,
        "status": row.status,
        "customer_id": row.customer_id,
        "metadata": dict(row.metadata_json or {}),
    }

