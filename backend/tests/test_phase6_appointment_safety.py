"""PHASE 6 appointment safety tests (tasks.txt)."""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from app.appointments.intents import AppointmentIntent, CancelAppointmentArgs
from app.calendars import tools as calendar_tools
from app.calendars.tool_schemas import VOICE_TOOL_DEFINITIONS
from app.calendars.tools import FUNCTION_MAP
from app.voice.context import CallContext
from app.voice.dates import (
    next_weekday_date,
    resolve_relative_date,
    resolve_relative_datetime,
)
from app.voice.session import load_voice_config


def test_tool_schemas_match_function_map() -> None:
    schema_names = {item["name"] for item in VOICE_TOOL_DEFINITIONS}
    # get_appointment_details is a compat alias; not exposed to the LLM.
    assert schema_names <= set(FUNCTION_MAP)
    for item in VOICE_TOOL_DEFINITIONS:
        fn = FUNCTION_MAP[item["name"]]
        params = set(inspect.signature(fn).parameters) - {"kwargs", "_kwargs"}
        # Accept **_kwargs tools: required schema props must be parameters.
        required = set(item["parameters"].get("required", []))
        assert required <= params | {"kwargs"}


def test_cancel_rejects_datetime_without_event_id() -> None:
    result = calendar_tools.cancel_appointment(
        datetime_start="2026-09-15T12:00:00Z",
        confirmed=True,
    )
    assert result["success"] is False
    assert "event_id" in result["error"].lower() or "approximate" in result["error"].lower()


def test_reschedule_rejects_original_datetime_without_event_id() -> None:
    result = calendar_tools.reschedule_appointment(
        original_datetime="2026-09-15T12:00:00Z",
        new_datetime_start="2026-09-16T12:00:00Z",
        new_datetime_end="2026-09-16T13:00:00Z",
        confirmed=True,
    )
    assert result["success"] is False
    assert "event_id" in result["error"].lower() or "approximate" in result["error"].lower()


def test_create_requires_confirmation_before_mutation(monkeypatch) -> None:
    called = {"create": False}

    class _Svc:
        db = MagicMock()

        def create_event(self, **_kwargs):
            called["create"] = True
            return {}

    monkeypatch.setattr(
        calendar_tools,
        "_resolve_service",
        lambda: (_Svc(), None, "UTC", "primary"),
    )
    start = datetime(2026, 9, 15, 14, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)
    result = calendar_tools.create_calendar_event(
        summary="Consult",
        datetime_start=start,
        datetime_end=end,
        confirmed=False,
    )
    assert result["needs_confirmation"] is True
    assert called["create"] is False
    assert "book" in result["confirmation_prompt"].lower()


def test_cancel_confirmation_gate(monkeypatch) -> None:
    class _Events:
        def get(self, **_kwargs):
            return self

        def execute(self):
            return {
                "id": "evt1",
                "summary": "Dental",
                "start": {"dateTime": "2026-09-15T14:00:00Z"},
                "end": {"dateTime": "2026-09-15T15:00:00Z"},
            }

    class _Service:
        def events(self):
            return _Events()

    class _Svc:
        db = MagicMock()
        service = _Service()

        def delete_event(self, *_a, **_k):
            raise AssertionError("delete must not run before confirmation")

    monkeypatch.setattr(
        calendar_tools,
        "_resolve_service",
        lambda: (_Svc(), None, "UTC", "primary"),
    )
    result = calendar_tools.cancel_appointment(event_id="evt1", confirmed=False)
    assert result["needs_confirmation"] is True
    assert result["pending"]["event_id"] == "evt1"


def test_relative_dates_zoneinfo() -> None:
    # Europe/Brussels winter (UTC+1)
    winter = datetime(2026, 1, 14, 10, 0, tzinfo=ZoneInfo("Europe/Brussels"))  # Wednesday
    assert resolve_relative_date("today", timezone_name="Europe/Brussels", now=winter).isoformat() == "2026-01-14"
    assert resolve_relative_date("tomorrow", timezone_name="Europe/Brussels", now=winter).isoformat() == "2026-01-15"
    assert resolve_relative_date("next Friday", timezone_name="Europe/Brussels", now=winter).isoformat() == "2026-01-16"
    assert resolve_relative_date("next Wednesday", timezone_name="Europe/Brussels", now=winter).isoformat() == "2026-01-21"

    evening = resolve_relative_datetime(
        "this evening", timezone_name="Europe/Brussels", now=winter
    )
    assert evening.hour == 17
    assert evening.tzinfo == ZoneInfo("Europe/Brussels")


def test_relative_dates_dst_spring_forward() -> None:
    # 2026-03-29 is DST start in Europe/Brussels (02:00 → 03:00).
    before = datetime(2026, 3, 28, 12, 0, tzinfo=ZoneInfo("Europe/Brussels"))
    nxt = resolve_relative_date("tomorrow", timezone_name="Europe/Brussels", now=before)
    assert nxt.isoformat() == "2026-03-29"
    # Local noon next day still resolves cleanly across the gap.
    local = resolve_relative_datetime(
        "tomorrow", timezone_name="Europe/Brussels", now=before
    )
    assert local.date().isoformat() == "2026-03-29"
    assert local.tzinfo == ZoneInfo("Europe/Brussels")


def test_next_weekday_skips_today() -> None:
    friday = datetime(2026, 9, 4, 9, 0, tzinfo=ZoneInfo("UTC"))  # Friday
    assert next_weekday_date(friday, 4).isoformat() == "2026-09-11"


def test_appointment_intent_schema() -> None:
    intent = AppointmentIntent(
        operation="cancel",
        event_id="abc",
        timezone="Europe/Brussels",
        confirmed=False,
    )
    assert intent.operation == "cancel"
    args = CancelAppointmentArgs(event_id="abc", confirmed=True)
    assert args.confirmed is True


def test_load_voice_config_injects_tool_schemas(db_session, monkeypatch) -> None:
    from app.core.security import hash_password
    from app.db.models import User
    from app.voice import session as voice_session

    class _SessionProxy:
        def get(self, *args, **kwargs):
            return db_session.get(*args, **kwargs)

        def close(self) -> None:
            return None

    monkeypatch.setattr(voice_session, "SessionLocal", lambda: _SessionProxy())
    user = User(
        username="schemauser",
        email="schema@example.com",
        password=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    cfg = load_voice_config(
        CallContext(
            call_sid="CAschema",
            user_id=user.id,
            timezone="UTC",
            calendar_id="primary",
        )
    )
    names = {f["name"] for f in cfg["agent"]["think"]["functions"]}
    assert names == {item["name"] for item in VOICE_TOOL_DEFINITIONS}
    assert "find_appointments" in names
    assert "event_id" in str(cfg["agent"]["think"]["functions"])
    assert "confirmed=true" in cfg["agent"]["think"]["prompt"]
