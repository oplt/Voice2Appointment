"""Minimal structured appointment intents / tool payloads (Phase 6)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AppointmentIntent(BaseModel):
    operation: Literal["create", "reschedule", "cancel", "check", "find"]
    title: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    timezone: str = "UTC"
    event_id: str | None = None
    confirmed: bool = False


class CreateAppointmentArgs(BaseModel):
    summary: str = Field(min_length=1)
    datetime_start: datetime
    datetime_end: datetime
    description: str | None = None
    client_name: str | None = None
    client_phone: str | None = None
    client_email: str | None = None
    confirmed: bool = False


class RescheduleAppointmentArgs(BaseModel):
    event_id: str = Field(min_length=1)
    new_datetime_start: datetime
    new_datetime_end: datetime
    reason: str | None = None
    confirmed: bool = False


class CancelAppointmentArgs(BaseModel):
    event_id: str = Field(min_length=1)
    reason: str | None = None
    confirmed: bool = False


class FindAppointmentsArgs(BaseModel):
    datetime_start: datetime
    datetime_end: datetime
    summary_contains: str | None = None


class CheckAvailabilityArgs(BaseModel):
    datetime_start: datetime
    datetime_end: datetime
