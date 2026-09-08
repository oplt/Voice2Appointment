"""Clinic / hospital profile helpers — administrative scheduling only."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CatalogCategory, CatalogItem, Resource, ResourceCapability
from app.industries.ehr import EHRPort, get_ehr_adapter

# Pattern hints that the caller is seeking diagnosis/treatment advice.
_DIAGNOSIS_HINTS = re.compile(
    r"\b("
    r"diagnos\w*|prescrib\w*|treat my|what(?:'s| is) wrong|medical advice|"
    r"do i have|is this cancer|should i take"
    r")\b",
    re.IGNORECASE,
)


class ClinicSafetyError(ValueError):
    """Caller crossed the administrative-scheduling safety gate."""


def emergency_safety_gate(utterance: str) -> dict[str, Any]:
    """Gate medical diagnosis/treatment asks; escalate emergencies to handoff.

    Does not provide clinical advice. Never claims regulatory compliance.
    """
    text = (utterance or "").strip()
    lower = text.casefold()
    emergency = any(
        token in lower
        for token in (
            "emergency",
            "chest pain",
            "can't breathe",
            "cannot breathe",
            "unconscious",
            "stroke",
            "overdose",
            "suicid",
        )
    )
    if emergency:
        return {
            "allowed": False,
            "reason": "emergency_escalation",
            "action": "request_human_handoff",
            "message": "For emergencies, please contact local emergency services or request a human transfer.",
        }
    if _DIAGNOSIS_HINTS.search(text):
        raise ClinicSafetyError(
            "This assistant only schedules administrative appointments and "
            "cannot provide diagnosis or treatment recommendations."
        )
    return {"allowed": True, "reason": "administrative_ok", "action": "continue"}


def list_specialties(db: Session, organization_id: int) -> list[CatalogCategory]:
    return list(
        db.scalars(
            select(CatalogCategory).where(
                CatalogCategory.organization_id == organization_id,
                CatalogCategory.active.is_(True),
            )
        ).all()
    )


def list_visit_types(
    db: Session, organization_id: int, *, specialty: str | None = None
) -> list[CatalogItem]:
    stmt = select(CatalogItem).where(
        CatalogItem.organization_id == organization_id,
        CatalogItem.active.is_(True),
        CatalogItem.bookable.is_(True),
        CatalogItem.kind == "service",
    )
    items = list(db.scalars(stmt).all())
    if specialty is None:
        return items
    wanted = specialty.casefold()
    return [
        item
        for item in items
        if str((item.metadata_json or {}).get("specialty", "")).casefold() == wanted
    ]


def requires_referral(item: CatalogItem) -> bool:
    return bool((item.metadata_json or {}).get("requires_referral"))


def list_practitioners(
    db: Session,
    organization_id: int,
    *,
    location_id: int | None = None,
    capability: str | None = None,
) -> list[Resource]:
    stmt = select(Resource).where(
        Resource.organization_id == organization_id,
        Resource.active.is_(True),
        Resource.resource_type == "practitioner",
    )
    if location_id is not None:
        stmt = stmt.where(Resource.location_id == location_id)
    resources = list(db.scalars(stmt).all())
    if capability is None:
        return resources
    rows = db.execute(
        select(ResourceCapability.resource_id, ResourceCapability.capability).where(
            ResourceCapability.resource_id.in_([r.id for r in resources] or [-1])
        )
    )
    by_resource: dict[int, set[str]] = {}
    for resource_id, cap in rows:
        by_resource.setdefault(int(resource_id), set()).add(str(cap).casefold())
    wanted = capability.casefold()
    return [r for r in resources if wanted in by_resource.get(r.id, set())]


def redact_clinic_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Strip clinical/medical keys before analytics or ordinary logs."""
    blocked = {
        "diagnosis",
        "symptoms",
        "medication",
        "clinical_notes",
        "ehr_payload",
        "treatment",
    }
    return {key: value for key, value in data.items() if key.casefold() not in blocked}


def ehr_lookup_patient(
    *,
    organization_id: int,
    phone: str | None,
    email: str | None,
    adapter: EHRPort | None = None,
):
    return (adapter or get_ehr_adapter()).lookup_patient(
        organization_id=organization_id, phone=phone, email=email
    )
