"""Twilio telephony provider."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterator

import twilio.rest
from twilio.base.exceptions import TwilioRestException

TERMINAL_CALL_STATUSES = frozenset(
    {"completed", "busy", "failed", "no-answer", "canceled", "cancelled"}
)


def _call_to_dict(c: Any) -> dict[str, Any]:
    return {
        "sid": c.sid,
        "from": c.from_,
        "to": c.to,
        "start_time": c.start_time.isoformat() if c.start_time else None,
        "duration_sec": int(c.duration) if c.duration else None,
        "price": float(c.price) if c.price else None,
        "price_unit": c.price_unit,
        "direction": getattr(c, "direction", None),
        "from_formatted": getattr(c, "from_formatted", None),
        "status": getattr(c, "status", None),
    }


class TwilioProvider:
    def __init__(self, account_sid: str, auth_token: str):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self._client = twilio.rest.Client(account_sid, auth_token)

    def fetch_calls(
        self,
        limit: int = 100,
        *,
        start_time_after: datetime | None = None,
        page_size: int | None = None,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch calls with optional page budget. ``limit`` is a hard max records."""
        size = page_size or min(limit, 100)
        kwargs: dict[str, Any] = {"page_size": size}
        if start_time_after is not None:
            kwargs["start_time_after"] = start_time_after
        max_records = limit
        if max_pages is not None:
            max_records = min(limit, size * max_pages)
        call_data: list[dict[str, Any]] = []
        for c in self._client.calls.stream(**kwargs):
            call_data.append(_call_to_dict(c))
            if len(call_data) >= max_records:
                break
        return call_data

    def fetch_call(self, sid: str) -> dict[str, Any] | None:
        try:
            c = self._client.calls(sid).fetch()
        except TwilioRestException:
            return None
        return _call_to_dict(c)

    def fetch_calls_by_sids(self, sids: Iterator[str] | list[str]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for sid in sids:
            row = self.fetch_call(sid)
            if row is not None:
                out.append(row)
        return out

    def handle_recording_webhook(self, payload: dict[str, str]) -> dict[str, Any]:
        return self.parse_recording_webhook(payload)

    @staticmethod
    def parse_recording_webhook(payload: dict[str, str]) -> dict[str, Any]:
        """Extract recording fields — no network / no credential access."""
        call_sid = payload.get("CallSid")
        recording_sid = payload.get("RecordingSid")
        recording_url = payload.get("RecordingUrl")
        if not call_sid or not recording_sid or not recording_url:
            return {"status": "missing fields", "ok": False}
        return {
            "status": "ok",
            "ok": True,
            "call_sid": call_sid,
            "recording_sid": recording_sid,
            "recording_url": recording_url,
        }
