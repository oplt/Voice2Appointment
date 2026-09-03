"""Call session list schemas (P4-03)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CallSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    call_sid: str
    from_number: str | None = None
    to_number: str | None = None
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: int | None = None
    outcome: str | None = None
    terminal_reason: str | None = None
    has_transcript: bool = False


class CallSessionDetailOut(CallSessionOut):
    transcript: str | None = None


class CallSessionListOut(BaseModel):
    items: list[CallSessionOut]
    next_cursor: str | None = None
    limit: int = 50
