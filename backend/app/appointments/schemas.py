"""Appointment Pydantic schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
    status: str = "pending"


class AppointmentUpdate(BaseModel):
    summary: str | None = None
    description: str | None = None
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None
    timezone: str | None = None
    client_name: str | None = None
    client_phone: str | None = None
    client_email: str | None = None
    notes: str | None = None
    status: str | None = None


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
