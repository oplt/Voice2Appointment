"""Tenant booking serialization helpers (PostgreSQL advisory locks)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import blake2b

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.metrics import metrics


@dataclass(frozen=True)
class SchedulingLockTarget:
    """The scheduling scope serialized while durable availability is decided.

    ``organization_id`` currently maps to the account owner.  The optional
    fields make the lock ready for location, resource, capacity-pool, and time
    range scheduling without coupling new callers to a user-id-only key.
    """

    organization_id: int
    location_id: int | None = None
    resource_id: int | None = None
    capacity_pool_id: int | None = None
    start_bucket: str | None = None


def _lock_key(target: SchedulingLockTarget) -> int:
    material = ":".join(
        str(value)
        for value in (
            "booking-v2",
            target.organization_id,
            target.location_id,
            target.resource_id,
            target.capacity_pool_id,
            target.start_bucket,
        )
    ).encode()
    # PostgreSQL advisory locks accept signed bigint values.  A deterministic
    # digest avoids Python's process-randomized ``hash`` and keeps the namespace
    # separate from unrelated advisory-lock users.
    return int.from_bytes(
        blake2b(material, digest_size=8).digest(), "big"
    ) & 0x7FFF_FFFF_FFFF_FFFF


@contextmanager
def scheduling_lock(db: Session, target: SchedulingLockTarget) -> Iterator[None]:
    """Serialize a short durable scheduling decision for the current transaction.

    PostgreSQL: transaction-scoped advisory lock.
    SQLite/other: no-op (tests rely on single-threaded StaticPool).
    """
    bind = db.get_bind()
    dialect = bind.dialect.name if bind is not None else ""
    if dialect == "postgresql":
        started = time.perf_counter()
        result = "acquired"
        try:
            db.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": _lock_key(target)},
            )
        except Exception:  # noqa: BLE001
            result = "failure"
            raise
        finally:
            metrics.observe(
                "booking_lock_wait_ms",
                (time.perf_counter() - started) * 1000.0,
                labels={"result": result},
            )
    yield


@contextmanager
def tenant_booking_lock(db: Session, user_id: int) -> Iterator[None]:
    """Backward-compatible account-wide scheduling lock."""
    with scheduling_lock(db, SchedulingLockTarget(organization_id=user_id)):
        yield
