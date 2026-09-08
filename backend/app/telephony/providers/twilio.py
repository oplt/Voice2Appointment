"""Twilio telephony provider."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Any, Iterator
from urllib.parse import parse_qs, urlparse

import twilio.rest
from twilio.base.exceptions import TwilioRestException

from app.core.config import settings
from app.core.metrics import metrics

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
        "provider_updated_at": (
            c.date_updated.isoformat()
            if getattr(c, "date_updated", None)
            else None
        ),
    }


@dataclass(frozen=True)
class CallPage:
    records: list[dict[str, Any]]
    next_page_token: str | None
    exhausted: bool


def _page_token(next_page_url: str | None) -> str | None:
    if not next_page_url:
        return None
    query = parse_qs(urlparse(next_page_url).query)
    values = query.get("PageToken") or query.get("pageToken")
    return values[0] if values else None


class TwilioProvider:
    def __init__(self, account_sid: str, auth_token: str):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self._client = twilio.rest.Client(account_sid, auth_token)
        self._request_lock = Lock()
        self._next_request_at = 0.0

    def _throttle(self) -> None:
        rate = settings.twilio_requests_per_second
        interval = 1.0 / rate
        with self._request_lock:
            now = time.monotonic()
            scheduled = max(now, self._next_request_at)
            self._next_request_at = scheduled + interval
        delay = scheduled - now
        if delay > 0:
            time.sleep(delay)

    def _request(self, operation: str, request: Any) -> Any:
        self._throttle()
        started = time.perf_counter()
        result = "success"
        category = "ok"
        try:
            return request()
        except Exception as exc:  # noqa: BLE001
            result = "failure"
            if isinstance(exc, TwilioRestException):
                status = int(getattr(exc, "status", 0) or 0)
                if status == 429:
                    category = "rate_limited"
                elif status in {401, 403}:
                    category = "auth"
                elif 400 <= status < 500:
                    category = "client_4xx"
                elif status >= 500:
                    category = "server_5xx"
                else:
                    category = "http_error"
            else:
                category = type(exc).__name__[:40]
            metrics.incr(
                "provider_errors",
                labels={"provider": "twilio", "operation": operation, "category": category},
            )
            raise
        finally:
            metrics.incr(
                "twilio_requests",
                labels={"provider": "twilio", "operation": operation, "result": result},
            )
            metrics.observe(
                "twilio_request_latency_ms",
                (time.perf_counter() - started) * 1000.0,
                labels={"operation": operation, "result": result},
            )

    def fetch_call_page(
        self,
        *,
        start_time_after: datetime | None,
        page_size: int,
        page_token: str | None = None,
    ) -> CallPage:
        """Fetch exactly one SDK page and expose its opaque continuation token."""
        kwargs: dict[str, Any] = {"page_size": page_size}
        if start_time_after is not None:
            kwargs["start_time_after"] = start_time_after
        if page_token:
            kwargs["page_token"] = page_token
        page = self._request("fetch_call_page", lambda: self._client.calls.page(**kwargs))
        records = [_call_to_dict(call) for call in page]
        token = _page_token(page.next_page_url)
        return CallPage(records=records, next_page_token=token, exhausted=token is None)

    def fetch_calls(
        self,
        limit: int = 100,
        *,
        start_time_after: datetime | None = None,
        page_size: int | None = None,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        """Compatibility wrapper over explicit page traversal."""
        size = page_size or min(limit, 100)
        page_budget = max_pages or max(1, (limit + size - 1) // size)
        records: list[dict[str, Any]] = []
        token: str | None = None
        for _ in range(page_budget):
            page = self.fetch_call_page(
                start_time_after=start_time_after,
                page_size=size,
                page_token=token,
            )
            records.extend(page.records[: max(0, limit - len(records))])
            token = page.next_page_token
            if page.exhausted or len(records) >= limit:
                break
        return records

    def fetch_call(self, sid: str) -> dict[str, Any] | None:
        try:
            c = self._request("fetch_call", lambda: self._client.calls(sid).fetch())
        except TwilioRestException as exc:
            # A missing historical call is permanent; rate limits and provider
            # failures must propagate to the bounded task retry policy.
            if getattr(exc, "status", None) == 404:
                return None
            raise
        return _call_to_dict(c)

    def fetch_calls_by_sids(self, sids: Iterator[str] | list[str]) -> list[dict[str, Any]]:
        values = list(sids)
        if not values:
            return []
        workers = min(settings.twilio_active_refresh_concurrency, len(values))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            rows = list(executor.map(self.fetch_call, values))
        return [row for row in rows if row is not None]

    def update_call_twiml(self, call_sid: str, twiml: str) -> Any:
        return self._request(
            "update_call", lambda: self._client.calls(call_sid).update(twiml=twiml)
        )

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
