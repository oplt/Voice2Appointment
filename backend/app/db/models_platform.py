"""Platform/org capability ORM models (knowledge, entitlements, industry, waitlist, audit)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.model_base import JSON_TYPE, TimestampMixin, TZDateTime, _utcnow


class KnowledgeEntry(TimestampMixin, Base):
    __tablename__ = "knowledge_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict, server_default=text("'{}'"))


class FeatureEntitlement(TimestampMixin, Base):
    __tablename__ = "feature_entitlement"
    __table_args__ = (UniqueConstraint("organization_id", "feature", name="uq_feature_entitlement"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True)
    feature: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    limits_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict, server_default=text("'{}'"))


class IndustryProfile(TimestampMixin, Base):
    """Per-organization industry capability/policy surface (not a separate app)."""

    __tablename__ = "industry_profile"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_industry_profile_org"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True
    )
    industry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scheduling_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="single_resource")
    required_customer_fields: Mapped[list[Any]] = mapped_column(
        JSON_TYPE, nullable=False, default=list, server_default=text("'[]'")
    )
    required_booking_fields: Mapped[list[Any]] = mapped_column(
        JSON_TYPE, nullable=False, default=list, server_default=text("'[]'")
    )
    enabled_tools: Mapped[list[Any]] = mapped_column(
        JSON_TYPE, nullable=False, default=list, server_default=text("'[]'")
    )
    confirmation_policy: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE, nullable=False, default=dict, server_default=text("'{}'")
    )
    deposit_policy: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE, nullable=False, default=dict, server_default=text("'{}'")
    )
    handoff_policy: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE, nullable=False, default=dict, server_default=text("'{}'")
    )
    privacy_policy: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE, nullable=False, default=dict, server_default=text("'{}'")
    )
    terminology: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE, nullable=False, default=dict, server_default=text("'{}'")
    )
    flow_steps: Mapped[list[Any]] = mapped_column(
        JSON_TYPE, nullable=False, default=list, server_default=text("'[]'")
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE, nullable=False, default=dict, server_default=text("'{}'")
    )


class WaitlistEntry(TimestampMixin, Base):
    __tablename__ = "waitlist_entry"
    __table_args__ = (
        Index("ix_waitlist_org_status", "organization_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True
    )
    location_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("location.id"), nullable=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("customer.id"), nullable=True, index=True)
    catalog_item_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("catalog_item.id"), nullable=True)
    party_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    preferred_start: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    preferred_end: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="waiting")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE, nullable=False, default=dict, server_default=text("'{}'")
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("res_user.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict, server_default=text("'{}'"))
    occurred_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False, default=_utcnow)
