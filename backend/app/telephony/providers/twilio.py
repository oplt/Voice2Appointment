"""Twilio telephony provider."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import twilio.rest


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
    ) -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {"limit": limit}
        if start_time_after is not None:
            kwargs["start_time_after"] = start_time_after
        calls = self._client.calls.list(**kwargs)
        call_data: list[dict[str, Any]] = []
        for c in calls:
            call_data.append(
                {
                    "sid": c.sid,
                    "from": c.from_,
                    "to": c.to,
                    "start_time": c.start_time.isoformat() if c.start_time else None,
                    "duration_sec": int(c.duration) if c.duration else None,
                    "price": float(c.price) if c.price else None,
                    "price_unit": c.price_unit,
                    "direction": getattr(c, "direction", None),
                    "from_formatted": getattr(c, "from_formatted", None),
                }
            )
        return call_data

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
