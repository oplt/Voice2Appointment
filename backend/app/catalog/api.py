"""Organization-scoped catalog and pricing API."""

from __future__ import annotations

from typing import Any, Literal, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require_db
from app.catalog import service as catalog_service
from app.catalog.schemas import (
    BulkActiveIn,
    CategoryIn,
    CategoryOut,
    CategoryPatch,
    DuplicateItemIn,
    ItemIn,
    ItemOut,
    ItemPageOut,
    ItemPatch,
    OptionIn,
    OptionOut,
    OptionPatch,
    ResourceRequirementIn,
    ResourceRequirementOut,
)
from app.core.feature_flags import require_catalog_domain
from app.db.models import CatalogCategory, CatalogItem, CatalogOption
from app.resources.service import replace_service_requirements, requirements_for_service
from app.tenancy.api import OrganizationId, require_domain_permission

router = APIRouter(
    tags=["catalog"],
    dependencies=[Depends(require_catalog_domain), Depends(require_domain_permission("catalog"))],
)

def _owned_item(db: Session, organization_id: int, item_id: int) -> CatalogItem:
    try:
        return catalog_service.get_catalog_item(
            db, organization_id=organization_id, item_id=item_id
        )
    except catalog_service.CatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Catalog item not found") from exc


def _catalog_http(exc: Exception) -> NoReturn:
    if isinstance(exc, catalog_service.CatalogNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, catalog_service.CatalogConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, catalog_service.CatalogError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


@router.get("/catalog/categories", response_model=list[CategoryOut])
def list_categories(
    organization_id: OrganizationId, db: Session = Depends(require_db)
) -> list[CatalogCategory]:
    return list(
        db.scalars(
            select(CatalogCategory)
            .where(CatalogCategory.organization_id == organization_id)
            .order_by(CatalogCategory.name)
        ).all()
    )


@router.post("/catalog/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryIn, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> CatalogCategory:
    try:
        row = catalog_service.create_category(
            db, organization_id=organization_id, **payload.model_dump()
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    except Exception as exc:
        db.rollback()
        _catalog_http(exc)


@router.patch("/catalog/categories/{category_id}", response_model=CategoryOut)
def patch_category(
    category_id: int,
    payload: CategoryPatch,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> CatalogCategory:
    try:
        row = catalog_service.update_category(
            db,
            organization_id=organization_id,
            category_id=category_id,
            fields=payload.model_dump(exclude_unset=True),
        )
        db.commit()
        db.refresh(row)
        return row
    except Exception as exc:
        db.rollback()
        _catalog_http(exc)


@router.get("/catalog/items", response_model=ItemPageOut)
def list_items(
    organization_id: OrganizationId,
    active: bool | None = Query(None),
    query: str | None = Query(None, max_length=255),
    category_id: int | None = Query(None),
    kind: Literal["service", "product", "addon", "package"] | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(require_db),
) -> ItemPageOut:
    try:
        items, total = catalog_service.list_catalog_items(
            db,
            organization_id=organization_id,
            query=query,
            category_id=category_id,
            kind=kind,
            active=active,
            limit=limit,
            offset=offset,
        )
        return ItemPageOut(
            items=[ItemOut.model_validate(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        _catalog_http(exc)


@router.post("/catalog/items", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
def create_item(
    payload: ItemIn, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> CatalogItem:
    values = payload.model_dump()
    if (
        values["category_id"] is not None
        and db.scalar(
            select(CatalogCategory).where(
                CatalogCategory.id == values["category_id"],
                CatalogCategory.organization_id == organization_id,
            )
        )
        is None
    ):
        raise HTTPException(status_code=404, detail="Catalog category not found")
    try:
        row = catalog_service.create_catalog_item(db, organization_id=organization_id, **values)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    except Exception as exc:
        db.rollback()
        _catalog_http(exc)


@router.get("/catalog/items/{item_id}", response_model=ItemOut)
def get_item(
    item_id: int, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> CatalogItem:
    return _owned_item(db, organization_id, item_id)


@router.patch("/catalog/items/{item_id}", response_model=ItemOut)
def patch_item(
    item_id: int,
    payload: ItemPatch,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> CatalogItem:
    values = payload.model_dump(exclude_unset=True)
    category_id = values.get("category_id")
    if (
        category_id is not None
        and db.scalar(
            select(CatalogCategory).where(
                CatalogCategory.id == category_id,
                CatalogCategory.organization_id == organization_id,
            )
        )
        is None
    ):
        raise HTTPException(status_code=404, detail="Catalog category not found")
    expected_version = values.pop("expected_version")
    try:
        row = catalog_service.update_catalog_item(
            db,
            organization_id=organization_id,
            item_id=item_id,
            expected_version=expected_version,
            fields=values,
        )
        db.commit()
        db.refresh(row)
        return row
    except Exception as exc:
        db.rollback()
        _catalog_http(exc)


@router.post("/catalog/items/{item_id}/archive", response_model=ItemOut)
def archive_item(
    item_id: int,
    organization_id: OrganizationId,
    expected_version: int = Query(ge=1),
    db: Session = Depends(require_db),
) -> CatalogItem:
    try:
        row = catalog_service.archive_catalog_item(
            db, organization_id=organization_id, item_id=item_id, expected_version=expected_version
        )
        db.commit()
        db.refresh(row)
        return row
    except Exception as exc:
        db.rollback()
        _catalog_http(exc)


@router.post(
    "/catalog/items/{item_id}/duplicate",
    response_model=ItemOut,
    status_code=status.HTTP_201_CREATED,
)
def duplicate_item(
    item_id: int,
    payload: DuplicateItemIn,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> CatalogItem:
    try:
        row = catalog_service.duplicate_catalog_item(
            db, organization_id=organization_id, item_id=item_id, name=payload.name
        )
        db.commit()
        db.refresh(row)
        return row
    except Exception as exc:
        db.rollback()
        _catalog_http(exc)


@router.post("/catalog/bulk-activate", response_model=list[ItemOut])
def bulk_activate(
    payload: BulkActiveIn, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> list[CatalogItem]:
    try:
        rows = catalog_service.bulk_set_catalog_items_active(
            db, organization_id=organization_id, item_ids=payload.item_ids, active=True
        )
        db.commit()
        return rows
    except Exception as exc:
        db.rollback()
        _catalog_http(exc)


@router.post("/catalog/bulk-deactivate", response_model=list[ItemOut])
def bulk_deactivate(
    payload: BulkActiveIn, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> list[CatalogItem]:
    try:
        rows = catalog_service.bulk_set_catalog_items_active(
            db, organization_id=organization_id, item_ids=payload.item_ids, active=False
        )
        db.commit()
        return rows
    except Exception as exc:
        db.rollback()
        _catalog_http(exc)


@router.get("/catalog/items/{item_id}/options", response_model=list[OptionOut])
def list_options(
    item_id: int, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> list[CatalogOption]:
    _owned_item(db, organization_id, item_id)
    return list(
        db.scalars(select(CatalogOption).where(CatalogOption.catalog_item_id == item_id)).all()
    )


@router.post(
    "/catalog/items/{item_id}/options",
    response_model=OptionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_option(
    item_id: int,
    payload: OptionIn,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> CatalogOption:
    item = _owned_item(db, organization_id, item_id)
    try:
        row = catalog_service.create_option(db, item=item, **payload.model_dump())
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    except Exception as exc:
        db.rollback()
        _catalog_http(exc)


@router.patch("/catalog/items/{item_id}/options/{option_id}", response_model=OptionOut)
def patch_option(
    item_id: int,
    option_id: int,
    payload: OptionPatch,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> CatalogOption:
    item = _owned_item(db, organization_id, item_id)
    try:
        row = catalog_service.update_option(
            db, item=item, option_id=option_id, fields=payload.model_dump(exclude_unset=True)
        )
        db.commit()
        db.refresh(row)
        return row
    except Exception as exc:
        db.rollback()
        _catalog_http(exc)


@router.delete(
    "/catalog/items/{item_id}/options/{option_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_option(
    item_id: int, option_id: int, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> None:
    item = _owned_item(db, organization_id, item_id)
    try:
        catalog_service.delete_option(db, item=item, option_id=option_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        _catalog_http(exc)


@router.get(
    "/catalog/items/{item_id}/resource-requirements", response_model=list[ResourceRequirementOut]
)
def list_resource_requirements(
    item_id: int, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> list[Any]:
    _owned_item(db, organization_id, item_id)
    return requirements_for_service(db, item_id)


@router.put(
    "/catalog/items/{item_id}/resource-requirements", response_model=list[ResourceRequirementOut]
)
def put_resource_requirements(
    item_id: int,
    payload: list[ResourceRequirementIn],
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> list[Any]:
    try:
        rows = replace_service_requirements(
            db,
            organization_id=organization_id,
            catalog_item_id=item_id,
            requirements=[item.model_dump() for item in payload],
        )
        db.commit()
        return rows
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
