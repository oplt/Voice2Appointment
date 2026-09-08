"""Google Calendar provider (session + user scoped)."""

from __future__ import annotations

import json
import logging
import secrets
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, TypeVar

import google_auth_httplib2
import httplib2
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calendars.providers.google_idempotency import http_status, insert_event
from app.core.config import settings
from app.core.metrics import metrics
from app.core.security import create_oauth_state, verify_oauth_state
from app.db.models import GoogleCalendarAuth

SCOPES = ["https://www.googleapis.com/auth/calendar"]
logger = logging.getLogger(__name__)
_GoogleResult = TypeVar("_GoogleResult")


@dataclass(frozen=True)
class GoogleCredentialSnapshot:
    """Immutable token input reusable across sequential voice tool calls."""

    token_json: str


def _google_error_category(exc: BaseException) -> str:
    if isinstance(exc, HttpError):
        try:
            status = int(getattr(exc.resp, "status", 0) or 0)
        except (TypeError, ValueError):
            status = 0
        if status == 429:
            return "rate_limited"
        if status in {401, 403}:
            return "auth"
        if 400 <= status < 500:
            return "client_4xx"
        if status >= 500:
            return "server_5xx"
        return "http_error"
    return type(exc).__name__[:40]


def _google_retryable(exc: BaseException) -> bool:
    if not isinstance(exc, HttpError):
        return False
    try:
        status = int(getattr(exc.resp, "status", 0) or 0)
    except (TypeError, ValueError):
        return False
    return status in {429, 500, 502, 503, 504}


def _google_request(operation: str, request: Callable[[], _GoogleResult]) -> _GoogleResult:
    """Record a bounded, provider-level request duration without request payloads."""
    started = time.perf_counter()
    result = "success"
    category = "ok"
    try:
        return request()
    except Exception as exc:  # noqa: BLE001
        result = "failure"
        category = _google_error_category(exc)
        metrics.incr(
            "provider_errors",
            labels={"provider": "google", "operation": operation, "category": category},
        )
        raise
    finally:
        metrics.incr(
            "google_requests",
            labels={"provider": "google", "operation": operation, "result": result},
        )
        metrics.observe(
            "google_request_latency_ms",
            (time.perf_counter() - started) * 1000.0,
            labels={"operation": operation, "result": result},
        )
        # Phase 12 aliases for calendar lookup/create dashboards.
        if operation in {
            "freebusy",
            "list_calendars",
            "calendars_get",
            "events_list",
            "availability",
            "get_event",
        }:
            metrics.observe(
                "calendar_lookup_latency_ms",
                (time.perf_counter() - started) * 1000.0,
                labels={"operation": operation, "result": result},
            )
        if operation in {
            "create_event",
            "events_insert",
            "update_event",
            "patch_event",
            "delete_event",
        }:
            metrics.observe(
                "calendar_create_latency_ms",
                (time.perf_counter() - started) * 1000.0,
                labels={"operation": operation, "result": result},
            )


def _execute_google(operation: str, request: Any) -> Any:
    """Execute with counted retries (replaces opaque httplib num_retries)."""
    attempts = max(0, int(settings.google_request_retries))
    last_exc: BaseException | None = None
    for attempt in range(attempts + 1):
        try:
            return _google_request(operation, lambda: request.execute(num_retries=0))
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= attempts or not _google_retryable(exc):
                raise
            metrics.incr(
                "provider_retries",
                labels={"provider": "google", "operation": operation},
            )
            time.sleep(min(2.0, 0.2 * (2**attempt)))
    assert last_exc is not None
    raise last_exc


def _lifecycle_metric(stage: str, started: float) -> None:
    metrics.observe(
        "google_client_lifecycle_ms",
        (time.perf_counter() - started) * 1000.0,
        labels={"stage": stage},
    )


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _overlaps(start_a: str, end_a: str, start_b: str, end_b: str) -> bool:
    a0, a1 = _parse_iso(start_a), _parse_iso(end_a)
    b0, b1 = _parse_iso(start_b), _parse_iso(end_b)
    return a0 < b1 and b0 < a1


def _client_config() -> dict:
    if not settings.google_client_id or not settings.google_client_secret:
        raise ValueError("Google OAuth is not configured")
    redirect = (settings.google_redirect_uri or "").strip()
    if not redirect:
        raise ValueError("GOOGLE_REDIRECT_URI is required")
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect],
        }
    }


