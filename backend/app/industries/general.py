"""General company capability helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, CatalogItem, KnowledgeEntry, Price, PriceBook
from app.pricing.service import active_price

GENERAL_CAPABILITIES = frozenset(
    {
        "book_appointment",
        "answer_faq",
        "provide_product_information",
        "provide_price",
        "qualify_lead",
        "take_message",
        "request_quote",
        "check_order_status",
        "human_transfer",
        "send_secure_payment_product_link",
    }
)


def search_catalog(db: Session, organization_id: int, *, query: str = "") -> list[CatalogItem]:
    items = list(
        db.scalars(
            select(CatalogItem).where(
                CatalogItem.organization_id == organization_id,
                CatalogItem.active.is_(True),
            )
        ).all()
    )
    if not query.strip():
        return items
    needle = query.casefold()
    return [
        item
        for item in items
        if needle in item.name.casefold()
        or needle in (item.description or "").casefold()
    ]


def answer_faq(db: Session, organization_id: int, *, query: str) -> list[KnowledgeEntry]:
    entries = list(
        db.scalars(
            select(KnowledgeEntry).where(
                KnowledgeEntry.organization_id == organization_id,
                KnowledgeEntry.active.is_(True),
            )
        ).all()
    )
    needle = query.casefold()
    return [
        entry
        for entry in entries
        if needle in entry.title.casefold() or needle in entry.content.casefold()
    ]


def get_price(
    db: Session,
    *,
    organization_id: int,
    catalog_item_id: int,
    location_id: int | None = None,
) -> Price | None:
    book = db.scalar(
        select(PriceBook).where(
            PriceBook.organization_id == organization_id,
            PriceBook.active.is_(True),
        )
    )
    if book is None:
        return None
    return active_price(
        db,
        price_book_id=book.id,
        catalog_item_id=catalog_item_id,
        location_id=location_id,
    )


def take_message(
    db: Session,
    *,
    organization_id: int,
    message: str,
    customer_name: str | None = None,
    customer_phone: str | None = None,
    actor_user_id: int | None = None,
) -> AuditLog:
    row = AuditLog(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="take_message",
        entity_type="lead_message",
        entity_id=None,
        data={
            "message": message,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
        },
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


def create_quote_request(
    db: Session,
    *,
    organization_id: int,
    catalog_item_id: int | None,
    details: dict[str, Any],
    actor_user_id: int | None = None,
) -> AuditLog:
    row = AuditLog(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="create_quote_request",
        entity_type="quote_request",
        entity_id=str(catalog_item_id) if catalog_item_id is not None else None,
        data=dict(details),
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


def qualify_lead(
    db: Session,
    *,
    organization_id: int,
    answers: dict[str, Any],
    actor_user_id: int | None = None,
) -> AuditLog:
    row = AuditLog(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="qualify_lead",
        entity_type="lead",
        entity_id=None,
        data=dict(answers),
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row
