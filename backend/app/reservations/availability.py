"""Generalized availability search over rules, exceptions, and resource capacity."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    AvailabilityException,
    AvailabilityRule,
    CatalogItem,
    Location,
    PriceBook,
)
from app.pricing.service import active_price
from app.reservations.allocation import AllocationError, allocate_resources, infer_scheduling_mode
from app.reservations.types import (
    AvailabilityRequest,
    AvailabilityResult,
    CandidateSlot,
    PriceEstimate,
)
from app.resources.service import requirements_for_service

_HOLD_CONSTRAINT = "availability is advisory; booking revalidates under lock"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_hhmm(value: str) -> time:
    return time.fromisoformat(value)


def _windows_for_day(
    db: Session,
    *,
    organization_id: int,
    location_id: int | None,
    day: date,
    zone: ZoneInfo,
) -> list[tuple[datetime, datetime]]:
    weekday = day.weekday()
    rules = list(
        db.scalars(
            select(AvailabilityRule).where(
                AvailabilityRule.organization_id == organization_id,
                AvailabilityRule.weekday == weekday,
                or_(
                    AvailabilityRule.location_id == location_id,
                    AvailabilityRule.location_id.is_(None),
                ),
                AvailabilityRule.resource_id.is_(None),
            )
        ).all()
    )
    windows: list[tuple[datetime, datetime]] = []
    if rules:
        for rule in rules:
            start_local = datetime.combine(day, _parse_hhmm(rule.start_time), tzinfo=zone)
            end_local = datetime.combine(day, _parse_hhmm(rule.end_time), tzinfo=zone)
            if end_local > start_local:
                windows.append((start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)))
    else:
        location = db.get(Location, location_id) if location_id is not None else None
        hours = (location.business_hours if location is not None else {}) or {}
        day_name = (
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        )[weekday]
        day_windows = hours.get(day_name) or hours.get(str(weekday)) or []
        if isinstance(day_windows, dict):
            day_windows = [day_windows]
        for window in day_windows:
            if not isinstance(window, dict):
                continue
            start_raw = window.get("start")
            end_raw = window.get("end")
            if not start_raw or not end_raw:
                continue
            start_local = datetime.combine(day, _parse_hhmm(str(start_raw)), tzinfo=zone)
            end_local = datetime.combine(day, _parse_hhmm(str(end_raw)), tzinfo=zone)
            if end_local > start_local:
                windows.append((start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)))
        if not windows and not hours:
            # Unrestricted org/location: default daytime search window.
            start_local = datetime.combine(day, time(9, 0), tzinfo=zone)
            end_local = datetime.combine(day, time(17, 0), tzinfo=zone)
            windows.append((start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)))

    exceptions = list(
        db.scalars(
            select(AvailabilityException).where(
                AvailabilityException.organization_id == organization_id,
                AvailabilityException.starts_at < datetime.combine(day, time.max, tzinfo=zone).astimezone(timezone.utc),
                AvailabilityException.ends_at > datetime.combine(day, time.min, tzinfo=zone).astimezone(timezone.utc),
                or_(
                    AvailabilityException.location_id == location_id,
                    AvailabilityException.location_id.is_(None),
                ),
            )
        ).all()
    )
    closed = [
        (_aware(exc.starts_at), _aware(exc.ends_at))
        for exc in exceptions
        if not exc.available
    ]
    opened = [
        (_aware(exc.starts_at), _aware(exc.ends_at))
        for exc in exceptions
        if exc.available
    ]
    windows.extend(opened)

    def subtract(base: list[tuple[datetime, datetime]], blockers: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
        result = list(base)
        for block_start, block_end in blockers:
            next_result: list[tuple[datetime, datetime]] = []
            for win_start, win_end in result:
                if block_end <= win_start or block_start >= win_end:
                    next_result.append((win_start, win_end))
                    continue
                if win_start < block_start:
                    next_result.append((win_start, block_start))
                if block_end < win_end:
                    next_result.append((block_end, win_end))
            result = next_result
        return result

    return subtract(windows, closed)


def _price_estimate(
    db: Session,
    *,
    organization_id: int,
    catalog_item: CatalogItem,
    location_id: int | None,
    price_book_id: int | None,
    channel: str | None,
) -> PriceEstimate | None:
    book_id = price_book_id
    if book_id is None:
        book = db.scalar(
            select(PriceBook).where(
                PriceBook.organization_id == organization_id,
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
        location_id=location_id,
        channel=channel,
    )
    if price is None:
        return None
    return PriceEstimate(
        currency=price.currency,
        amount_minor=price.amount_minor,
        tax_metadata=dict(price.tax_metadata or {}),
        catalog_item_id=catalog_item.id,
        item_name=catalog_item.name,
    )


def search_availability(db: Session, request: AvailabilityRequest) -> AvailabilityResult:
    """Return candidate slots with provisional allocations and price estimates.

    Results are advisory. Final booking must revalidate under a scheduling lock.
    """
    if request.party_size <= 0:
        raise ValueError("party_size must be positive")
    if request.slot_step_minutes <= 0:
        raise ValueError("slot_step_minutes must be positive")

    item = db.get(CatalogItem, request.catalog_item_id)
    if item is None or item.organization_id != request.organization_id:
        raise ValueError("catalog item not found")
    if not item.active or not item.bookable:
        raise ValueError("catalog item is not bookable")
    duration = item.duration_minutes or 30
    buffer_before = timedelta(minutes=item.buffer_before_minutes or 0)
    buffer_after = timedelta(minutes=item.buffer_after_minutes or 0)
    service_span = timedelta(minutes=duration)

    location = db.get(Location, request.location_id) if request.location_id else None
    if location is not None and location.organization_id != request.organization_id:
        raise ValueError("location not found")
    try:
        zone = ZoneInfo(location.timezone if location is not None else "UTC")
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone must be a valid IANA timezone") from exc

    requirements = requirements_for_service(db, item.id)
    mode = request.scheduling_mode or infer_scheduling_mode(
        requirements, party_size=request.party_size
    )
    estimate = _price_estimate(
        db,
        organization_id=request.organization_id,
        catalog_item=item,
        location_id=request.location_id,
        price_book_id=request.price_book_id,
        channel=request.channel,
    )

    range_start = _aware(request.start_date)
    range_end = _aware(request.end_date or (range_start + timedelta(days=1)))
    if range_end <= range_start:
        raise ValueError("end_date must be after start_date")

    local_start_day = range_start.astimezone(zone).date()
    local_end_day = (range_end - timedelta(microseconds=1)).astimezone(zone).date()

    slots: list[CandidateSlot] = []
    constraints: dict[str, Any] = {
        "advisory": True,
        "note": _HOLD_CONSTRAINT,
        "duration_minutes": duration,
        "buffer_before_minutes": item.buffer_before_minutes,
        "buffer_after_minutes": item.buffer_after_minutes,
        "scheduling_mode": mode,
    }

    day = local_start_day
    while day <= local_end_day:
        for window_start, window_end in _windows_for_day(
            db,
            organization_id=request.organization_id,
            location_id=request.location_id,
            day=day,
            zone=zone,
        ):
            cursor = max(window_start, range_start)
            # Align to step boundary in local time.
            local_cursor = cursor.astimezone(zone)
            minute = local_cursor.minute
            remainder = minute % request.slot_step_minutes
            if remainder:
                local_cursor = local_cursor.replace(second=0, microsecond=0) + timedelta(
                    minutes=request.slot_step_minutes - remainder
                )
            else:
                local_cursor = local_cursor.replace(second=0, microsecond=0)
            cursor = local_cursor.astimezone(timezone.utc)
            step = timedelta(minutes=request.slot_step_minutes)
            while cursor + service_span <= window_end and cursor + service_span <= range_end:
                occupied_start = cursor - buffer_before
                occupied_end = cursor + service_span + buffer_after
                try:
                    resolved_mode, allocations = allocate_resources(
                        db,
                        organization_id=request.organization_id,
                        location_id=request.location_id,
                        start=occupied_start,
                        end=occupied_end,
                        requirements=requirements,
                        party_size=request.party_size,
                        preferred_resource_ids=request.preferred_resource_ids,
                        required_capabilities=request.required_capabilities,
                        scheduling_mode=mode,
                    )
                except AllocationError:
                    cursor += step
                    continue
                slots.append(
                    CandidateSlot(
                        start_datetime=cursor,
                        end_datetime=cursor + service_span,
                        scheduling_mode=resolved_mode,
                        allocations=tuple(allocations),
                        price_estimate=estimate,
                        constraints={
                            "occupied_start": occupied_start.isoformat(),
                            "occupied_end": occupied_end.isoformat(),
                        },
                    )
                )
                cursor += step
        day += timedelta(days=1)

    return AvailabilityResult(slots=tuple(slots), constraints=constraints)
