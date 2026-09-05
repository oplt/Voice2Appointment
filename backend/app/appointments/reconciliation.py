"""Recovery of durable appointment provider operations."""

from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from app.appointments.provider_operations import (
    _MAX_ATTEMPTS,
    _claim_attempt,
    _perform_cancel,
    _perform_reschedule,
    _record_failure,
    complete_create,
)
from app.db.models import Appointment

ProviderCall = Callable[..., Any]


def reconcile_pending_appointment(
    db: Session,
    row: Appointment,
    *,
    provider_create: ProviderCall | None = None,
    provider_update: ProviderCall | None = None,
    provider_delete: ProviderCall | None = None,
) -> dict[str, Any]:
    if row.provider_sync_status != "pending_provider":
        return {"id": row.id, "action": "skip"}
    operation = row.provider_operation or "create"
    if row.provider_attempt_count >= _MAX_ATTEMPTS:
        row.provider_sync_status = "failed"
        if operation == "create":
            row.status = "failed"
        row.provider_next_retry_at = None
        db.commit()
        return {"id": row.id, "action": "failed", "operation": operation}
    hook = {
        "create": provider_create,
        "reschedule": provider_update,
        "cancel": provider_delete,
    }.get(operation)
    if hook is None:
        claimed = _claim_attempt(db, row.id)
        if claimed is None:
            return {"id": row.id, "action": "leased", "operation": operation}
        _record_failure(db, row.id, RuntimeError("provider hook unavailable"))
        db.expire_all()
        current = db.get(Appointment, row.id)
        action = "failed" if current and current.provider_sync_status == "failed" else "retry"
        return {"id": row.id, "action": action, "operation": operation}
    try:
        if operation == "create":
            result = complete_create(db, row, hook)
        elif operation == "reschedule":
            result = _perform_reschedule(db, row, hook)
        elif operation == "cancel":
            result = _perform_cancel(db, row, hook)
        else:
            raise RuntimeError("unknown provider operation")
    except Exception:
        return {"id": row.id, "action": "retry", "operation": operation}
    action = "finalized" if result.provider_sync_status == "confirmed" else "leased"
    return {"id": row.id, "action": action, "operation": operation}
