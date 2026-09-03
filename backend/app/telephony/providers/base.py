"""Telephony provider protocol."""

from __future__ import annotations

from typing import Any, Protocol


class TelephonyProvider(Protocol):
    def fetch_calls(self, limit: int = 100) -> list[dict[str, Any]]:
        """Fetch recent call records from the provider."""
        ...

    def handle_recording_webhook(self, payload: dict[str, str]) -> dict[str, Any]:
        """Process a recording-status webhook payload."""
        ...
