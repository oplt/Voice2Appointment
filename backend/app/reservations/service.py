"""Reservation hold, authoritative commit, and appointment-compatible finalize."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import blake2b
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.appointments.locking import SchedulingLockTarget, scheduling_lock
from app.core.feature_flags import require_reservation_domain
from app.db.models import (
    Appointment,
    CatalogItem,
    Customer,
    PriceBook,
    Reservation,
    ReservationLineItem,
    ReservationResource,
    User,
)
from app.pricing.service import active_price, snapshot_line_item
from app.reservations.allocation import AllocationError, allocate_resources
from app.reservations.availability import search_availability
from app.reservations.types import AvailabilityRequest, AvailabilityResult, ResourceAllocation
from app.resources.service import requirements_for_service

HOLD_TTL_SECONDS = 300
ProviderCreate = Callable[..., dict[str, Any]]


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


def build_reservation_idempotency_key(
    *,
    organization_id: int,
    catalog_item_id: int,
    start_utc: datetime,
    end_utc: datetime,
    party_size: int,
    customer_id: int | None = None,
) -> str:
    material = "|".join(
        str(part)
        for part in (
            organization_id,
            catalog_item_id,
            _aware(start_utc).isoformat(),
            _aware(end_utc).isoformat(),
            party_size,
            customer_id or "",
        )
    )
    return blake2b(material.encode(), digest_size=16).hexdigest()


def _lock_target(
    *,
    organization_id: int,
    location_id: int | None,
    start: datetime,
) -> SchedulingLockTarget:
    return SchedulingLockTarget(
        organization_id=organization_id,
        location_id=location_id,
        start_bucket=_aware(start).strftime("%Y%m%d%H"),
    )


def _persist_allocations(
    db: Session, reservation: Reservation, allocations: list[ResourceAllocation]
) -> None:
    reservation.allocation_json = {
        "resources": [
            {
                "resource_id": item.resource_id,
                "resource_name": item.resource_name,
                "resource_type": item.resource_type,
                "quantity": item.quantity,
            }
            for item in allocations
        ]
    }
    for item in allocations:
        db.add(
            ReservationResource(
                reservation_id=reservation.id,
                resource_id=item.resource_id,
                quantity=item.quantity,
            )
        )


def _snapshot_prices(
    db: Session,
    *,
    reservation: Reservation,
    catalog_item: CatalogItem,
    price_book_id: int | None,
) -> ReservationLineItem | None:
    book_id = price_book_id
    if book_id is None:
        book = db.scalar(
            select(PriceBook).where(
                PriceBook.organization_id == reservation.organization_id,
                PriceBook.active.is_(True),
            )
        )
        book_id = book.id if book is not None else None
    if book_id is None:
        return None
    price = active_price(
        db,
        price_book_id=book_id,
        catalog_item_id=catalog_item.id,
        location_id=reservation.location_id,
    )
    if price is None:
        return None
    line = snapshot_line_item(
        reservation_id=reservation.id, item=catalog_item, price=price, quantity=1
    )
    db.add(line)
    return line


def _resolve_duration(
    item: CatalogItem,
    start: datetime,
    end: datetime | None,
    *,
    duration_minutes: int | None = None,
) -> datetime:
    duration = duration_minutes if duration_minutes is not None else (item.duration_minutes or 30)
    if duration <= 0:
        raise ReservationError("duration_minutes must be positive")
    expected = start + timedelta(minutes=duration)
    if end is not None and _aware(end) != expected:
        raise ReservationError(
            f"{item.name} reservations must be {duration} minutes"
        )
    return expected


def find_availability(db: Session, request: AvailabilityRequest) -> AvailabilityResult:
    require_reservation_domain()
    return search_availability(db, request)


def hold_reservation(
    db: Session,
    *,
    organization_id: int,
    catalog_item_id: int,
    start_datetime: datetime,
    end_datetime: datetime | None = None,
    location_id: int | None = None,
    customer_id: int | None = None,
    party_size: int = 1,
    preferred_resource_ids: tuple[int, ...] = (),
    required_capabilities: tuple[str, ...] = (),
    price_book_id: int | None = None,
    scheduling_mode: str | None = None,
    hold_ttl_seconds: int = HOLD_TTL_SECONDS,
    idempotency_key: str | None = None,
    duration_minutes: int | None = None,
) -> Reservation:
    require_reservation_domain()
    """Acquire a short-lived authoritative hold after revalidating capacity."""
    if party_size <= 0:
        raise ReservationError("party_size must be positive")
    item = db.get(CatalogItem, catalog_item_id)
    if item is None or item.organization_id != organization_id:
        raise ReservationError("catalog item not found")
    if not item.active or not item.bookable:
        raise ReservationError("catalog item is not bookable")
    if customer_id is not None:
        customer = db.get(Customer, customer_id)
        if customer is None or customer.organization_id != organization_id:
            raise ReservationError("customer not found")

    start = _aware(start_datetime)
    end = _resolve_duration(
        item,
        start,
        _aware(end_datetime) if end_datetime else None,
        duration_minutes=duration_minutes,
    )
    key = idempotency_key or build_reservation_idempotency_key(
        organization_id=organization_id,
        catalog_item_id=catalog_item_id,
        start_utc=start,
        end_utc=end,
        party_size=party_size,
        customer_id=customer_id,
    )
    existing = db.scalar(
        select(Reservation).where(
            Reservation.organization_id == organization_id,
            Reservation.idempotency_key == key,
        )
    )
    if existing is not None:
        return existing

    requirements = requirements_for_service(db, item.id)
    occupied_start = start - timedelta(minutes=item.buffer_before_minutes or 0)
    occupied_end = end + timedelta(minutes=item.buffer_after_minutes or 0)
    target = _lock_target(
        organization_id=organization_id, location_id=location_id, start=start
    )
    with scheduling_lock(db, target):
        try:
            mode, allocations = allocate_resources(
                db,
                organization_id=organization_id,
                location_id=location_id,
                start=occupied_start,
                end=occupied_end,
                requirements=requirements,
                party_size=party_size,
                preferred_resource_ids=preferred_resource_ids,
                required_capabilities=required_capabilities,
                scheduling_mode=scheduling_mode,  # type: ignore[arg-type]
            )
        except AllocationError as exc:
            raise ReservationConflictError(str(exc)) from exc

        row = Reservation(
            organization_id=organization_id,
            location_id=location_id,
            customer_id=customer_id,
            catalog_item_id=item.id,
            scheduling_mode=mode,
            status="held",
            start_datetime=start,
            end_datetime=end,
            party_size=party_size,
            hold_expires_at=_utcnow() + timedelta(seconds=hold_ttl_seconds),
            idempotency_key=key,
            provider_sync_status="none",
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            existing = db.scalar(
                select(Reservation).where(
                    Reservation.organization_id == organization_id,
                    Reservation.idempotency_key == key,
                )
            )
            if existing is not None:
                return existing
            raise
        _persist_allocations(db, row, allocations)
        _snapshot_prices(
            db, reservation=row, catalog_item=item, price_book_id=price_book_id
        )
        db.commit()
        db.refresh(row)
        return row


def commit_reservation(
    db: Session,
    reservation_id: int,
    *,
    owner_user_id: int | None = None,
    sync_calendar: bool = False,
    provider_create: ProviderCreate | None = None,
    calendar_id: str = "primary",
) -> Reservation:
    """Verify hold, commit reservation, optionally bridge Appointment + provider sync."""
    require_reservation_domain()
    row = db.get(Reservation, reservation_id)
    if row is None:
        raise ReservationError("reservation not found")
    if row.status in {"confirmed", "pending_provider"}:
        return row
    if row.status == "cancelled":
        raise ReservationError("reservation is cancelled")
    if (
        row.status == "held"
        and row.hold_expires_at is not None
        and _aware(row.hold_expires_at) <= _utcnow()
    ):
        row.status = "expired"
        db.commit()
        raise ReservationConflictError("reservation hold expired")

    item = db.get(CatalogItem, row.catalog_item_id) if row.catalog_item_id else None
    requirements = requirements_for_service(db, item.id) if item is not None else []
    occupied_start = row.start_datetime - timedelta(
        minutes=(item.buffer_before_minutes if item is not None else 0) or 0
    )
    occupied_end = row.end_datetime + timedelta(
        minutes=(item.buffer_after_minutes if item is not None else 0) or 0
    )
    target = _lock_target(
        organization_id=row.organization_id,
        location_id=row.location_id,
        start=row.start_datetime,
    )
    pending_appointment_id: int | None = None
    with scheduling_lock(db, target):
        # Re-load under lock.
        row = db.get(Reservation, reservation_id)
        if row is None:
            raise ReservationError("reservation not found")
        if row.status in {"confirmed", "pending_provider"}:
            return row
        try:
            mode, allocations = allocate_resources(
                db,
                organization_id=row.organization_id,
                location_id=row.location_id,
                start=occupied_start,
                end=occupied_end,
                requirements=requirements,
                party_size=row.party_size,
                scheduling_mode=row.scheduling_mode,  # type: ignore[arg-type]
                exclude_reservation_id=row.id,
            )
        except AllocationError as exc:
            raise ReservationConflictError(str(exc)) from exc

        # Replace provisional allocation with authoritative one.
        for existing in list(
            db.scalars(
                select(ReservationResource).where(
                    ReservationResource.reservation_id == row.id
                )
            ).all()
        ):
            db.delete(existing)
        db.flush()
        row.scheduling_mode = mode
        _persist_allocations(db, row, allocations)

        if sync_calendar and owner_user_id is not None:
            user = db.get(User, owner_user_id)
            if user is None or user.organization_id not in (None, row.organization_id):
                raise ReservationError("owner user not found for organization")
            customer = db.get(Customer, row.customer_id) if row.customer_id else None
            appointment = Appointment(
                user_id=owner_user_id,
                organization_id=row.organization_id,
                summary=item.name if item is not None else "Reservation",
                start_datetime=row.start_datetime,
                end_datetime=row.end_datetime,
                timezone="UTC",
                client_name=customer.name if customer is not None else None,
                client_phone=customer.phone if customer is not None else None,
                client_email=customer.email if customer is not None else None,
                status="pending" if provider_create is not None else "confirmed",
                provider_sync_status=(
                    "pending_provider" if provider_create is not None else "confirmed"
                ),
                provider_operation="create" if provider_create is not None else None,
                provider_calendar_id=calendar_id,
                idempotency_key=f"reservation:{row.idempotency_key or row.id}",
            )
            db.add(appointment)
            db.flush()
            row.appointment_id = appointment.id
            if provider_create is not None:
                row.status = "pending_provider"
                row.provider_sync_status = "pending_provider"
                pending_appointment_id = appointment.id
            else:
                row.status = "confirmed"
                row.provider_sync_status = "confirmed"
        else:
            row.status = "confirmed"
            row.provider_sync_status = "none"

        row.hold_expires_at = None
        db.commit()
        db.refresh(row)

    if pending_appointment_id is not None and provider_create is not None:
        from app.appointments.provider_operations import complete_create

        appointment = complete_create(db, pending_appointment_id, provider_create)
        row = db.get(Reservation, reservation_id)
        assert row is not None
        if appointment.provider_sync_status == "confirmed":
            row.status = "confirmed"
            row.provider_sync_status = "confirmed"
            db.commit()
            db.refresh(row)
        elif appointment.provider_sync_status == "failed":
            row.status = "failed"
            row.provider_sync_status = "failed"
            db.commit()
            db.refresh(row)
    return row


def book_reservation(
    db: Session,
    *,
    organization_id: int,
    catalog_item_id: int,
    start_datetime: datetime,
    end_datetime: datetime | None = None,
    location_id: int | None = None,
    customer_id: int | None = None,
    party_size: int = 1,
    preferred_resource_ids: tuple[int, ...] = (),
    required_capabilities: tuple[str, ...] = (),
    price_book_id: int | None = None,
    scheduling_mode: str | None = None,
    idempotency_key: str | None = None,
    duration_minutes: int | None = None,
    owner_user_id: int | None = None,
    sync_calendar: bool = False,
    provider_create: ProviderCreate | None = None,
    calendar_id: str = "primary",
) -> Reservation:
    """Hold then immediately commit — one-shot booking path."""
    held = hold_reservation(
        db,
        organization_id=organization_id,
        catalog_item_id=catalog_item_id,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        location_id=location_id,
        customer_id=customer_id,
        party_size=party_size,
        preferred_resource_ids=preferred_resource_ids,
        required_capabilities=required_capabilities,
        price_book_id=price_book_id,
        scheduling_mode=scheduling_mode,
        idempotency_key=idempotency_key,
        duration_minutes=duration_minutes,
    )
    if held.status in {"confirmed", "pending_provider"}:
        return held
    return commit_reservation(
        db,
        held.id,
        owner_user_id=owner_user_id,
        sync_calendar=sync_calendar,
        provider_create=provider_create,
        calendar_id=calendar_id,
    )


def expire_stale_holds(db: Session, *, limit: int = 100) -> int:
    """Mark expired holds so capacity is released reliably."""
    now = _utcnow()
    rows = list(
        db.scalars(
            select(Reservation)
            .where(Reservation.status == "held", Reservation.hold_expires_at.is_not(None))
            .limit(limit * 4)
        ).all()
    )
    expired_rows = [
        row for row in rows if _aware(row.hold_expires_at) <= now  # type: ignore[arg-type]
    ][:limit]
    for row in expired_rows:
        row.status = "expired"
    if expired_rows:
        db.commit()
    return len(expired_rows)


def finalize_pending_reservations(
    db: Session,
    *,
    provider_create_for_user: Callable[[int], ProviderCreate | None] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Retry provider finalize for reservations linked to pending appointments."""
    rows = list(
        db.scalars(
            select(Reservation)
            .where(Reservation.status == "pending_provider")
            .limit(limit)
        ).all()
    )
    results: list[dict[str, Any]] = []
    for row in rows:
        if row.appointment_id is None or provider_create_for_user is None:
            results.append({"reservation_id": row.id, "result": "skipped"})
            continue
        appointment = db.get(Appointment, row.appointment_id)
        if appointment is None:
            results.append({"reservation_id": row.id, "result": "missing_appointment"})
            continue
        create = provider_create_for_user(appointment.user_id)
        if create is None:
            results.append({"reservation_id": row.id, "result": "no_provider"})
            continue
        from app.appointments.provider_operations import complete_create

        updated = complete_create(db, appointment.id, create)
        row = db.get(Reservation, row.id)
        assert row is not None
        if updated.provider_sync_status == "confirmed":
            row.status = "confirmed"
            row.provider_sync_status = "confirmed"
        elif updated.provider_sync_status == "failed":
            row.status = "failed"
            row.provider_sync_status = "failed"
        db.commit()
        results.append(
            {
                "reservation_id": row.id,
                "result": row.provider_sync_status,
                "appointment_id": updated.id,
            }
        )
    return results
