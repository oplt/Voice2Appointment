"""Shared resource API helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Location, Reservation, ReservationResource, Resource

_FUTURE_BLOCKING_STATUSES = frozenset({"held", "confirmed", "pending", "pending_provider"})


def future_reservation_count(db: Session, *, organization_id: int, resource_id: int) -> int:
    now = datetime.now(timezone.utc)
    return int(
        db.scalar(
            select(func.count())
            .select_from(ReservationResource)
            .join(Reservation, Reservation.id == ReservationResource.reservation_id)
            .where(
                Reservation.organization_id == organization_id,
                ReservationResource.resource_id == resource_id,
                Reservation.status.in_(tuple(_FUTURE_BLOCKING_STATUSES)),
                Reservation.end_datetime > now,
            )
        )
        or 0
    )


def get_resource(db: Session, organization_id: int, resource_id: int) -> Resource:
    row = db.scalar(
        select(Resource).where(
            Resource.id == resource_id, Resource.organization_id == organization_id
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return row


def owned_location(db: Session, organization_id: int, location_id: int | None) -> None:
    if (
        location_id is not None
        and db.scalar(
            select(Location).where(
                Location.id == location_id, Location.organization_id == organization_id
            )
        )
        is None
    ):
        raise HTTPException(status_code=404, detail="Location not found")


def normalize_pair(left: int, right: int) -> tuple[int, int]:
    if left == right:
        raise HTTPException(status_code=422, detail="resource cannot be adjacent to itself")
    return (left, right) if left < right else (right, left)
