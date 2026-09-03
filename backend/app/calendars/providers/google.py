"""Google Calendar provider (session + user scoped)."""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime

import google_auth_httplib2
import httplib2
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_oauth_state, verify_oauth_state
from app.db.models import GoogleCalendarAuth

_GCAL_READ_TIMEOUT = 30

SCOPES = ["https://www.googleapis.com/auth/calendar"]
logger = logging.getLogger(__name__)


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
    flow.fetch_token(code=code)
    creds = flow.credentials
    if creds is None:
        raise ValueError("Failed to obtain Google credentials")

    account_email = None
    try:
        http = httplib2.Http(timeout=_GCAL_READ_TIMEOUT)
        authorized_http = google_auth_httplib2.AuthorizedHttp(creds, http=http)
        svc = build("calendar", "v3", http=authorized_http)
        about = svc.calendarList().get(calendarId="primary").execute()
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
    from app.core.cache import invalidate_user_calendar_caches

    invalidate_user_calendar_caches(user_id)
    return record


class GoogleCalendarService:
    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        self.service = self.authenticate()

    def _auth_record(self) -> GoogleCalendarAuth:
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
        return record

    def authenticate(self):
        """Load/refresh stored tokens. Never starts an interactive local server."""
        try:
            auth_record = self._auth_record()
            token_json = auth_record.token_json
            if not token_json:
                raise ValueError(
                    "Google Calendar is not connected. Complete OAuth from Settings."
                )

            try:
                token_data = json.loads(token_json)
                creds = Credentials.from_authorized_user_info(token_data, SCOPES)
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                logger.error("Error parsing Google token: %s", type(exc).__name__)
                raise ValueError("Stored Google credentials are invalid") from exc

            if not creds.valid:
                if creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
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

            http = httplib2.Http(timeout=_GCAL_READ_TIMEOUT)
            authorized_http = google_auth_httplib2.AuthorizedHttp(creds, http=http)
            self.service = build("calendar", "v3", http=authorized_http)
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
            if not conflicts:
                return True, []
            events_result = (
                self.service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=datetime_start,
                    timeMax=datetime_end,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            return False, events_result.get("items", [])
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
        result = self.service.freebusy().query(body=body).execute()
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
            if idempotency_key:
                event["extendedProperties"] = {
                    "private": {"idempotency_key": idempotency_key}
                }
            return (
                self.service.events()
                .insert(calendarId=calendar_id, body=event)
                .execute()
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
            event = (
                self.service.events()
                .get(calendarId=calendar_id, eventId=event_id)
                .execute()
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
            return (
                self.service.events()
                .update(calendarId=calendar_id, eventId=event_id, body=event)
                .execute()
            )
        except HttpError as error:
            logger.error("Google update_event error: %s", type(error).__name__)
            raise

    def delete_event(self, event_id, calendar_id="primary"):
        try:
            self.service.events().delete(
                calendarId=calendar_id, eventId=event_id
            ).execute()
            return True
        except HttpError as error:
            logger.error("Google delete_event error: %s", type(error).__name__)
            raise

    def list_events(
        self, time_min: str, time_max: str, calendar_id="primary", max_results=100
    ):
        return (
            self.service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                maxResults=max_results,
            )
            .execute()
        )