def build_authorization_url(*, user_id: int) -> dict[str, str]:
    """PKCE authorization URL for server-side OAuth (P3-02)."""
    code_verifier = secrets.token_urlsafe(64)
    state = create_oauth_state(user_id=user_id, code_verifier=code_verifier)
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        state=state,
        code_verifier=code_verifier,
    )
    flow.redirect_uri = settings.google_redirect_uri.strip()
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return {"authorization_url": auth_url, "state": state}


def exchange_authorization_code(db: Session, *, state: str, code: str) -> GoogleCalendarAuth:
    verified = verify_oauth_state(state)
    if verified is None:
        raise ValueError("Invalid or expired OAuth state")
    user_id, code_verifier = verified
    redirect = settings.google_redirect_uri.strip()
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        state=state,
        code_verifier=code_verifier,
    )
    flow.redirect_uri = redirect
    _google_request("oauth_token_exchange", lambda: flow.fetch_token(code=code))
    creds = flow.credentials
    if creds is None:
        raise ValueError("Failed to obtain Google credentials")

    account_email = None
    try:
        http = httplib2.Http(timeout=settings.google_http_timeout_seconds)
        authorized_http = google_auth_httplib2.AuthorizedHttp(creds, http=http)
        svc = build("calendar", "v3", http=authorized_http)
        about = _execute_google(
            "calendar_metadata", svc.calendarList().get(calendarId="primary")
        )
        account_email = about.get("id")
    except Exception:
        logger.warning("Could not load primary calendar metadata after OAuth")

    record = db.scalar(
        select(GoogleCalendarAuth)
        .where(GoogleCalendarAuth.user_id == user_id)
        .order_by(GoogleCalendarAuth.updated_at.desc())
    )
    if record is None:
        record = GoogleCalendarAuth(user_id=user_id, provider="google")
        db.add(record)

    record.token_json = creds.to_json()
    record.credentials_json = json.dumps(_client_config())
    record.scopes = " ".join(SCOPES)
    record.revoked = False
    record.status = "connected"
    record.account_email = account_email
    if not record.calendar_id:
        record.calendar_id = "primary"
    if not record.time_zone:
        record.time_zone = settings.default_timezone
    db.commit()
    db.refresh(record)
    return record


