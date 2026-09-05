"""Pydantic wire contracts for analytics HTTP responses."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SeriesBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")

    labels: list[str] = Field(default_factory=list)
    values: list[float | int] = Field(default_factory=list)


class PeakHeatmap(BaseModel):
    model_config = ConfigDict(extra="ignore")

    weekdays: list[str]
    hours: list[int]
    matrix: list[list[int]]


class CountryRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    country: str
    iso3: str
    calls: int
    total_cost: float | None = None
    currency: str | None = None


class FunnelStage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    label: str
    count: int


class FunnelBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")

    stages: list[FunnelStage] = Field(default_factory=list)
    failure_categories: list[dict[str, Any]] = Field(default_factory=list)
    definitions: dict[str, str] | None = None
    timezone: str | None = None
    range: dict[str, str] | None = None


class ComparisonMetric(BaseModel):
    model_config = ConfigDict(extra="ignore")

    current: float
    prior: float
    delta: float
    delta_pct: float | None = None


class ComparisonBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")

    range: dict[str, str]
    label: str
    total_calls: ComparisonMetric
    total_duration: ComparisonMetric


class AnalyticsMetaResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    timezone: str
    today: str
    default_range_days: int
    max_range_days: int
    default_range: dict[str, str]


class AnalyticsSummaryResponse(BaseModel):
    """Canonical analytics summary wire shape."""

    model_config = ConfigDict(extra="ignore")

    total_calls: int
    total_duration: float | int
    avg_duration: float | int
    total_cost: float | None = None
    currency: str | None = None
    reporting_currency: str | None = None
    totals_by_currency: dict[str, dict[str, float | int]] = Field(default_factory=dict)
    cost_over_time_by_currency: dict[str, SeriesBlock] = Field(default_factory=dict)
    timezone: str | None = None
    range: dict[str, str | None] | None = None
    generated_at: str | None = None
    source_synced_at: str | None = None
    stale: bool = False
    stale_reason: str | None = None
    cache_status: Literal["hit", "miss"] | str | None = None
    cache_age_seconds: int | None = None
    truncated: bool = False
    phone_reidentification_allowed: bool = False
    calls_over_time: SeriesBlock
    duration_distribution: SeriesBlock
    cost_over_time: SeriesBlock
    top_numbers: SeriesBlock
    peak_hours_days: PeakHeatmap
    top_countries: list[CountryRow] = Field(default_factory=list)
    geo_country_counts: list[dict[str, Any]] = Field(default_factory=list)
    funnel: FunnelBlock | None = None
    comparison: ComparisonBlock | None = None
