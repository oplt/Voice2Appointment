"""PHASE 0 critical security / integrity tests."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from twilio.request_validator import RequestValidator

from app.appointments import booking as booking_service
from app.appointments.policy import BookingConflictError, save_booking_policy, BookingPolicy
from app.auth import service as auth_service
from app.core.config import settings
from app.core.security import hash_password
from app.db.models import Appointment, CallSession, User
from app.telephony import service as telephony_service
from app.telephony.security import (
    assert_valid_twilio_sid,
    is_allowed_twilio_media_host,
    twilio_recording_api_url,
)
from app.telephony.stream_tokens import consume_stream_token, issue_stream_token
from app.voice.context import CallContext
from app.voice.session import VoiceSession, get_call_transcript


def _sign(auth_token: str, url: str, params: dict[str, str]) -> str:
    return RequestValidator(auth_token).compute_signature(url, params)


# --- P0-01 / migrations smoke via model metadata ---


def test_phase0_model_has_stream_token_and_provider_sync(db_engine) -> None:
    call_cols = {c.name for c in CallSession.__table__.columns}
    appt_cols = {c.name for c in Appointment.__table__.columns}
    assert "stream_token_hash" in call_cols
    assert "stream_token_expires_at" in call_cols
    assert "stream_token_consumed_at" in call_cols
    assert "provider_sync_status" in appt_cols


def test_alembic_single_head() -> None:
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = Path(__file__).resolve().parents[1] / "migrations"
    cfg = Config()
    cfg.set_main_option("script_location", str(root))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1, heads
    assert heads[0] == "c9d0e1f2a3b4"


# --- P0-02 Twilio signatures ---


def test_twilio_webhook_rejects_missing_signature(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "twilio_auth_token", "testtoken")
    response = client.post(
        "/api/v1/telephony/twilio/recording",
        data={
            "AccountSid": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            "CallSid": "CAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            "RecordingSid": "RExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            "RecordingUrl": "https://api.twilio.com/rec",
        },
    )
    assert response.status_code == 403


def test_twilio_webhook_accepts_valid_signature(client, db_session, monkeypatch) -> None:
    token = "testauthtoken"
    monkeypatch.setattr(settings, "twilio_auth_token", token)
    monkeypatch.setattr(settings, "public_base_url", "http://localhost:8000")

    user = User(
        username="siguser",
        email="sig@example.com",
        password=hash_password("password123"),
        twilio_account_sid="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        twilio_auth_token=token,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    CallSession.create(
        call_sid="CAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        from_number="+1",
        to_number="+2",
        user_id=user.id,
        session=db_session,
    )

    params = {
        "AccountSid": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "CallSid": "CAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "RecordingSid": "RExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "RecordingUrl": "https://api.twilio.com/2010-04-01/Accounts/AC/Recordings/RE",
    }
    url = "http://localhost:8000/api/v1/telephony/twilio/recording"
    sig = _sign(token, url, params)
    response = client.post(
        "/api/v1/telephony/twilio/recording",
        data=params,
        headers={"X-Twilio-Signature": sig},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


# --- P0-03 stream tokens ---


def test_stream_token_one_use_and_ignores_forged_user(db_session) -> None:
    user = User(
        username="tokuser",
        email="tok@example.com",
        password=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    cs = CallSession.create(
        call_sid="CAyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy",
        from_number="+1",
        to_number="+2",
        user_id=user.id,
        session=db_session,
    )
    raw = issue_stream_token(db_session, cs)
    consumed = consume_stream_token(
        db_session, call_sid=cs.call_sid, raw_token=raw
    )
    assert consumed.user_id == user.id
    with pytest.raises(ValueError, match="already used"):
        consume_stream_token(db_session, call_sid=cs.call_sid, raw_token=raw)

    raw2 = issue_stream_token(db_session, cs)
    ctx = telephony_service.resolve_call_context_from_start(
        db_session,
        call_sid=cs.call_sid,
        custom_parameters={"user_id": "99999", "stream_token": raw2},
    )
    assert ctx.user_id == user.id


# --- P0-04 recording hardening ---


def test_recording_sid_and_host_guards() -> None:
    with pytest.raises(ValueError):
        assert_valid_twilio_sid("../etc/passwd", prefix="RE")
    with pytest.raises(ValueError):
        assert_valid_twilio_sid("REshort", prefix="RE")
    assert is_allowed_twilio_media_host("api.twilio.com")
    assert not is_allowed_twilio_media_host("evil.example.com")
    url = twilio_recording_api_url(
        account_sid="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        recording_sid="RExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    )
    assert url.startswith("https://api.twilio.com/")


def test_recording_ownership_mismatch_rejected(db_session) -> None:
    owner = User(
        username="owner",
        email="owner@example.com",
        password=hash_password("password123"),
        twilio_account_sid="ACaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        twilio_auth_token="tok",
    )
    other = User(
        username="other",
        email="other@example.com",
        password=hash_password("password123"),
        twilio_account_sid="ACbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        twilio_auth_token="tok2",
    )
    db_session.add_all([owner, other])
    db_session.commit()
    db_session.refresh(owner)
    db_session.refresh(other)
    CallSession.create(
        call_sid="CAaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        from_number="+1",
        to_number="+2",
        user_id=owner.id,
        session=db_session,
    )
    result = telephony_service.process_recording_webhook(
        db_session,
        {
            "AccountSid": other.twilio_account_sid,
            "CallSid": "CAaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "RecordingSid": "RExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            "RecordingUrl": "https://evil.example/x",
        },
        enqueue=False,
    )
    assert result["ok"] is False


# --- P0-05 transcript isolation ---


def test_transcript_isolated_per_session() -> None:
    a = VoiceSession(MagicMock(), call_context=CallContext("CA1", 1, "UTC", "primary"))
    b = VoiceSession(MagicMock(), call_context=CallContext("CA2", 2, "UTC", "primary"))
    a.transcript.append("user: hello A")
    b.transcript.append("user: hello B")
    assert a.transcript != b.transcript
    a.transcript.clear()
    assert b.transcript == ["user: hello B"]
    assert get_call_transcript() == ""


# --- P0-07 / P0-08 booking policy + idempotency ---


def test_book_appointment_policy_and_idempotent(db_session) -> None:
    user = User(
        username="booker",
        email="booker@example.com",
        password=hash_password("password123"),
    )
    save_booking_policy(
        user,
        BookingPolicy(
            default_service_duration_minutes=30,
            business_hours={"monday": [{"start": "09:00", "end": "17:00"}]},
        ),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    # Pick a Monday 10:00 UTC
    start = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)  # Monday
    first = booking_service.book_appointment(
        db_session,
        user.id,
        summary="Consultation",
        start_datetime=start,
        timezone_name="UTC",
    )
    second = booking_service.book_appointment(
        db_session,
        user.id,
        summary="Consultation",
        start_datetime=start,
        timezone_name="UTC",
    )
    assert first.id == second.id

    with pytest.raises(BookingConflictError):
        booking_service.book_appointment(
            db_session,
            user.id,
            summary="Other",
            start_datetime=start + timedelta(minutes=15),
            end_datetime=start + timedelta(minutes=45),
            timezone_name="UTC",
        )


def test_book_pending_then_provider(db_session) -> None:
    user = User(
        username="prov",
        email="prov@example.com",
        password=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    start = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    calls = {"n": 0}

    def provider_create(**kwargs):
        calls["n"] += 1
        return {"id": "evt1", "htmlLink": "https://cal.example/evt1"}

    row = booking_service.book_appointment(
        db_session,
        user.id,
        summary="Meet",
        start_datetime=start,
        end_datetime=start + timedelta(minutes=30),
        timezone_name="UTC",
        provider_create=provider_create,
    )
    assert row.google_calendar_event_id == "evt1"
    assert row.provider_sync_status == "confirmed"
    assert calls["n"] == 1

    again = booking_service.book_appointment(
        db_session,
        user.id,
        summary="Meet",
        start_datetime=start,
        end_datetime=start + timedelta(minutes=30),
        timezone_name="UTC",
        provider_create=provider_create,
    )
    assert again.id == row.id
    assert calls["n"] == 1  # no second provider write


# --- P0-09 password reset logs ---


def test_password_reset_logs_have_no_secrets(db_session, caplog, monkeypatch) -> None:
    monkeypatch.setattr(settings, "mail_username", None)
    monkeypatch.setattr(settings, "mail_password", None)
    monkeypatch.setattr(settings, "app_env", "development")
    user = User(
        username="resetlog",
        email="resetlog@example.com",
        password=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()

    with caplog.at_level(logging.INFO):
        msg = auth_service.request_password_reset(db_session, user.email)
    assert msg == auth_service.GENERIC_RESET_MESSAGE
    joined = " ".join(r.message for r in caplog.records)
    assert "resetlog@example.com" not in joined
    assert "token=" not in joined
    assert "/reset-password" not in joined
