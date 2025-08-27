# calendar.py
import json
import datetime as dt
from dateutil import tz
from typing import Tuple, Dict, Any, List
from flask import Blueprint, request, jsonify, redirect, url_for, session, current_app
from flask_login import login_required, current_user
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from db.models import GoogleCalendarAuth
from flaskapp import db

google_bp = Blueprint("google_calendar", __name__, url_prefix="/google")

# Use a single scope everywhere (readonly is safer for mirroring)
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# ---------- DB helpers (NO Google API here) ----------
def get_user_google_secrets(user_id) -> Tuple[Dict[str, Any], Dict[str, Any] | None]:
    """
    Returns (client_config_dict, token_info_dict_or_None)
    client_config_dict must look like credentials.json content: {"web": {...}} or {"installed": {...}}
    """
    rec = GoogleCalendarAuth.query.filter_by(user_id=user_id).first()
    if not rec or not rec.credentials_json:
        raise RuntimeError(f"No Google credentials stored for user {user_id}")

    client_config = json.loads(rec.credentials_json)
    token_info = json.loads(rec.token_json) if rec.token_json else None
    return client_config, token_info

def save_user_token(user_id, token_info: Dict[str, Any]) -> None:
    rec = GoogleCalendarAuth.query.filter_by(user_id=user_id).first()
    if not rec:
        raise RuntimeError("Cannot save token: credentials row missing.")
    rec.token_json = json.dumps(token_info)
    db.session.add(rec)
    db.session.commit()


def _normalize_client_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    # Ensure it’s wrapped with "web" or "installed"
    if "web" in raw or "installed" in raw:
        return raw
    # If you stored only the inner dict, assume "web"
    return {"web": raw}


def _build_credentials(user_id) -> Credentials | None:
    client_config, token_info = get_user_google_secrets(user_id)

    creds = None
    if token_info:
        creds = Credentials.from_authorized_user_info(token_info, SCOPES)

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_user_token(user_id, json.loads(creds.to_json()))
    return creds


def _get_calendar_service(user_id):
    creds = _build_credentials(user_id)
    if not creds:
        return None
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


@google_bp.route("/connect")
@login_required
def connect():
    """
    Start OAuth if we don't have a valid token.
    This is the WEB APP flow (not InstalledAppFlow).
    """
    client_config_raw, token_info = get_user_google_secrets(current_user.id)
    client_config = _normalize_client_config(client_config_raw)

    # If we already have a valid, non-expired token -> done
    if token_info:
        creds = Credentials.from_authorized_user_info(token_info, SCOPES)
        if creds and creds.valid and not creds.expired:
            return redirect(url_for("dashboard"))

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=url_for("google_calendar.oauth2callback", _external=True),
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",      # ensure refresh_token on first consent
    )
    session["google_oauth_state"] = state
    return redirect(auth_url)


@google_bp.route("/oauth2callback")
@login_required
def oauth2callback():
    """Finish OAuth, store token in DB, and return to dashboard."""
    client_config_raw, _ = get_user_google_secrets(current_user.id)
    client_config = _normalize_client_config(client_config_raw)
    state = session.get("google_oauth_state")

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        state=state,
        redirect_uri=url_for("google_calendar.oauth2callback", _external=True),
    )
    flow.fetch_token(authorization_response=request.url)
    creds: Credentials = flow.credentials

    save_user_token(current_user.id, json.loads(creds.to_json()))
    return redirect(url_for("dashboard"))


def _iso(dtobj: dt.datetime) -> str:
    # ISO 8601 with timezone if present
    return dtobj.isoformat()


@google_bp.route("/events")
@login_required
def events():
    """JSON endpoint for FullCalendar"""
    try:
        svc = _get_calendar_service(current_user.id)
        if not svc:
            return jsonify({"error": "not_connected"}), 401

        time_min = request.args.get("timeMin")
        time_max = request.args.get("timeMax")
        calendar_id = request.args.get("calendarId", "primary")

        if not time_min or not time_max:
            return jsonify({"error": "missing_time_range"}), 400

        items: List[Dict[str, Any]] = []
        page_token = None

        while True:
            resp = svc.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,       # expand recurring
                orderBy="startTime",
                pageToken=page_token,
                maxResults=2500,
            ).execute()

            items.extend(resp.get("items", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        events = []
        for ev in items:
            start = ev["start"].get("dateTime") or ev["start"].get("date")
            end   = ev["end"].get("dateTime")   or ev["end"].get("date")
            events.append({
                "id": ev.get("id"),
                "title": ev.get("summary", "(No title)"),
                "start": start,
                "end": end,
                "allDay": ("date" in ev["start"]) or ("date" in ev["end"]),
                "location": ev.get("location"),
                "url": ev.get("htmlLink"),
            })
        return jsonify(events)

    except Exception as e:
        current_app.logger.exception("Failed to fetch Google Calendar events")
        return jsonify({"error": "server_error", "details": str(e)}), 500


@google_bp.route("/counts")
@login_required
def counts():
    """Helper for KPIs"""
    svc = _get_calendar_service(current_user.id)
    if not svc:
        return jsonify({"error": "not_connected"}), 401

    # Get user's timezone from database
    from db.models import GoogleCalendarAuth
    auth_record = GoogleCalendarAuth.query.filter_by(user_id=current_user.id).first()
    user_tz = auth_record.time_zone if auth_record and auth_record.time_zone else 'Europe/Brussels'
    
    tz_user = tz.gettz(user_tz)
    now = dt.datetime.now(tz_user)
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_today = start_today + dt.timedelta(days=1)

    week_start = start_today - dt.timedelta(days=start_today.weekday())  # Monday
    week_end = week_start + dt.timedelta(days=7)

    def count_between(start, end):
        resp = svc.events().list(
            calendarId="primary",
            timeMin=_iso(start),
            timeMax=_iso(end),
            singleEvents=True,
            orderBy="startTime",
            maxResults=2500
        ).execute()
        return len(resp.get("items", []))

    return jsonify({
        "today": count_between(start_today, end_today),
        "week": count_between(week_start, week_end),
    })
