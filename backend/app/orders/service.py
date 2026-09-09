"""Minimal order domain for voice status lookups."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Order


def get_order_status(
    db: Session, organization_id: int, order_id: str
) -> Order | None:
    external_id = (order_id or "").strip()
    if not external_id:
        return None
    return db.scalar(
        select(Order).where(
            Order.organization_id == organization_id,
            Order.external_id == external_id,
        )
    )


def upsert_order(
    db: Session,
    *,
    organization_id: int,
    external_id: str,
    status: str,
    customer_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> Order:
    row = get_order_status(db, organization_id, external_id)
    if row is None:
        row = Order(
            organization_id=organization_id,
            external_id=external_id.strip(),
            status=status,
            customer_id=customer_id,
            metadata_json=dict(metadata or {}),
        )
        db.add(row)
        db.flush()
        return row
    row.status = status
    if customer_id is not None:
        row.customer_id = customer_id
    if metadata is not None:
        row.metadata_json = dict(metadata)
    db.flush()
    return row
