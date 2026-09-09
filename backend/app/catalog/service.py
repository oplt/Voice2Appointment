"""Catalog lookup and legacy booking-policy duration compatibility."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.feature_flags import require_catalog_domain
from app.db.models import CatalogCategory, CatalogItem, CatalogOption, User

_KINDS = frozenset({"service", "product", "addon", "package"})


class CatalogError(ValueError):
    pass


class CatalogNotFoundError(CatalogError):
    pass


class CatalogConflictError(CatalogError):
    pass


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


def list_catalog_items(
    db: Session,
    *,
    organization_id: int,
    query: str | None = None,
    category_id: int | None = None,
    kind: str | None = None,
    active: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[CatalogItem], int]:
    require_catalog_domain()
    if kind is not None and kind not in _KINDS:
        raise CatalogError("catalog kind must be service, product, addon, or package")
    statement = select(CatalogItem).where(CatalogItem.organization_id == organization_id)
    if query and query.strip():
        statement = statement.where(CatalogItem.name.ilike(f"%{query.strip()}%"))
    if category_id is not None:
        statement = statement.where(CatalogItem.category_id == category_id)
    if kind is not None:
        statement = statement.where(CatalogItem.kind == kind)
    if active is not None:
        statement = statement.where(CatalogItem.active.is_(active))
    rows = list(db.scalars(statement.order_by(CatalogItem.name, CatalogItem.id)).all())
    return rows[offset : offset + limit], len(rows)


def get_catalog_item(db: Session, *, organization_id: int, item_id: int) -> CatalogItem:
    row = db.scalar(
        select(CatalogItem).where(
            CatalogItem.id == item_id, CatalogItem.organization_id == organization_id
        )
    )
    if row is None:
        raise CatalogNotFoundError("catalog item not found")
    return row


def update_catalog_item(
    db: Session,
    *,
    organization_id: int,
    item_id: int,
    expected_version: int,
    fields: dict[str, object],
) -> CatalogItem:
    row = get_catalog_item(db, organization_id=organization_id, item_id=item_id)
    kind = fields.get("kind")
    if kind is not None and kind not in _KINDS:
        raise CatalogError("catalog kind must be service, product, addon, or package")
    duration = fields.get("duration_minutes")
    if duration is not None and (not isinstance(duration, int) or duration <= 0):
        raise CatalogError("duration_minutes must be positive")
    result = db.execute(
        update(CatalogItem)
        .where(
            CatalogItem.id == item_id,
            CatalogItem.organization_id == organization_id,
            CatalogItem.version == expected_version,
        )
        .values(**fields, version=expected_version + 1)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise CatalogConflictError("catalog item has changed; refresh and retry")
    db.refresh(row)
    return row


def archive_catalog_item(
    db: Session, *, organization_id: int, item_id: int, expected_version: int
) -> CatalogItem:
    return update_catalog_item(
        db,
        organization_id=organization_id,
        item_id=item_id,
        expected_version=expected_version,
        fields={"active": False, "bookable": False},
    )


def duplicate_catalog_item(
    db: Session, *, organization_id: int, item_id: int, name: str | None = None
) -> CatalogItem:
    source = get_catalog_item(db, organization_id=organization_id, item_id=item_id)
    copy = CatalogItem(
        organization_id=organization_id,
        category_id=source.category_id,
        kind=source.kind,
        name=(name or f"{source.name} (copy)").strip(),
        description=source.description,
        active=False,
        bookable=False,
        sellable=source.sellable,
        duration_minutes=source.duration_minutes,
        buffer_before_minutes=source.buffer_before_minutes,
        buffer_after_minutes=source.buffer_after_minutes,
        metadata_json=dict(source.metadata_json or {}),
    )
    db.add(copy)
    db.flush()
    for option in db.scalars(
        select(CatalogOption).where(CatalogOption.catalog_item_id == source.id)
    ).all():
        db.add(
            CatalogOption(
                catalog_item_id=copy.id,
                name=option.name,
                active=option.active,
                metadata_json=dict(option.metadata_json or {}),
            )
        )
    return copy


def bulk_set_catalog_items_active(
    db: Session, *, organization_id: int, item_ids: list[int], active: bool
) -> list[CatalogItem]:
    ids = sorted(set(item_ids))
    if not ids:
        raise CatalogError("item_ids must not be empty")
    rows = list(
        db.scalars(
            select(CatalogItem).where(
                CatalogItem.organization_id == organization_id, CatalogItem.id.in_(ids)
            )
        ).all()
    )
    if len(rows) != len(ids):
        raise CatalogNotFoundError("catalog item not found")
    for row in rows:
        row.active = active
        if not active:
            row.bookable = False
        row.version += 1
    return rows


def bulk_activate(db: Session, *, organization_id: int, item_ids: list[int]) -> list[CatalogItem]:
    return bulk_set_catalog_items_active(
        db, organization_id=organization_id, item_ids=item_ids, active=True
    )


def bulk_deactivate(db: Session, *, organization_id: int, item_ids: list[int]) -> list[CatalogItem]:
    return bulk_set_catalog_items_active(
        db, organization_id=organization_id, item_ids=item_ids, active=False
    )


def create_category(
    db: Session, *, organization_id: int, name: str, active: bool = True
) -> CatalogCategory:
    cleaned = name.strip()
    if not cleaned:
        raise CatalogError("category name is required")
    return CatalogCategory(organization_id=organization_id, name=cleaned, active=active)


def update_category(
    db: Session, *, organization_id: int, category_id: int, fields: dict[str, object]
) -> CatalogCategory:
    row = db.scalar(
        select(CatalogCategory).where(
            CatalogCategory.id == category_id, CatalogCategory.organization_id == organization_id
        )
    )
    if row is None:
        raise CatalogNotFoundError("catalog category not found")
    if "name" in fields and (not isinstance(fields["name"], str) or not fields["name"].strip()):
        raise CatalogError("category name is required")
    for field, value in fields.items():
        setattr(row, field, value.strip() if field == "name" and isinstance(value, str) else value)
    return row


def create_option(
    db: Session, *, item: CatalogItem, name: str, active: bool, metadata_json: dict[str, object]
) -> CatalogOption:
    cleaned = name.strip()
    if not cleaned:
        raise CatalogError("option name is required")
    return CatalogOption(
        catalog_item_id=item.id, name=cleaned, active=active, metadata_json=metadata_json
    )


def update_option(
    db: Session, *, item: CatalogItem, option_id: int, fields: dict[str, object]
) -> CatalogOption:
    row = db.scalar(
        select(CatalogOption).where(
            CatalogOption.id == option_id, CatalogOption.catalog_item_id == item.id
        )
    )
    if row is None:
        raise CatalogNotFoundError("catalog option not found")
    if "name" in fields and (not isinstance(fields["name"], str) or not fields["name"].strip()):
        raise CatalogError("option name is required")
    for field, value in fields.items():
        setattr(row, field, value.strip() if field == "name" and isinstance(value, str) else value)
    return row


def delete_option(db: Session, *, item: CatalogItem, option_id: int) -> None:
    row = db.scalar(
        select(CatalogOption).where(
            CatalogOption.id == option_id, CatalogOption.catalog_item_id == item.id
        )
    )
    if row is None:
        raise CatalogNotFoundError("catalog option not found")
    db.delete(row)


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
