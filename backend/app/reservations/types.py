"""Shared reservation-engine request/response types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

SchedulingMode = Literal["single_resource", "multi_resource", "capacity"]


@dataclass(frozen=True)
class ResourceAllocation:
    resource_id: int
    resource_name: str
    resource_type: str
    quantity: int


@dataclass(frozen=True)
class PriceEstimate:
    currency: str
    amount_minor: int
    tax_metadata: dict[str, Any] = field(default_factory=dict)
    catalog_item_id: int | None = None
    item_name: str | None = None


@dataclass(frozen=True)
class AvailabilityRequest:
    organization_id: int
    catalog_item_id: int
    start_date: datetime
    end_date: datetime | None = None
    location_id: int | None = None
    party_size: int = 1
    preferred_resource_ids: tuple[int, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    price_book_id: int | None = None
    channel: str | None = None
    slot_step_minutes: int = 15
    scheduling_mode: SchedulingMode | None = None


@dataclass(frozen=True)
class CandidateSlot:
    start_datetime: datetime
    end_datetime: datetime
    scheduling_mode: SchedulingMode
    allocations: tuple[ResourceAllocation, ...]
    price_estimate: PriceEstimate | None
    constraints: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AvailabilityResult:
    slots: tuple[CandidateSlot, ...]
    constraints: dict[str, Any] = field(default_factory=dict)
