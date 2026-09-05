"""Public calendar API contracts."""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class CalendarStatusOut(BaseModel):
    connected: bool
    account_email: str | None = None
    calendar_id: str | None = None
    time_zone: str
    embedded_link: str | None = None
    status: str | None = None


class CalendarEventOut(BaseModel):
    id: str
    title: str
    start: str
    end: str | None = None
    allDay: bool
    url: str | None = None
    description: str = ""
    location: str = ""

    @field_validator("url")
    @classmethod
    def _approved_event_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        from urllib.parse import urlparse

        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname not in {
            "calendar.google.com",
            "www.google.com",
        }:
            raise ValueError("calendar event link is not approved")
        return value


class CalendarEventsOut(BaseModel):
    items: list[CalendarEventOut]
    effective_timezone: str


class CalendarEmbedOut(BaseModel):
    embed_url: str
    view_type: str
    calendar_id: str

    @field_validator("embed_url")
    @classmethod
    def _approved_embed_url(cls, value: str) -> str:
        from urllib.parse import urlparse

        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname != "calendar.google.com":
            raise ValueError("calendar embed link is not approved")
        return value
