"""Shared helpers for industry voice tool handlers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from app.calendars.tools import voice_db, voice_user_id
from app.db.models import CatalogItem, User


def parse_dt(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def org_context() -> tuple[Any, int, int] | dict[str, Any]:
    db = voice_db.get()
    user_id = voice_user_id.get()
    if db is None or user_id is None:
        return {"success": False, "error": "voice_context_missing"}
    user = db.get(User, user_id)
    if user is None or user.organization_id is None:
        return {"success": False, "error": "organization_missing"}
    return db, user.organization_id, user_id


def find_bookable_catalog_item(
    db: Any,
    organization_id: int,
    *,
    catalog_item_id: int | None,
    summary: str | None,
) -> CatalogItem | None:
    if catalog_item_id is not None:
        item = db.get(CatalogItem, catalog_item_id)
        if (
            item is not None
            and item.organization_id == organization_id
            and item.active
            and item.bookable
        ):
            return item
        return None
    needle = (summary or "").strip()
    if not needle:
        return None
    exact = db.scalar(
        select(CatalogItem).where(
            CatalogItem.organization_id == organization_id,
            CatalogItem.active.is_(True),
            CatalogItem.bookable.is_(True),
            func.lower(CatalogItem.name) == needle.casefold(),
        )
    )
    if exact is not None:
        return exact
    return db.scalar(
        select(CatalogItem)
        .where(
            CatalogItem.organization_id == organization_id,
            CatalogItem.active.is_(True),
            CatalogItem.bookable.is_(True),
            CatalogItem.name.ilike(f"%{needle}%"),
        )
        .limit(1)
    )



# Underscore aliases preserved for existing vertical handler imports.
_parse_dt = parse_dt
_as_bool = as_bool
_org_context = org_context
_find_bookable_catalog_item = find_bookable_catalog_item
