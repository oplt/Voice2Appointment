"""Pydantic argument models for key voice tools."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _ToolArgs(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class SendSecureLinkArgs(_ToolArgs):
    purpose: str = "payment"
    client_phone: str | None = None
    client_email: str | None = None
    client_name: str | None = None

    @model_validator(mode="after")
    def require_recipient(self) -> SendSecureLinkArgs:
        phone = (self.client_phone or "").strip()
        email = (self.client_email or "").strip()
        if not phone and not email:
            raise ValueError("client_phone or client_email is required")
        return self


class CheckOrderStatusArgs(_ToolArgs):
    order_id: str = Field(min_length=1)

    @field_validator("order_id")
    @classmethod
    def non_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("order_id must not be blank")
        return cleaned


class CreateReservationArgs(_ToolArgs):
    catalog_item_id: int
    datetime_start: str
    party_size: int = 2
    location_id: int | None = None
    client_name: str | None = None
    client_phone: str | None = None
    seating_preference: str | None = None
    dietary_notes: str | None = None
    accessibility_notes: str | None = None
    special_occasion: str | None = None
    confirmed: bool = False


class CancelReservationArgs(_ToolArgs):
    reservation_id: int
    confirmed: bool = False


class ModifyReservationArgs(_ToolArgs):
    reservation_id: int
    party_size: int | None = None
    datetime_start: str | None = None
    confirmed: bool = False


class PromoteWaitlistArgs(_ToolArgs):
    waitlist_id: int
    confirmed: bool = False


class CreateAppointmentArgs(_ToolArgs):
    summary: str
    datetime_start: str
    datetime_end: str
    description: str | None = None
    client_name: str | None = None
    client_phone: str | None = None
    client_email: str | None = None
    confirmed: bool = False
    catalog_item_id: int | None = None
    practitioner_id: int | None = None
    location_id: int | None = None
    utterance: str | None = None


class BookSalonServiceArgs(_ToolArgs):
    catalog_item_id: int
    datetime_start: str
    addon_item_ids: list[int] = Field(default_factory=list)
    preferred_staff_id: int | None = None
    required_capability: str | None = None
    location_id: int | None = None
    client_name: str | None = None
    client_phone: str | None = None
    confirmed: bool = False

    @field_validator("addon_item_ids", mode="before")
    @classmethod
    def empty_addon_list(cls, value: Any) -> Any:
        return [] if value is None else value


class ModifySalonBookingArgs(_ToolArgs):
    reservation_id: int
    datetime_start: str | None = None
    preferred_staff_id: int | None = None
    confirmed: bool = False


# Back-compat alias used by earlier drafts / tests.
BookSalonAppointmentArgs = BookSalonServiceArgs