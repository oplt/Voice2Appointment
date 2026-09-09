"""Pydantic contracts for the resources HTTP API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ResourceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    resource_type: str = Field(min_length=1, max_length=64)
    location_id: int | None = None
    active: bool = True
    capacity: int = Field(default=1, ge=1)


class ResourcePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    resource_type: str | None = Field(default=None, min_length=1, max_length=64)
    location_id: int | None = None
    active: bool | None = None
    capacity: int | None = Field(default=None, ge=1)


class ResourceOut(ResourceIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class CapabilityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capability: str = Field(min_length=1, max_length=100)


class CapabilityOut(CapabilityIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    resource_id: int


class AvailabilityRuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weekday: int = Field(ge=0, le=6)
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")


class AvailabilityRulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weekday: int | None = Field(default=None, ge=0, le=6)
    start_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")


class AvailabilityRuleOut(AvailabilityRuleIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    resource_id: int | None
    location_id: int | None


class AvailabilityExceptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    starts_at: datetime
    ends_at: datetime
    available: bool = False
    reason: str | None = Field(default=None, max_length=255)


class AvailabilityExceptionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    available: bool | None = None
    reason: str | None = Field(default=None, max_length=255)


class AvailabilityExceptionOut(AvailabilityExceptionIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    resource_id: int | None
    location_id: int | None


class AdjacentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    resource_id: int
    name: str
    resource_type: str
    capacity: int
    active: bool