class GoogleCalendarService:
    def __init__(
        self,
        db: Session,
        user_id: int,
        *,
        credential_snapshot: GoogleCredentialSnapshot | None = None,
    ):
        self.db = db
        self.user_id = user_id
        self.credential_snapshot = credential_snapshot
        self.service = self.authenticate()

    def _auth_record(self) -> GoogleCalendarAuth:
        started = time.perf_counter()
        record = self.db.scalar(
            select(GoogleCalendarAuth)
            .where(
                GoogleCalendarAuth.user_id == self.user_id,
                GoogleCalendarAuth.revoked.is_(False),
            )
            .order_by(GoogleCalendarAuth.updated_at.desc())
        )
        if not record:
            raise ValueError("No Google Calendar authentication found")
        _lifecycle_metric("auth_lookup", started)
        return record

    def authenticate(self):
        """Load/refresh stored tokens. Never starts an interactive local server."""
        try:
            auth_record = None
            token_json = (
                self.credential_snapshot.token_json
                if self.credential_snapshot is not None
                else None
            )
            if token_json is None:
                auth_record = self._auth_record()
                token_json = auth_record.token_json
            if not token_json:
                raise ValueError(
                    "Google Calendar is not connected. Complete OAuth from Settings."
                )

            try:
                decode_started = time.perf_counter()
                token_data = json.loads(token_json)
                creds = Credentials.from_authorized_user_info(token_data, SCOPES)
                _lifecycle_metric("credential_decode", decode_started)
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                logger.error("Error parsing Google token: %s", type(exc).__name__)
                raise ValueError("Stored Google credentials are invalid") from exc

            if not creds.valid:
                if creds.expired and creds.refresh_token:
                    try:
                        if auth_record is None:
                            auth_record = self._auth_record()
                        refresh_started = time.perf_counter()
                        _google_request("token_refresh", lambda: creds.refresh(Request()))
                        _lifecycle_metric("token_refresh", refresh_started)
                        auth_record.token_json = creds.to_json()
                        self.db.commit()
                    except Exception as exc:
                        logger.error(
                            "Google token refresh failed: %s", type(exc).__name__
                        )
                        raise ValueError(
                            "Google Calendar connection expired. Reconnect from Settings."
                        ) from exc
                else:
                    raise ValueError(
                        "Google Calendar connection expired. Reconnect from Settings."
                    )

            build_started = time.perf_counter()
            http = httplib2.Http(timeout=settings.google_http_timeout_seconds)
            authorized_http = google_auth_httplib2.AuthorizedHttp(creds, http=http)
            self.service = build("calendar", "v3", http=authorized_http)
            self.credential_snapshot = GoogleCredentialSnapshot(creds.to_json())
            _lifecycle_metric("service_build", build_started)
            return self.service
        except ValueError:
            raise
        except Exception as exc:
            logger.error(
                "Error in Google Calendar authentication: %s", type(exc).__name__
            )
            raise ValueError("Google Calendar authentication failed") from exc

    def check_availability(
        self, datetime_start, datetime_end, calendar_id="primary"
    ):
        try:
            busy = self.get_busy_intervals(datetime_start, datetime_end, calendar_id)
            conflicts = [
                {"start": b["start"], "end": b["end"]}
                for b in busy
                if _overlaps(datetime_start, datetime_end, b["start"], b["end"])
            ]
            # freebusy already provides the authoritative availability answer.
            # Do not issue events.list here: event titles are unnecessary for a
            # normal decision and should only be fetched by an authorized detail
            # lookup.
            return not conflicts, conflicts
        except HttpError as error:
            logger.error("Google availability error: %s", type(error).__name__)
            raise

    def get_busy_intervals(
        self, time_min: str, time_max: str, calendar_id: str = "primary"
    ) -> list[dict[str, str]]:
        body = {
            "timeMin": time_min,
            "timeMax": time_max,
            "items": [{"id": calendar_id}],
        }
        result = _execute_google("freebusy", self.service.freebusy().query(body=body))
        calendars = result.get("calendars") or {}
        entry = calendars.get(calendar_id) or {}
        return list(entry.get("busy") or [])

    def create_event(
        self,
        summary,
        datetime_start,
        datetime_end,
        description="",
        timezone="UTC",
        calendar_id="primary",
        idempotency_key: str | None = None,
    ):
        try:
            event = {
                "summary": summary,
                "description": description,
                "start": {"dateTime": datetime_start, "timeZone": timezone},
                "end": {"dateTime": datetime_end, "timeZone": timezone},
            }
            return insert_event(
                self.service.events(),
                calendar_id=calendar_id,
                event=event,
                idempotency_key=idempotency_key,
                execute=lambda request: _execute_google("create_event", request),
            )
        except HttpError as error:
            logger.error("Google create_event error: %s", type(error).__name__)
            raise

    def update_event(
        self,
        event_id,
        summary=None,
        datetime_start=None,
        datetime_end=None,
        description=None,
        timezone="UTC",
        calendar_id="primary",
    ):
        try:
            event = _execute_google(
                "get_event",
                self.service.events().get(calendarId=calendar_id, eventId=event_id),
            )
            if summary:
                event["summary"] = summary
            if datetime_start:
                event["start"]["dateTime"] = datetime_start
                event["start"]["timeZone"] = timezone
            if datetime_end:
                event["end"]["dateTime"] = datetime_end
                event["end"]["timeZone"] = timezone
            if description:
                event["description"] = description
            return _execute_google(
                "update_event",
                self.service.events().update(
                    calendarId=calendar_id, eventId=event_id, body=event
                ),
            )
        except HttpError as error:
            logger.error("Google update_event error: %s", type(error).__name__)
            raise

    def get_event(self, event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
        return _execute_google(
            "get_event",
            self.service.events().get(calendarId=calendar_id, eventId=event_id),
        )

    def delete_event(self, event_id, calendar_id="primary"):
        try:
            _execute_google(
                "delete_event",
                self.service.events().delete(calendarId=calendar_id, eventId=event_id),
            )
            return True
        except HttpError as error:
            if http_status(error) in {404, 410}:
                return True
            logger.error("Google delete_event error: %s", type(error).__name__)
            raise

    def list_events(
        self, time_min: str, time_max: str, calendar_id="primary", max_results=100
    ):
        return _execute_google(
            "list_events",
            self.service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                maxResults=max_results,
            ),
        )

    def list_calendars(self) -> dict[str, Any]:
        return _execute_google("list_calendars", self.service.calendarList().list())
