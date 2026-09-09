"""Reservation lifecycle idempotency and mutation guards."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import blake2b
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import AuditLog, Reservation, ReservationLifecycleOperation


class ReservationError(ValueError):
    """Reservation policy or state error."""


class ReservationConflictError(ReservationError):
    """Slot or hold is no longer available."""


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _lifecycle_key(operation: str, payload: dict[str, Any], key: str | None) -> str:
    if key:
        return key
    material = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":"))
    return blake2b(f"{operation}|{material}".encode(), digest_size=16).hexdigest()


def _begin_lifecycle_operation(
    db: Session,
    reservation: Reservation,
    *,
    operation: str,
    idempotency_key: str | None,
    payload: dict[str, Any],
) -> tuple[ReservationLifecycleOperation, bool]:
    """Create a durable mutation record, or return the original retry."""
    key = _lifecycle_key(operation, payload, idempotency_key)
    existing = db.scalar(
        select(ReservationLifecycleOperation).where(
            ReservationLifecycleOperation.reservation_id == reservation.id,
            ReservationLifecycleOperation.operation == operation,
            ReservationLifecycleOperation.idempotency_key == key,
        )
    )
    if existing is not None:
        return existing, False
    record = ReservationLifecycleOperation(
        organization_id=reservation.organization_id,
        reservation_id=reservation.id,
        operation=operation,
        idempotency_key=key,
        payload=payload,
        status="processing",
    )
    db.add(record)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(ReservationLifecycleOperation).where(
                ReservationLifecycleOperation.reservation_id == reservation.id,
                ReservationLifecycleOperation.operation == operation,
                ReservationLifecycleOperation.idempotency_key == key,
            )
        )
        if existing is not None:
            return existing, False
        raise
    return record, True


def _finish_lifecycle_operation(
    db: Session,
    reservation: Reservation,
    record: ReservationLifecycleOperation,
    *,
    actor_user_id: int | None,
) -> None:
    record.status = "applied"
    record.result = {
        **dict(record.result or {}),
        "reservation_status": reservation.status,
        "provider_sync_status": reservation.provider_sync_status,
    }
    db.add(
        AuditLog(
            organization_id=reservation.organization_id,
            actor_user_id=actor_user_id,
            action=f"reservation.{record.operation}",
            entity_type="reservation",
            entity_id=str(reservation.id),
            data={"idempotency_key": record.idempotency_key, **dict(record.payload)},
            occurred_at=_utcnow(),
        )
    )


def _require_mutable(reservation: Reservation) -> None:
    if reservation.status in {"cancelled", "expired", "failed"}:
        raise ReservationError(f"reservation is {reservation.status}")
    if reservation.status in {"pending_provider", "cancel_pending_provider"}:
        raise ReservationError("reservation provider operation already in progress")

