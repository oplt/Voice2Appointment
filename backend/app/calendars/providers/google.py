"""Google Calendar provider (session + user scoped)."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import GoogleCalendarAuth

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _overlaps(start_a: str, end_a: str, start_b: str, end_b: str) -> bool:
    a0, a1 = _parse_iso(start_a), _parse_iso(end_a)
    b0, b1 = _parse_iso(start_b), _parse_iso(end_b)
    return a0 < b1 and b0 < a1


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
        try:
            auth_record = self._auth_record()
            credentials_json = auth_record.credentials_json
            token_json = auth_record.token_json

            if not credentials_json:
                raise ValueError("No credentials found in database")

            creds = None
            if token_json:
                try:
                    token_data = json.loads(token_json)
                    creds = Credentials.from_authorized_user_info(token_data, SCOPES)
                except (json.JSONDecodeError, Exception) as e:
                    logging.error("Error parsing token: %s", e)
                    creds = None

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                        auth_record.token_json = creds.to_json()
                        self.db.commit()
                    except Exception as e:
                        logging.error("Error refreshing token: %s", e)
                        creds = None

                if not creds:
                    with tempfile.NamedTemporaryFile(
                        mode="w", suffix=".json", delete=False
                    ) as temp_creds:
                        temp_creds.write(credentials_json)
                        temp_creds_path = temp_creds.name

                    try:
                        flow = InstalledAppFlow.from_client_secrets_file(
                            temp_creds_path, SCOPES
                        )
                        creds = flow.run_local_server(port=0)
                        auth_record.token_json = creds.to_json()
                        self.db.commit()
                    finally:
                        try:
                            os.unlink(temp_creds_path)
                        except OSError:
                            pass

            if not creds:
                raise ValueError("Failed to obtain valid Google Calendar credentials")

            self.service = build("calendar", "v3", credentials=creds)
            return self.service

        except Exception as e:
            logging.error("Error in Google Calendar authentication: %s", e)
            raise

    def check_availability(self, datetime_start, datetime_end, calendar_id="primary"):
        try:
            busy = self.get_busy_intervals(datetime_start, datetime_end, calendar_id)
            conflicts = [
                {"start": b["start"], "end": b["end"]} for b in busy if _overlaps(
                    datetime_start, datetime_end, b["start"], b["end"]
                )
            ]
            # Keep event list for callers that want summaries when busy.
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
            logging.error("An error occurred: %s", error)
            raise

    def get_busy_intervals(
        self, time_min: str, time_max: str, calendar_id: str = "primary"
    ) -> list[dict[str, str]]:
        """One FreeBusy query for the window — used for local alternative-slot math."""
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
    ):
        try:
            event = {
                "summary": summary,
                "description": description,
                "start": {"dateTime": datetime_start, "timeZone": timezone},
                "end": {"dateTime": datetime_end, "timeZone": timezone},
            }
            return (
                self.service.events()
                .insert(calendarId=calendar_id, body=event)
                .execute()
            )
        except HttpError as error:
            logging.error("An error occurred: %s", error)
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
            logging.error("An error occurred: %s", error)
            raise

    def delete_event(self, event_id, calendar_id="primary"):
        try:
            self.service.events().delete(
                calendarId=calendar_id, eventId=event_id
            ).execute()
            return True
        except HttpError as error:
            logging.error("An error occurred: %s", error)
            raise

    def list_events(self, time_min: str, time_max: str, calendar_id="primary", max_results=100):
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
