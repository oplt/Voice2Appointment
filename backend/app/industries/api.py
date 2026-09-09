"""Knowledge-base and industry-profile HTTP API."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require_db
from app.db.models import IndustryProfile, KnowledgeEntry
from app.industries.service import assign_industry_profile, get_industry_profile
from app.tenancy.api import OrganizationId, require_org_permission

router = APIRouter(
    tags=["industry", "knowledge"],
    dependencies=[Depends(require_org_permission("organization.manage"))],
)


class KnowledgeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    active: bool = True
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class KnowledgePatch(KnowledgeIn):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1)


class KnowledgeOut(KnowledgeIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class IndustryProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    industry_type: Literal["clinic", "restaurant", "salon", "general"]
    overrides: dict[str, Any] = Field(default_factory=dict)


class IndustryProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    industry_type: str
    scheduling_mode: str
    required_customer_fields: list[Any]
    required_booking_fields: list[Any]
    enabled_tools: list[Any]
    confirmation_policy: dict[str, Any]
    deposit_policy: dict[str, Any]
    handoff_policy: dict[str, Any]
    privacy_policy: dict[str, Any]
    terminology: dict[str, Any]
    flow_steps: list[Any]
    metadata_json: dict[str, Any]


@router.get("/knowledge", response_model=list[KnowledgeOut])
def list_knowledge(
    organization_id: OrganizationId, db: Session = Depends(require_db)
) -> list[KnowledgeEntry]:
    return list(
        db.scalars(
            select(KnowledgeEntry)
            .where(KnowledgeEntry.organization_id == organization_id)
            .order_by(KnowledgeEntry.title)
        ).all()
    )


@router.post("/knowledge", response_model=KnowledgeOut, status_code=status.HTTP_201_CREATED)
def create_knowledge(
    payload: KnowledgeIn, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> KnowledgeEntry:
    row = KnowledgeEntry(organization_id=organization_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/knowledge/{entry_id}", response_model=KnowledgeOut)
def patch_knowledge(
    entry_id: int,
    payload: KnowledgePatch,
    organization_id: OrganizationId,
    db: Session = Depends(require_db),
) -> KnowledgeEntry:
    row = db.scalar(
        select(KnowledgeEntry).where(
            KnowledgeEntry.id == entry_id, KnowledgeEntry.organization_id == organization_id
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


@router.get("/industry-profile", response_model=IndustryProfileOut | None)
def get_profile(
    organization_id: OrganizationId, db: Session = Depends(require_db)
) -> IndustryProfile | None:
    return get_industry_profile(db, organization_id)


@router.put("/industry-profile", response_model=IndustryProfileOut)
def put_profile(
    payload: IndustryProfileIn, organization_id: OrganizationId, db: Session = Depends(require_db)
) -> IndustryProfile:
    try:
        row = assign_industry_profile(
            db,
            organization_id=organization_id,
            industry_type=payload.industry_type,
            overrides=payload.overrides,
        )
        db.commit()
        db.refresh(row)
        return row
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
