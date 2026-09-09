"""Resource-scoped serialization for authoritative reservation allocation."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager

from sqlalchemy.orm import Session

from app.appointments.locking import SchedulingLockTarget, scheduling_lock


@contextmanager
def resource_scheduling_locks(
    db: Session,
    *,
    organization_id: int,
    resource_ids: tuple[int, ...],
) -> Iterator[None]:
    """Acquire resource advisory locks in a stable order for one allocation.

    The lock does not include a time bucket: overlapping reservations for the
    same resource must contend even when their start times cross an hour.
    """
    with ExitStack() as locks:
        for resource_id in sorted(set(resource_ids)):
            locks.enter_context(
                scheduling_lock(
                    db,
                    SchedulingLockTarget(
                        organization_id=organization_id,
                        resource_id=resource_id,
                    ),
                )
            )
        yield
