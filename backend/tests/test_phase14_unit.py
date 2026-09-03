"""PHASE 14.1 unit tests: dates, validation, idempotency, tenants, alternatives."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.appointments.idempotency import build_appointment_idempotency_key, normalize_title
from app.appointments.intents import CreateAppointmentArgs
from app.calendars.tools import generate_alternative_slots
from app.core.security import hash_password
from app.db.models import User
from app.telephony.service import find_user_by_twilio_phone, resolve_inbound_user
from app.voice.dates import resolve_relative_date, resolve_relative_datetime


def test_date_normalization_tomorrow_and_next_weekday() -> None:
    now = datetime(2026, 9, 3, 10, 0, tzinfo=ZoneInfo("Europe/Brussels"))  # Thursday
    assert resolve_relative_date("tomorrow", timezone_name="Europe/Brussels", now=now).isoformat() == (
        "2026-09-04"
    )
    assert resolve_relative_date("morgen", timezone_name="Europe/Brussels", now=now).isoformat() == (
        "2026-09-04"
    )
    nxt = resolve_relative_date("next Monday", timezone_name="Europe/Brussels", now=now)
    assert nxt.isoformat() == "2026-09-07"
    dt = resolve_relative_datetime(
        "this afternoon", timezone_name="Europe/Brussels", now=now
    )
    assert dt.hour == 12
    assert str(dt.tzinfo) == "Europe/Brussels"


def test_appointment_validation_rejects_empty_summary() -> None:
    with pytest.raises(ValidationError):
        CreateAppointmentArgs(
            summary="",
            datetime_start=datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc),
            datetime_end=datetime(2026, 9, 10, 16, 0, tzinfo=timezone.utc),
        )


def test_idempotency_key_stable_across_title_whitespace() -> None:
    start = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)
    a = build_appointment_idempotency_key(
        user_id=1,
        calendar_id="primary",
        start_utc=start,
        end_utc=end,
        summary="  Dentist  Visit ",
        call_sid="CA1",
    )
    b = build_appointment_idempotency_key(
        user_id=1,
        calendar_id="primary",
        start_utc=start,
        end_utc=end,
        summary="dentist visit",
        call_sid="CA1",
    )
    assert a == b
    assert normalize_title("  Hello ") == "hello"


def test_tenant_lookup_by_phone_and_account(db_session) -> None:
    user = User(
        username="tenant",
        email="tenant@example.com",
        password=hash_password("password123"),
        twilio_account_sid="ACtenant",
        twilio_phone_number="+32 470 12 34 56",
    )
    db_session.add(user)
    db_session.commit()

    found = find_user_by_twilio_phone(db_session, "+32470123456")
    assert found is not None
    assert found.id == user.id

    inbound = resolve_inbound_user(
        db_session, to_number="+32470123456", account_sid="ACother"
    )
    assert inbound is not None and inbound.id == user.id

    by_sid = resolve_inbound_user(
        db_session, to_number="+19999999999", account_sid="ACtenant"
    )
    assert by_sid is not None and by_sid.id == user.id

    assert resolve_inbound_user(db_session, to_number=None, account_sid="ACmissing") is None


def test_alternative_slots_calculated_locally_from_one_busy_window() -> None:
    start = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)
    cal = MagicMock()
    cal.get_busy_intervals.return_value = [
        {
            "start": (start + timedelta(hours=1)).isoformat(),
            "end": (start + timedelta(hours=2)).isoformat(),
        }
    ]
    alts = generate_alternative_slots(start, end, cal, num_alternatives=3)
    assert cal.get_busy_intervals.call_count == 1
    assert len(alts) >= 1
    assert (start + timedelta(hours=1)).isoformat() not in {a["start"] for a in alts}
