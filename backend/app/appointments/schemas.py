"""Appointment Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AppointmentStatus(str, Enum):
    pending = "pending"
    confirmed = "confirmed"
    cancelled = "cancelled"
    failed = "failed"
    completed = "completed"


_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"confirmed", "cancelled", "failed", "pending"}),
    "confirmed": frozenset({"cancelled", "completed", "confirmed"}),
    "cancelled": frozenset({"cancelled"}),
    "failed": frozenset({"failed", "pending"}),
    "completed": frozenset({"completed"}),
}


def validate_timezone_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError("timezone is required")
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone must be a valid IANA timezone") from exc
    return name


def assert_status_transition(current: str, new: str) -> None:
    allowed = _ALLOWED_TRANSITIONS.get(current, frozenset())
    if new not in allowed:
        raise ValueError(f"cannot transition status from {current} to {new}")


class AppointmentCreate(BaseModel):
    summary: str = Field(min_length=1, max_length=255)
    description: str | None = None
    start_datetime: datetime
    end_datetime: datetime | None = None
    timezone: str = "UTC"
    client_name: str | None = None
    client_phone: str | None = None
    client_email: str | None = None
    notes: str | None = None
    status: AppointmentStatus = AppointmentStatus.pending

    @field_validator("timezone")
    @classmethod
    def tz_ok(cls, value: str) -> str:
        return validate_timezone_name(value)

    @field_validator("summary")
    @classmethod
    def summary_strip(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("summary cannot be empty")
        return cleaned


class AppointmentUpdate(BaseModel):
    summary: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None
    timezone: str | None = None
    client_name: str | None = None
    client_phone: str | None = None
    client_email: str | None = None
    notes: str | None = None
    status: AppointmentStatus | None = None

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> AppointmentUpdate:
        for field in ("summary", "start_datetime", "end_datetime", "timezone", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self

    @field_validator("timezone")
    @classmethod
    def tz_ok(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_timezone_name(value)

    @field_validator("summary")
    @classmethod
    def summary_strip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("summary cannot be empty")
        return cleaned


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    summary: str
    description: str | None = None
    start_datetime: datetime
    end_datetime: datetime
    timezone: str
    status: str
    client_name: str | None = None
    client_phone: str | None = None
    client_email: str | None = None
    notes: str | None = None
    google_calendar_event_id: str | None = None
    google_calendar_link: str | None = None
    provider_sync_status: str
    transcript: str | None = None


class AppointmentListItemOut(BaseModel):
    """Non-sensitive appointment fields safe for paginated list views."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    summary: str
    start_datetime: datetime
    end_datetime: datetime
    timezone: str
    status: str
    provider_sync_status: str


class AppointmentListOut(BaseModel):
    items: list[AppointmentListItemOut]
    next_cursor: str | None = None
    scope: str = "upcoming"
    limit: int = 50
