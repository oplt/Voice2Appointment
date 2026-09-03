"""Tenant booking serialization helpers (PostgreSQL advisory locks)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import Session


def _lock_key(user_id: int) -> int:
    # Stable 63-bit key: namespace bookings + tenant id.
    return (0xB00A_0000_0000_0000 | (int(user_id) & 0xFFFF_FFFF)) & 0x7FFF_FFFF_FFFF_FFFF


@contextmanager
def tenant_booking_lock(db: Session, user_id: int) -> Iterator[None]:
    """Serialize booking mutations per tenant for the current transaction.

    PostgreSQL: transaction-scoped advisory lock.
    SQLite/other: no-op (tests rely on single-threaded StaticPool).
    """
    bind = db.get_bind()
    dialect = bind.dialect.name if bind is not None else ""
    if dialect == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": _lock_key(user_id)},
        )
    yield
