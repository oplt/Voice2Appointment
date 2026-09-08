"""Catalog lookup and legacy booking-policy duration compatibility."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.feature_flags import require_catalog_domain
from app.db.models import CatalogItem, User

_KINDS = frozenset({"service", "product", "addon", "package"})


def create_catalog_item(
    db: Session,
    *,
    organization_id: int,
    name: str,
    kind: str = "service",
    duration_minutes: int | None = None,
    **fields: object,
) -> CatalogItem:
    require_catalog_domain()
    if kind not in _KINDS:
        raise ValueError("catalog kind must be service, product, addon, or package")
    if duration_minutes is not None and duration_minutes <= 0:
        raise ValueError("duration_minutes must be positive")
    return CatalogItem(
        organization_id=organization_id,
        name=name.strip(),
        kind=kind,
        duration_minutes=duration_minutes,
        **fields,
    )


def booking_duration_minutes(db: Session, user: User, summary: str) -> int | None:
    """Prefer a bookable catalog service; callers retain JSON-policy fallback."""
    from app.core.feature_flags import catalog_domain_enabled

    if not catalog_domain_enabled():
        return None
    if user.organization_id is None:
        return None
    item = db.scalar(
        select(CatalogItem).where(
            CatalogItem.organization_id == user.organization_id,
            CatalogItem.kind == "service",
            CatalogItem.active.is_(True),
            CatalogItem.bookable.is_(True),
            CatalogItem.name.ilike(summary.strip()),
        )
    )
    return item.duration_minutes if item is not None else None
