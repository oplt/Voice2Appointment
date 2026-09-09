"""Pydantic contracts for the catalog HTTP API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CategoryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    active: bool = True


class CategoryOut(CategoryIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class CategoryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    active: bool | None = None


class ItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    kind: Literal["service", "product", "addon", "package"] = "service"
    category_id: int | None = None
    description: str | None = None
    active: bool = True
    bookable: bool = False
    sellable: bool = True
    duration_minutes: int | None = Field(default=None, gt=0)
    buffer_before_minutes: int = Field(default=0, ge=0)
    buffer_after_minutes: int = Field(default=0, ge=0)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ItemPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    kind: Literal["service", "product", "addon", "package"] | None = None
    category_id: int | None = None
    description: str | None = None
    active: bool | None = None
    bookable: bool | None = None
    sellable: bool | None = None
    duration_minutes: int | None = Field(default=None, gt=0)
    buffer_before_minutes: int | None = Field(default=None, ge=0)
    buffer_after_minutes: int | None = Field(default=None, ge=0)
    metadata_json: dict[str, Any] | None = None
    expected_version: int = Field(ge=1)


class ItemOut(ItemIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    version: int


class ItemPageOut(BaseModel):
    items: list[ItemOut]
    total: int
    limit: int
    offset: int


class DuplicateItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=255)


class BulkActiveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_ids: list[int] = Field(min_length=1, max_length=200)


class OptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    active: bool = True
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class OptionOut(OptionIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    catalog_item_id: int


class OptionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    active: bool | None = None
    metadata_json: dict[str, Any] | None = None


class ResourceRequirementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_type: str | None = Field(default=None, max_length=64)
    capability: str | None = Field(default=None, max_length=100)
    quantity: int = Field(default=1, gt=0)
    required: bool = True


class ResourceRequirementOut(ResourceRequirementIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    catalog_item_id: int
