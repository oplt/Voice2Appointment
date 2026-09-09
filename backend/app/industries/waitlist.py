"""Shared waitlist operations for clinic/restaurant profiles."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Customer, WaitlistEntry


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def join_waitlist(
    db: Session,
    *,
    organization_id: int,
    location_id: int | None = None,
    customer_id: int | None = None,
    catalog_item_id: int | None = None,
    party_size: int = 1,
    preferred_start: datetime | None = None,
    preferred_end: datetime | None = None,
    notes: str | None = None,
    metadata: dict | None = None,
) -> WaitlistEntry:
    if party_size <= 0:
        raise ValueError("party_size must be positive")
    if customer_id is not None:
        customer = db.get(Customer, customer_id)
        if customer is None or customer.organization_id != organization_id:
            raise ValueError("customer not found")
    entry = WaitlistEntry(
        organization_id=organization_id,
        location_id=location_id,
        customer_id=customer_id,
        catalog_item_id=catalog_item_id,
        party_size=party_size,
        preferred_start=_aware(preferred_start),
        preferred_end=_aware(preferred_end),
        status="waiting",
        notes=notes,
        metadata_json=dict(metadata or {}),
    )
    db.add(entry)
    db.flush()
    return entry


def list_waitlist(
    db: Session, *, organization_id: int, status: str = "waiting"
) -> list[WaitlistEntry]:
    return list(
        db.scalars(
            select(WaitlistEntry).where(
                WaitlistEntry.organization_id == organization_id,
                WaitlistEntry.status == status,
            )
        ).all()
    )


def promote_waitlist(
    db: Session,
    entry_id: int,
    *,
    organization_id: int,
    actor_user_id: int | None = None,
) -> WaitlistEntry:
    entry = db.get(WaitlistEntry, entry_id)
    if entry is None or entry.organization_id != organization_id:
        raise ValueError("waitlist entry not found")
    if entry.status in {"cancelled", "promoted"}:
        raise ValueError(f"waitlist entry is already {entry.status}")
    metadata = dict(entry.metadata_json or {})
    metadata["promoted_at"] = datetime.now(timezone.utc).isoformat()
    if actor_user_id is not None:
        metadata["promoted_by_user_id"] = actor_user_id
    # NotificationDelivery is appointment-scoped; record intent for outbound later.
    metadata["notify_pending"] = True
    entry.metadata_json = metadata
    entry.status = "promoted"
    db.flush()
    return entry


def cancel_waitlist_entry(
    db: Session,
    entry_id: int,
    *,
    organization_id: int,
    actor_user_id: int | None = None,
) -> WaitlistEntry:
    entry = db.get(WaitlistEntry, entry_id)
    if entry is None or entry.organization_id != organization_id:
        raise ValueError("waitlist entry not found")
    if entry.status == "cancelled":
        return entry
    metadata = dict(entry.metadata_json or {})
    metadata["cancelled_at"] = datetime.now(timezone.utc).isoformat()
    if actor_user_id is not None:
        metadata["cancelled_by_user_id"] = actor_user_id
    entry.metadata_json = metadata
    entry.status = "cancelled"
    db.flush()
    return entry
