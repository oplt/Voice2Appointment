"""Reservation hold, authoritative commit, and appointment-compatible finalize."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from hashlib import blake2b
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.feature_flags import require_reservation_domain
from app.db.models import (
    Appointment,
    AuditLog,
    CatalogItem,
    Customer,
    PriceBook,
    Reservation,
    ReservationLifecycleOperation,
    ReservationLineItem,
    ReservationResource,
    Resource,
    User,
)
from app.pricing.service import active_price, snapshot_line_item
from app.reservations.allocation import (
    AllocationError,
    allocate_resources,
    matching_resource_ids,
)
from app.reservations.availability import search_availability
from app.reservations.locking import resource_scheduling_locks as scheduling_lock
from app.reservations.persistence import persist_allocations as _persist_allocations
from app.reservations.persistence import snapshot_prices as _snapshot_prices
from app.reservations.types import AvailabilityRequest, AvailabilityResult
from app.resources.service import requirements_for_service

HOLD_TTL_SECONDS = 300
ProviderCreate = Callable[..., dict[str, Any]]
ProviderDelete = Callable[..., Any]
ProviderUpdate = Callable[..., Any]


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
    channel: str | None = None,
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
            channel or "",
        )
    )
    return blake2b(material.encode(), digest_size=16).hexdigest()


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
    channel: str | None = None,
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
        channel=channel,
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
    lock_resource_ids = matching_resource_ids(
        db,
        organization_id=organization_id,
        location_id=location_id,
        requirements=requirements,
        preferred_resource_ids=preferred_resource_ids,
        required_capabilities=required_capabilities,
    )
    with scheduling_lock(
        db, organization_id=organization_id, resource_ids=lock_resource_ids
    ):
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
            db,
            reservation=row,
            catalog_item=item,
            price_book_id=price_book_id,
            channel=channel,
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
    lock_resource_ids = matching_resource_ids(
        db,
        organization_id=row.organization_id,
        location_id=row.location_id,
        requirements=requirements,
    )
    pending_appointment_id: int | None = None
    with scheduling_lock(
        db, organization_id=row.organization_id, resource_ids=lock_resource_ids
    ):
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
    channel: str | None = None,
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
        channel=channel,
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


def _item_for_reservation(db: Session, reservation: Reservation) -> CatalogItem:
    item = db.get(CatalogItem, reservation.catalog_item_id)
    if item is None or item.organization_id != reservation.organization_id:
        raise ReservationError("catalog item not found")
    return item


def _reallocate_reservation(
    db: Session,
    reservation: Reservation,
    *,
    item: CatalogItem,
    start: datetime,
    end: datetime,
    party_size: int,
    preferred_resource_ids: tuple[int, ...] = (),
    required_resource_ids: tuple[int, ...] = (),
) -> None:
    requirements = requirements_for_service(db, item.id)
    occupied_start = start - timedelta(minutes=item.buffer_before_minutes or 0)
    occupied_end = end + timedelta(minutes=item.buffer_after_minutes or 0)
    candidates = matching_resource_ids(
        db,
        organization_id=reservation.organization_id,
        location_id=reservation.location_id,
        requirements=requirements,
        preferred_resource_ids=preferred_resource_ids,
    )
    existing_ids = tuple(
        db.scalars(
            select(ReservationResource.resource_id).where(
                ReservationResource.reservation_id == reservation.id
            )
        ).all()
    )
    with scheduling_lock(
        db,
        organization_id=reservation.organization_id,
        resource_ids=tuple(sorted(set(candidates) | set(existing_ids))),
    ):
        try:
            mode, allocations = allocate_resources(
                db,
                organization_id=reservation.organization_id,
                location_id=reservation.location_id,
                start=occupied_start,
                end=occupied_end,
                requirements=requirements,
                party_size=party_size,
                preferred_resource_ids=preferred_resource_ids,
                allowed_resource_ids=required_resource_ids,
                scheduling_mode=reservation.scheduling_mode,  # type: ignore[arg-type]
                exclude_reservation_id=reservation.id,
            )
        except AllocationError as exc:
            raise ReservationConflictError(str(exc)) from exc
        allocated_ids = {allocation.resource_id for allocation in allocations}
        if not set(required_resource_ids).issubset(allocated_ids):
            raise ReservationConflictError("requested resource is unavailable")
        for resource in db.scalars(
            select(ReservationResource).where(
                ReservationResource.reservation_id == reservation.id
            )
        ).all():
            db.delete(resource)
        db.flush()
        reservation.scheduling_mode = mode
        _persist_allocations(db, reservation, allocations)


def _replace_base_price_snapshot(
    db: Session,
    reservation: Reservation,
    *,
    old_catalog_item_id: int | None,
    item: CatalogItem,
    price_book_id: int | None,
    channel: str | None,
) -> None:
    if old_catalog_item_id is not None:
        for line in db.scalars(
            select(ReservationLineItem).where(
                ReservationLineItem.reservation_id == reservation.id,
                ReservationLineItem.catalog_item_id == old_catalog_item_id,
            )
        ).all():
            db.delete(line)
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
        return
    price = active_price(
        db,
        price_book_id=book_id,
        catalog_item_id=item.id,
        location_id=reservation.location_id,
        channel=channel,
    )
    if price is None:
        raise ReservationError("no active price for catalog item")
    db.add(snapshot_line_item(reservation_id=reservation.id, item=item, price=price))


def _line_snapshot(line: ReservationLineItem) -> dict[str, Any]:
    return {
        "catalog_item_id": line.catalog_item_id,
        "item_name": line.item_name,
        "quantity": line.quantity,
        "unit_price_minor": line.unit_price_minor,
        "currency": line.currency,
        "tax_metadata": dict(line.tax_metadata or {}),
    }


def _restore_reschedule_failure(
    db: Session, reservation: Reservation, payload: dict[str, Any]
) -> bool:
    """Put a provider-rejected reschedule back on its previously held slot."""
    item = db.get(CatalogItem, payload.get("old_catalog_item_id"))
    if item is None:
        return False
    old_start = datetime.fromisoformat(str(payload["old_start_datetime"]))
    old_end = datetime.fromisoformat(str(payload["old_end_datetime"]))
    old_party_size = int(payload.get("old_party_size", reservation.party_size))
    current_item_id = reservation.catalog_item_id
    current_start = reservation.start_datetime
    current_end = reservation.end_datetime
    current_party_size = reservation.party_size
    reservation.catalog_item_id = item.id
    reservation.start_datetime = old_start
    reservation.end_datetime = old_end
    reservation.party_size = old_party_size
    try:
        _reallocate_reservation(
            db,
            reservation,
            item=item,
            start=old_start,
            end=old_end,
            party_size=old_party_size,
        )
    except ReservationConflictError:
        reservation.catalog_item_id = current_item_id
        reservation.start_datetime = current_start
        reservation.end_datetime = current_end
        reservation.party_size = current_party_size
        return False
    if int(payload.get("catalog_item_id", item.id)) != item.id:
        for line in db.scalars(
            select(ReservationLineItem).where(
                ReservationLineItem.reservation_id == reservation.id,
                ReservationLineItem.catalog_item_id == payload.get("catalog_item_id"),
            )
        ).all():
            db.delete(line)
        for saved in payload.get("old_service_lines", []):
            db.add(ReservationLineItem(reservation_id=reservation.id, **saved))
    return True


def _stage_lifecycle_notification(
    db: Session,
    reservation: Reservation,
    *,
    kind: str,
    fingerprint: str | None = None,
) -> None:
    """Stage outbox intents when a reservation mutation has a linked appointment."""
    if not reservation.appointment_id:
        return
    appointment = db.get(Appointment, reservation.appointment_id)
    if appointment is None:
        return
    from app.notifications.service import stage_reservation_lifecycle_notification

    stage_reservation_lifecycle_notification(
        db, appointment, kind=kind, fingerprint=fingerprint
    )


def cancel_reservation(
    db: Session,
    reservation_id: int,
    *,
    actor_user_id: int | None = None,
    reason: str | None = None,
    provider_delete: ProviderDelete | None = None,
    idempotency_key: str | None = None,
) -> Reservation:
    """Cancel locally only after the linked calendar cancellation is durable."""
    require_reservation_domain()
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise ReservationError("reservation not found")
    payload = {"reason": reason or ""}
    record, started = _begin_lifecycle_operation(
        db, reservation, operation="cancel", idempotency_key=idempotency_key, payload=payload
    )
    if not started:
        return reservation
    if reservation.status == "cancelled":
        _finish_lifecycle_operation(db, reservation, record, actor_user_id=actor_user_id)
        db.commit()
        return reservation
    _require_mutable(reservation)
    appointment = db.get(Appointment, reservation.appointment_id) if reservation.appointment_id else None
    if appointment is not None:
        from app.appointments.provider_operations import cancel_appointment

        appointment = cancel_appointment(
            db,
            appointment.user_id,
            appointment_id=appointment.id,
            reason=reason,
            provider_delete=provider_delete,
        )
        if appointment.provider_sync_status == "pending_provider":
            reservation.status = "cancel_pending_provider"
            reservation.provider_sync_status = "pending_provider"
        elif appointment.status == "cancelled":
            reservation.status = "cancelled"
            reservation.provider_sync_status = "confirmed"
        else:
            reservation.provider_sync_status = appointment.provider_sync_status
    else:
        reservation.status = "cancelled"
        reservation.provider_sync_status = "none"
    _stage_lifecycle_notification(
        db, reservation, kind="cancel", fingerprint=idempotency_key or record.idempotency_key
    )
    _finish_lifecycle_operation(db, reservation, record, actor_user_id=actor_user_id)
    db.commit()
    db.refresh(reservation)
    return reservation


def reschedule_reservation(
    db: Session,
    reservation_id: int,
    *,
    start_datetime: datetime,
    end_datetime: datetime | None = None,
    catalog_item_id: int | None = None,
    party_size: int | None = None,
    price_book_id: int | None = None,
    channel: str | None = None,
    preferred_resource_ids: tuple[int, ...] = (),
    actor_user_id: int | None = None,
    provider_update: ProviderUpdate | None = None,
    idempotency_key: str | None = None,
) -> Reservation:
    """Revalidate resources, then synchronize a linked calendar appointment."""
    require_reservation_domain()
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise ReservationError("reservation not found")
    old_item = _item_for_reservation(db, reservation)
    item = db.get(CatalogItem, catalog_item_id) if catalog_item_id is not None else old_item
    if item is None or item.organization_id != reservation.organization_id or not item.bookable:
        raise ReservationError("catalog item is not bookable")
    new_start = _aware(start_datetime)
    new_end = _resolve_duration(item, new_start, _aware(end_datetime) if end_datetime else None)
    new_party_size = party_size if party_size is not None else reservation.party_size
    if new_party_size <= 0:
        raise ReservationError("party_size must be positive")
    payload = {
        "old_start_datetime": reservation.start_datetime.isoformat(),
        "old_end_datetime": reservation.end_datetime.isoformat(),
        "old_catalog_item_id": old_item.id,
        "old_party_size": reservation.party_size,
        "old_service_lines": [
            _line_snapshot(line)
            for line in db.scalars(
                select(ReservationLineItem).where(
                    ReservationLineItem.reservation_id == reservation.id,
                    ReservationLineItem.catalog_item_id == old_item.id,
                )
            ).all()
        ],
        "start_datetime": new_start.isoformat(),
        "end_datetime": new_end.isoformat(),
        "catalog_item_id": item.id,
        "party_size": new_party_size,
        "channel": channel,
    }
    record, started = _begin_lifecycle_operation(
        db, reservation, operation="reschedule", idempotency_key=idempotency_key, payload=payload
    )
    if not started:
        return reservation
    _require_mutable(reservation)
    _reallocate_reservation(
        db, reservation, item=item, start=new_start, end=new_end,
        party_size=new_party_size, preferred_resource_ids=preferred_resource_ids,
    )
    reservation.start_datetime = new_start
    reservation.end_datetime = new_end
    reservation.party_size = new_party_size
    if item.id != old_item.id:
        reservation.catalog_item_id = item.id
        _replace_base_price_snapshot(
            db,
            reservation,
            old_catalog_item_id=old_item.id,
            item=item,
            price_book_id=price_book_id,
            channel=channel,
        )
    appointment = db.get(Appointment, reservation.appointment_id) if reservation.appointment_id else None
    if appointment is None:
        reservation.status = "confirmed"
        reservation.provider_sync_status = "none"
    else:
        reservation.status = "pending_provider" if provider_update and appointment.google_calendar_event_id else "confirmed"
        reservation.provider_sync_status = "pending_provider" if reservation.status == "pending_provider" else "confirmed"
    db.commit()
    if appointment is not None:
        from app.appointments.provider_operations import reschedule_appointment_slot

        appointment = reschedule_appointment_slot(
            db, appointment.user_id, appointment_id=appointment.id,
            start_datetime=new_start, end_datetime=new_end,
            timezone_name=appointment.timezone, provider_update=provider_update,
        )
        reservation = db.get(Reservation, reservation_id)
        assert reservation is not None
        if appointment.provider_sync_status == "confirmed":
            reservation.status = "confirmed"
            reservation.provider_sync_status = "confirmed"
    _stage_lifecycle_notification(
        db,
        reservation,
        kind="reschedule",
        fingerprint=idempotency_key or record.idempotency_key,
    )
    _finish_lifecycle_operation(db, reservation, record, actor_user_id=actor_user_id)
    db.commit()
    db.refresh(reservation)
    return reservation


def update_party_size(
    db: Session, reservation_id: int, *, party_size: int, actor_user_id: int | None = None,
    idempotency_key: str | None = None,
) -> Reservation:
    require_reservation_domain()
    if party_size <= 0:
        raise ReservationError("party_size must be positive")
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise ReservationError("reservation not found")
    payload = {"party_size": party_size}
    record, started = _begin_lifecycle_operation(db, reservation, operation="party_size", idempotency_key=idempotency_key, payload=payload)
    if not started:
        return reservation
    _require_mutable(reservation)
    item = _item_for_reservation(db, reservation)
    _reallocate_reservation(db, reservation, item=item, start=reservation.start_datetime, end=reservation.end_datetime, party_size=party_size)
    reservation.party_size = party_size
    _stage_lifecycle_notification(
        db,
        reservation,
        kind="party_size",
        fingerprint=idempotency_key or record.idempotency_key,
    )
    _finish_lifecycle_operation(db, reservation, record, actor_user_id=actor_user_id)
    db.commit()
    db.refresh(reservation)
    return reservation


def change_resource_assignment(
    db: Session, reservation_id: int, *, resource_ids: tuple[int, ...], actor_user_id: int | None = None,
    idempotency_key: str | None = None,
) -> Reservation:
    require_reservation_domain()
    if not resource_ids:
        raise ReservationError("resource_ids must not be empty")
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise ReservationError("reservation not found")
    resources = list(db.scalars(select(Resource).where(Resource.id.in_(resource_ids))).all())
    if len(resources) != len(set(resource_ids)) or any(
        resource.organization_id != reservation.organization_id or not resource.active for resource in resources
    ):
        raise ReservationError("resource not found")
    payload = {"resource_ids": sorted(set(resource_ids))}
    record, started = _begin_lifecycle_operation(db, reservation, operation="resource_assignment", idempotency_key=idempotency_key, payload=payload)
    if not started:
        return reservation
    _require_mutable(reservation)
    item = _item_for_reservation(db, reservation)
    _reallocate_reservation(
        db, reservation, item=item, start=reservation.start_datetime, end=reservation.end_datetime,
        party_size=reservation.party_size, preferred_resource_ids=tuple(resource_ids),
        required_resource_ids=tuple(resource_ids),
    )
    _stage_lifecycle_notification(
        db,
        reservation,
        kind="resource_assignment",
        fingerprint=idempotency_key or record.idempotency_key,
    )
    _finish_lifecycle_operation(db, reservation, record, actor_user_id=actor_user_id)
    db.commit()
    db.refresh(reservation)
    return reservation


def add_line_item(
    db: Session, reservation_id: int, *, catalog_item_id: int, quantity: int = 1,
    price_book_id: int | None = None, channel: str | None = None, actor_user_id: int | None = None,
    idempotency_key: str | None = None,
) -> ReservationLineItem:
    require_reservation_domain()
    if quantity <= 0:
        raise ReservationError("quantity must be positive")
    reservation = db.get(Reservation, reservation_id)
    item = db.get(CatalogItem, catalog_item_id)
    if reservation is None or item is None or item.organization_id != reservation.organization_id:
        raise ReservationError("reservation or catalog item not found")
    payload = {"catalog_item_id": catalog_item_id, "quantity": quantity, "channel": channel}
    record, started = _begin_lifecycle_operation(db, reservation, operation="add_line_item", idempotency_key=idempotency_key, payload=payload)
    if not started:
        line_id = (record.result or {}).get("line_item_id")
        line = db.get(ReservationLineItem, line_id) if line_id is not None else None
        if line is None:
            raise ReservationError("line item not found")
        return line
    _require_mutable(reservation)
    book_id = price_book_id
    if book_id is None:
        book = db.scalar(select(PriceBook).where(PriceBook.organization_id == reservation.organization_id, PriceBook.active.is_(True)))
        book_id = book.id if book is not None else None
    price = active_price(
        db,
        price_book_id=book_id,
        catalog_item_id=item.id,
        location_id=reservation.location_id,
        channel=channel,
    ) if book_id else None
    if price is None:
        raise ReservationError("no active price for catalog item")
    line = snapshot_line_item(reservation_id=reservation.id, item=item, price=price, quantity=quantity)
    db.add(line)
    db.flush()
    record.result = {"line_item_id": line.id}
    _finish_lifecycle_operation(db, reservation, record, actor_user_id=actor_user_id)
    db.commit()
    db.refresh(line)
    return line


def remove_line_item(
    db: Session, reservation_id: int, *, line_item_id: int, actor_user_id: int | None = None,
    idempotency_key: str | None = None,
) -> Reservation:
    require_reservation_domain()
    reservation = db.get(Reservation, reservation_id)
    line = db.get(ReservationLineItem, line_item_id)
    if reservation is None or line is None or line.reservation_id != reservation.id:
        raise ReservationError("line item not found")
    payload = {"line_item_id": line_item_id}
    record, started = _begin_lifecycle_operation(db, reservation, operation="remove_line_item", idempotency_key=idempotency_key, payload=payload)
    if not started:
        return reservation
    _require_mutable(reservation)
    if line.catalog_item_id == reservation.catalog_item_id:
        raise ReservationError("cannot remove the reservation service line item")
    db.delete(line)
    _finish_lifecycle_operation(db, reservation, record, actor_user_id=actor_user_id)
    db.commit()
    db.refresh(reservation)
    return reservation


def change_service(
    db: Session, reservation_id: int, *, catalog_item_id: int, **kwargs: Any
) -> Reservation:
    """Compatibility wrapper for a service change at the existing time."""
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise ReservationError("reservation not found")
    return reschedule_reservation(
        db, reservation_id, start_datetime=reservation.start_datetime,
        catalog_item_id=catalog_item_id, **kwargs,
    )


def synchronize_reservation_from_appointment(db: Session, appointment_id: int) -> Reservation | None:
    """Reconcile reservation state after a retryable appointment operation."""
    reservation = db.scalar(select(Reservation).where(Reservation.appointment_id == appointment_id))
    if reservation is None:
        return None
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        return reservation
    if reservation.status == "cancel_pending_provider":
        if appointment.status == "cancelled":
            reservation.status = "cancelled"
            reservation.provider_sync_status = "confirmed"
        elif appointment.provider_sync_status == "failed":
            reservation.status = "confirmed"
            reservation.provider_sync_status = "failed"
    elif reservation.status == "pending_provider":
        if appointment.provider_sync_status == "confirmed":
            reservation.status = "confirmed"
            reservation.provider_sync_status = "confirmed"
        elif appointment.provider_sync_status == "failed":
            operation = appointment.provider_operation
            if operation == "create":
                reservation.status = "failed"
            elif operation == "reschedule":
                record = db.scalar(
                    select(ReservationLifecycleOperation)
                    .where(
                        ReservationLifecycleOperation.reservation_id == reservation.id,
                        ReservationLifecycleOperation.operation == "reschedule",
                    )
                    .order_by(ReservationLifecycleOperation.created_at.desc())
                )
                reservation.status = (
                    "confirmed"
                    if record is not None
                    and _restore_reschedule_failure(db, reservation, dict(record.payload or {}))
                    else "failed"
                )
            else:
                reservation.status = "confirmed"
            reservation.provider_sync_status = "failed"
    db.commit()
    db.refresh(reservation)
    return reservation


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
        refreshed_row = synchronize_reservation_from_appointment(db, updated.id)
        assert refreshed_row is not None
        results.append(
            {
                "reservation_id": refreshed_row.id,
                "result": refreshed_row.provider_sync_status,
                "appointment_id": updated.id,
            }
        )
    return results
