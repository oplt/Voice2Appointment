"""Tenant booking rules used by HTTP and voice appointment creation."""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Appointment, User

_DAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
DurationMinutes = Annotated[int, Field(ge=5, le=480)]


class BusinessHoursWindow(BaseModel):
    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def valid_clock_time(cls, value: str) -> str:
        try:
            parsed = time.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("must be an HH:MM time") from exc
        if parsed.second or parsed.microsecond:
            raise ValueError("must be an HH:MM time")
        return parsed.strftime("%H:%M")


class BookingPolicy(BaseModel):
    """Small commercial-policy surface; empty business hours means unrestricted."""

    default_service_duration_minutes: DurationMinutes = 30
    service_durations_minutes: dict[str, DurationMinutes] = Field(default_factory=dict)
    buffer_before_minutes: int = Field(default=0, ge=0, le=240)
    buffer_after_minutes: int = Field(default=0, ge=0, le=240)
    business_hours: dict[str, list[BusinessHoursWindow]] = Field(default_factory=dict)

    @field_validator("service_durations_minutes")
    @classmethod
    def valid_services(cls, value: dict[str, int]) -> dict[str, int]:
        cleaned: dict[str, int] = {}
        seen: set[str] = set()
        for name, duration in value.items():
            display_name = name.strip()
            normalized = display_name.casefold()
            if not display_name:
                raise ValueError("service names cannot be empty")
            if normalized in seen:
                raise ValueError("service names must be unique ignoring case")
            seen.add(normalized)
            cleaned[display_name] = duration
        return cleaned

    @field_validator("business_hours")
    @classmethod
    def valid_business_hours(
        cls, value: dict[str, list[BusinessHoursWindow]]
    ) -> dict[str, list[BusinessHoursWindow]]:
        unknown = set(value) - set(_DAYS)
        if unknown:
            raise ValueError(f"unknown weekdays: {', '.join(sorted(unknown))}")
        canonical: dict[str, list[BusinessHoursWindow]] = {}
        for day, windows in value.items():
            ordered = sorted(windows, key=lambda window: window.start)
            previous_end: time | None = None
            for window in ordered:
                start = time.fromisoformat(window.start)
                end = time.fromisoformat(window.end)
                if start >= end:
                    raise ValueError("business-hours start must be before end")
                if previous_end is not None and start < previous_end:
                    raise ValueError("business-hours windows cannot overlap")
                previous_end = end
            canonical[day] = ordered
        return canonical


class BookingPolicyError(ValueError):
    """A proposed slot violates a configured business rule."""


class BookingConflictError(BookingPolicyError):
    """A proposed slot overlaps another tenant appointment or its buffer."""


def load_booking_policy(config_json: str | None) -> BookingPolicy:
    if not config_json:
        return BookingPolicy()
    try:
        config = json.loads(config_json)
    except (json.JSONDecodeError, TypeError):
        return BookingPolicy()
    raw = config.get("booking_policy", {}) if isinstance(config, dict) else {}
    return BookingPolicy.model_validate(raw)


def save_booking_policy(user: User, policy: BookingPolicy) -> None:
    try:
        config: dict[str, Any] = json.loads(user.config_json or "{}")
    except (json.JSONDecodeError, TypeError):
        config = {}
    if not isinstance(config, dict):
        config = {}
    config["booking_policy"] = policy.model_dump(mode="json")
    user.config_json = json.dumps(config, separators=(",", ":"), sort_keys=True)


def service_duration(policy: BookingPolicy, summary: str) -> int:
    wanted = summary.strip().casefold()
    for name, duration in policy.service_durations_minutes.items():
        if name.strip().casefold() == wanted:
            return duration
    return policy.default_service_duration_minutes


def resolve_slot_end(
    policy: BookingPolicy,
    *,
    summary: str,
    start: datetime,
    end: datetime | None,
) -> datetime:
    duration = service_duration(policy, summary)
    expected_end = start + timedelta(minutes=duration)
    configured_service = any(
        name.strip().casefold() == summary.strip().casefold()
        for name in policy.service_durations_minutes
    )
    if configured_service and end is not None and end != expected_end:
        raise BookingPolicyError(
            f"{summary.strip()} appointments must be {duration} minutes"
        )
    return end or expected_end


def _local(value: datetime, timezone_name: str) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise BookingPolicyError("timezone must be a valid IANA timezone") from exc
    return value.astimezone(zone)


def buffered_slot(
    policy: BookingPolicy, start: datetime, end: datetime
) -> tuple[datetime, datetime]:
    """Expand a slot so buffers on both adjacent appointments are respected."""
    gap = timedelta(
        minutes=policy.buffer_before_minutes + policy.buffer_after_minutes
    )
    return start - gap, end + gap


def validate_slot(
    db: Session,
    user_id: int,
    *,
    start: datetime,
    end: datetime,
    timezone_name: str,
    exclude_appointment_id: int | None = None,
) -> BookingPolicy:
    """Validate hours and tenant-local conflicts, returning the active policy."""
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if end <= start:
        raise BookingPolicyError("end_datetime must be after start_datetime")

    user = db.get(User, user_id)
    if user is None:
        raise BookingPolicyError("user not found")
    policy = load_booking_policy(user.config_json)
    local_start = _local(start, timezone_name)
    local_end = _local(end, timezone_name)

    if local_start.date() != local_end.date():
        raise BookingPolicyError("appointments must fit within one local business day")
    windows = policy.business_hours.get(_DAYS[local_start.weekday()])
    if policy.business_hours and not windows:
        raise BookingPolicyError("requested day is outside business hours")
    if windows and not any(
        time.fromisoformat(window.start) <= local_start.timetz().replace(tzinfo=None)
        and local_end.timetz().replace(tzinfo=None) <= time.fromisoformat(window.end)
        for window in windows
    ):
        raise BookingPolicyError("requested time is outside business hours")

    blocked_start, blocked_end = buffered_slot(
        policy, start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    )
    stmt = select(Appointment.id).where(
        Appointment.user_id == user_id,
        Appointment.status.notin_(("cancelled", "canceled")),
        Appointment.start_datetime < blocked_end,
        Appointment.end_datetime > blocked_start,
    )
    if exclude_appointment_id is not None:
        stmt = stmt.where(Appointment.id != exclude_appointment_id)
    if db.scalar(stmt) is not None:
        raise BookingConflictError("requested time conflicts with another appointment or buffer")
    return policy
