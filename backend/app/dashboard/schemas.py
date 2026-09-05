"""Pydantic wire contract for the dashboard summary HTTP response (P7-04)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UpcomingAppointment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    summary: str
    start_datetime: str
    end_datetime: str
    status: str
    client_name: str | None = None


class DashboardKpi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: float | int | None = None
    definition: str
    window: str
    timezone: str
    drill_down: str
    exclusions: str
    numerator: int | None = None
    denominator: int | None = None


class DashboardSummaryResponse(BaseModel):
    """Canonical dashboard summary wire shape.

    Nested provider/operational/freshness blocks stay permissive dicts: they
    carry provider-derived optional keys that evolve independently of the
    required top-level counters this contract pins down.
    """

    model_config = ConfigDict(extra="ignore")

    appointments_today: int
    appointments_week: int
    upcoming: list[UpcomingAppointment] = Field(default_factory=list)
    calendar_connected: bool
    recent_calls: int
    call_statistics: dict[str, Any] | None = None
    provider_status: dict[str, Any] | None = None
    integrations: dict[str, Any] | None = None
    operational: dict[str, DashboardKpi] | None = None
    timezone: str | None = None
    generated_at: str | None = None
    freshness: dict[str, Any] | None = None
