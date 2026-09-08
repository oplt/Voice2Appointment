"""Assign and resolve organization industry profiles + entitlements."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FeatureEntitlement, IndustryProfile, Organization
from app.industries.catalog import PROFILE_CATALOG, get_profile_spec
from app.industries.types import IndustryProfileSpec, IndustryType


class IndustryProfileError(ValueError):
    pass


def get_industry_profile(db: Session, organization_id: int) -> IndustryProfile | None:
    return db.scalar(
        select(IndustryProfile).where(IndustryProfile.organization_id == organization_id)
    )


def profile_spec_for_org(db: Session, organization_id: int) -> IndustryProfileSpec:
    row = get_industry_profile(db, organization_id)
    if row is None:
        return PROFILE_CATALOG["general"]
    return get_profile_spec(row.industry_type)


def _sync_entitlements(
    db: Session, *, organization_id: int, features: list[str]
) -> None:
    existing = {
        row.feature: row
        for row in db.scalars(
            select(FeatureEntitlement).where(
                FeatureEntitlement.organization_id == organization_id
            )
        ).all()
    }
    wanted = set(features)
    for feature in wanted:
        row = existing.get(feature)
        if row is None:
            db.add(
                FeatureEntitlement(
                    organization_id=organization_id, feature=feature, enabled=True
                )
            )
        else:
            row.enabled = True
    for feature, row in existing.items():
        if feature not in wanted and feature.startswith(("tool:", "cap:")):
            row.enabled = False


def assign_industry_profile(
    db: Session,
    *,
    organization_id: int,
    industry_type: IndustryType | str,
    overrides: dict[str, Any] | None = None,
) -> IndustryProfile:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise IndustryProfileError("organization not found")
    spec = get_profile_spec(industry_type)
    patch = overrides or {}

    row = get_industry_profile(db, organization_id)
    if row is None:
        row = IndustryProfile(organization_id=organization_id)
        db.add(row)

    row.industry_type = spec.industry_type
    row.scheduling_mode = str(patch.get("scheduling_mode", spec.scheduling_mode))
    row.required_customer_fields = list(
        patch.get("required_customer_fields", spec.required_customer_fields)
    )
    row.required_booking_fields = list(
        patch.get("required_booking_fields", spec.required_booking_fields)
    )
    row.enabled_tools = list(patch.get("enabled_tools", spec.enabled_tools))
    row.confirmation_policy = (
        patch.get("confirmation_policy") or spec.confirmation_policy.model_dump()
    )
    row.deposit_policy = patch.get("deposit_policy") or spec.deposit_policy.model_dump()
    row.handoff_policy = patch.get("handoff_policy") or spec.handoff_policy.model_dump()
    row.privacy_policy = patch.get("privacy_policy") or spec.privacy_policy.model_dump()
    row.terminology = dict(patch.get("terminology", spec.terminology))
    row.flow_steps = list(patch.get("flow_steps", spec.flow_steps))
    row.metadata_json = {
        **spec.metadata,
        "resource_types": spec.resource_types,
        "capabilities": spec.capabilities,
        **dict(patch.get("metadata_json", {})),
    }

    entitlement_features = [
        *[f"tool:{name}" for name in row.enabled_tools],
        *[f"cap:{name}" for name in spec.capabilities],
        f"industry:{spec.industry_type}",
    ]
    _sync_entitlements(db, organization_id=organization_id, features=entitlement_features)
    db.flush()
    return row


def enabled_tools(db: Session, organization_id: int) -> list[str]:
    row = get_industry_profile(db, organization_id)
    if row is not None:
        return list(row.enabled_tools or [])
    return list(PROFILE_CATALOG["general"].enabled_tools)


def tool_enabled(db: Session, organization_id: int, tool_name: str) -> bool:
    tools = enabled_tools(db, organization_id)
    if tool_name in tools:
        return True
    entitlement = db.scalar(
        select(FeatureEntitlement).where(
            FeatureEntitlement.organization_id == organization_id,
            FeatureEntitlement.feature == f"tool:{tool_name}",
            FeatureEntitlement.enabled.is_(True),
        )
    )
    return entitlement is not None


def has_capability(db: Session, organization_id: int, capability: str) -> bool:
    entitlement = db.scalar(
        select(FeatureEntitlement).where(
            FeatureEntitlement.organization_id == organization_id,
            FeatureEntitlement.feature == f"cap:{capability}",
            FeatureEntitlement.enabled.is_(True),
        )
    )
    if entitlement is not None:
        return True
    spec = profile_spec_for_org(db, organization_id)
    return capability in spec.capabilities


def validate_customer_fields(
    db: Session, organization_id: int, fields: dict[str, Any]
) -> list[str]:
    """Return missing required customer field names."""
    row = get_industry_profile(db, organization_id)
    required = list(
        (row.required_customer_fields if row is not None else None)
        or PROFILE_CATALOG["general"].required_customer_fields
    )
    missing = []
    for name in required:
        value = fields.get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(name)
    return missing


def validate_booking_fields(
    db: Session, organization_id: int, fields: dict[str, Any]
) -> list[str]:
    row = get_industry_profile(db, organization_id)
    required = list(
        (row.required_booking_fields if row is not None else None)
        or PROFILE_CATALOG["general"].required_booking_fields
    )
    missing = []
    for name in required:
        value = fields.get(name)
        if value is None or value is False or (isinstance(value, str) and not value.strip()):
            missing.append(name)
    return missing


def sync_calendar_for_org(db: Session, organization_id: int) -> bool:
    """Restaurant capacity bookings must not become generic calendar events."""
    spec = profile_spec_for_org(db, organization_id)
    if spec.industry_type == "restaurant":
        return False
    return bool(spec.metadata.get("sync_calendar", True))
