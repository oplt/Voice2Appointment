"""Clinic compliance hooks — lightweight audit and consent helpers.

This module is **not** a regulatory certification (HIPAA, HITECH, or otherwise).
``PrivacyPolicy.compliance_claimed`` remains False by default and must stay
False unless an independent security/regulatory assessment completes. These
helpers only record operational audit rows and read customer consent flags.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AuditLog, Customer
from app.industries.clinic import redact_clinic_payload


def record_clinic_audit(
    db: Session,
    organization_id: int,
    *,
    actor_user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    data: dict[str, Any] | None = None,
) -> AuditLog:
    """Write a redacted clinic AuditLog row (administrative scheduling only)."""
    safe = redact_clinic_payload(dict(data or {}))
    row = AuditLog(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        data=safe,
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


def require_consent_flag(
    customer: Customer | None, flag: str, *, default: bool = False
) -> bool:
    """Return whether ``customer.consent_preferences[flag]`` is truthy."""
    if customer is None:
        return default
    prefs = customer.consent_preferences or {}
    if not isinstance(prefs, dict):
        return default
    if flag not in prefs:
        return default
    value = prefs.get(flag)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)
