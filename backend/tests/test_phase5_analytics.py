"""Phase 5: dashboard KPIs, funnel, masking, SQL analytics, cache keys."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.analytics.aggregate import mask_phone_label, prior_period
from app.analytics.funnel import funnel_summary, link_call_session_on_book
from app.analytics.service import analytics_summary, process_twilio_data
from app.appointments.booking import book_appointment
from app.core.security import hash_password
from app.dashboard.service import dashboard_summary
from app.db.models import Appointment, CallSession, TwilioCall, User


def _user(db, *, username: str, email: str) -> User:
    user = User(username=username, email=email, password=hash_password("password123"))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_mask_phone_label() -> None:
    assert mask_phone_label("+32470123456") == "***3456"
    assert mask_phone_label("12") == "***"


def test_prior_period_equal_length() -> None:
    assert prior_period(date(2026, 9, 1), date(2026, 9, 7)) == (
        date(2026, 8, 25),
        date(2026, 8, 31),
    )


def test_process_twilio_masks_top_numbers() -> None:
    calls = [
        {
            "sid": "CA1",
            "from": "+32470123456",
            "to": "+32470999999",
            "start_time": "2026-09-01T10:00:00Z",
            "duration_sec": 90,
            "price": 0.02,
            "price_unit": "USD",
        }
    ]
    result = process_twilio_data(calls, date(2026, 9, 1), date(2026, 9, 1))
    assert result is not None
    assert result["top_numbers"]["labels"] == ["***9999"]
    assert result["currency"] == "USD"


def test_dashboard_operational_kpis(db_session, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "deepgram_api_key", "dg")
    user = _user(db_session, username="kpi", email="kpi@example.com")
    user.twilio_account_sid = "AC"
    user.twilio_auth_token = "tok"
    db_session.commit()

    now = datetime.now(timezone.utc)
    CallSession.create(
        call_sid="CAok",
        from_number="+1",
        to_number="+2",
        user_id=user.id,
        session=db_session,
    )
    ok = db_session.query(CallSession).filter_by(call_sid="CAok").one()
    ok.outcome = "completed"
    ok.started_at = now
    CallSession.create(
        call_sid="CAfail",
        from_number="+1",
        to_number="+2",
        user_id=user.id,
        session=db_session,
    )
    bad = db_session.query(CallSession).filter_by(call_sid="CAfail").one()
    bad.outcome = "failed"
    bad.terminal_reason = "deepgram:auth"
    bad.started_at = now
    db_session.commit()

    summary = dashboard_summary(db_session, user.id)
    assert summary["operational"]["calls_today"]["value"] >= 2
    assert summary["operational"]["attention_needed"]["value"] >= 1
    assert summary["operational"]["completion_rate"]["denominator"] >= 1
    assert "definition" in summary["operational"]["calls_today"]
    assert summary["freshness"]["generated_at"]


def test_funnel_idempotent_booking_link(db_session) -> None:
    user = _user(db_session, username="funnel", email="funnel@example.com")
    cs = CallSession.create(
        call_sid="CAbook",
        from_number="+1",
        to_number="+2",
        user_id=user.id,
        session=db_session,
    )
    cs.outcome = "completed"
    db_session.commit()

    start = datetime.now(timezone.utc) + timedelta(days=1)
    end = start + timedelta(minutes=30)
    appt = book_appointment(
        db_session,
        user.id,
        summary="Consult",
        start_datetime=start,
        end_datetime=end,
        timezone_name="UTC",
        call_sid="CAbook",
    )
    assert appt.callsession_id == cs.id
    db_session.refresh(cs)
    assert cs.outcome == "booked"

    # Retry same idempotency → same appointment, funnel stage still once
    again = book_appointment(
        db_session,
        user.id,
        summary="Consult",
        start_datetime=start,
        end_datetime=end,
        timezone_name="UTC",
        call_sid="CAbook",
    )
    assert again.id == appt.id

    funnel = funnel_summary(
        db_session,
        user.id,
        start=date.today() - timedelta(days=1),
        end=date.today() + timedelta(days=1),
        timezone_name="UTC",
    )
    stages = {s["id"]: s["count"] for s in funnel["stages"]}
    assert stages["started"] >= 1
    assert stages["booking_attempted"] >= 1
    assert stages["booked"] >= 1


def test_funnel_unknown_historical(db_session) -> None:
    user = _user(db_session, username="unk", email="unk@example.com")
    CallSession.create(
        call_sid="CAold",
        from_number="+1",
        to_number="+2",
        user_id=user.id,
        session=db_session,
    )
    # leave outcome null, status default active → unknown
    funnel = funnel_summary(
        db_session,
        user.id,
        start=date.today() - timedelta(days=1),
        end=date.today() + timedelta(days=1),
    )
    unknown = next(s for s in funnel["stages"] if s["id"] == "unknown")
    assert unknown["count"] >= 1


def test_analytics_sql_summary_and_compare(db_session) -> None:
    user = _user(db_session, username="agg", email="agg@example.com")
    now = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
    db_session.add(
        TwilioCall(
            user_id=user.id,
            sid="CAtw1",
            from_number="+32470123456",
            to_number="+32470999999",
            start_time=now,
            duration_sec=120,
            price=0.05,
            price_unit="USD",
            status="completed",
        )
    )
    db_session.add(
        TwilioCall(
            user_id=user.id,
            sid="CAtw2",
            from_number="+32470123456",
            to_number="+32470999999",
            start_time=now - timedelta(days=10),
            duration_sec=60,
            price=0.02,
            price_unit="USD",
            status="completed",
        )
    )
    db_session.commit()

    summary = analytics_summary(
        db_session,
        user.id,
        start=date(2026, 9, 1),
        end=date(2026, 9, 3),
        timezone_name="UTC",
        compare=True,
    )
    assert summary["total_calls"] == 1
    assert summary["top_numbers"]["labels"] == ["***9999"]
    assert summary["currency"] == "USD"
    assert summary["generated_at"]
    assert summary["funnel"] is not None
    assert summary["comparison"] is not None
    assert summary["comparison"]["total_calls"]["current"] == 1.0


def test_link_call_session_on_book_idempotent(db_session) -> None:
    user = _user(db_session, username="link", email="link@example.com")
    cs = CallSession.create(
        call_sid="CAlink",
        from_number="+1",
        to_number="+2",
        user_id=user.id,
        session=db_session,
    )
    appt = Appointment(
        user_id=user.id,
        summary="X",
        start_datetime=datetime.now(timezone.utc),
        end_datetime=datetime.now(timezone.utc) + timedelta(minutes=30),
        timezone="UTC",
        status="confirmed",
    )
    db_session.add(appt)
    db_session.flush()
    link_call_session_on_book(
        db_session, user_id=user.id, call_sid="CAlink", appointment=appt
    )
    link_call_session_on_book(
        db_session, user_id=user.id, call_sid="CAlink", appointment=appt
    )
    db_session.commit()
    assert appt.callsession_id == cs.id
    db_session.refresh(cs)
    assert cs.outcome == "booked"
