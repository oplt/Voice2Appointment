"""Pydantic contracts for the reservations HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AvailabilityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    catalog_item_id: int
    start_date: datetime
    end_date: datetime | None = None
    location_id: int | None = None
    party_size: int = Field(default=1, gt=0)
    preferred_resource_ids: list[int] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    price_book_id: int | None = None
    channel: str | None = Field(default=None, max_length=32)
    slot_step_minutes: int = Field(default=15, ge=5, le=120)
    scheduling_mode: Literal["single_resource", "multi_resource", "capacity"] | None = None


class ReservationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    catalog_item_id: int
    start_datetime: datetime
    end_datetime: datetime | None = None
    location_id: int | None = None
    customer_id: int | None = None
    party_size: int = Field(default=1, gt=0)
    preferred_resource_ids: list[int] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    price_book_id: int | None = None
    channel: str | None = Field(default=None, max_length=32)
    scheduling_mode: Literal["single_resource", "multi_resource", "capacity"] | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


class HoldIn(ReservationIn):
    hold_ttl_seconds: int = Field(default=300, ge=30, le=3600)


class ReservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    location_id: int | None
    customer_id: int | None
    catalog_item_id: int | None
    appointment_id: int | None
    scheduling_mode: str
    status: str
    start_datetime: datetime
    end_datetime: datetime
    party_size: int
    hold_expires_at: datetime | None
    provider_sync_status: str
    allocation_json: dict[str, Any]


class ReservationPageOut(BaseModel):
    items: list[ReservationOut]
    total: int
    limit: int
    offset: int


class LineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    catalog_item_id: int | None
    item_name: str
    quantity: int
    unit_price_minor: int
    currency: str
    tax_metadata: dict[str, Any] = Field(default_factory=dict)


class ReservationDetailOut(ReservationOut):
    line_items: list[LineItemOut] = Field(default_factory=list)
    resource_ids: list[int] = Field(default_factory=list)


class CancelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=1000)
    idempotency_key: str | None = Field(default=None, max_length=128)


class RescheduleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_datetime: datetime
    end_datetime: datetime | None = None
    catalog_item_id: int | None = None
    party_size: int | None = Field(default=None, gt=0)
    price_book_id: int | None = None
    channel: str | None = Field(default=None, max_length=32)
    preferred_resource_ids: list[int] = Field(default_factory=list)
    idempotency_key: str | None = Field(default=None, max_length=128)


class PartySizeIn(BaseModel):
    party_size: int = Field(gt=0)
    idempotency_key: str | None = Field(default=None, max_length=128)


class ResourceAssignmentIn(BaseModel):
    resource_ids: list[int] = Field(min_length=1)
    idempotency_key: str | None = Field(default=None, max_length=128)


class LineItemIn(BaseModel):
    catalog_item_id: int
    quantity: int = Field(default=1, gt=0)
    price_book_id: int | None = None
    channel: str | None = Field(default=None, max_length=32)
    idempotency_key: str | None = Field(default=None, max_length=128)


class LineItemPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity: int = Field(gt=0)
    idempotency_key: str | None = Field(default=None, max_length=128)
