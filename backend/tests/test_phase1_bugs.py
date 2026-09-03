"""PHASE 1 bug-fix tests (tasks.txt)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.analytics.service import exclusive_end_datetime, process_twilio_data
from app.auth import service as auth_service
from app.core.security import (
    create_password_reset_token,
    hash_password,
    verify_password,
    verify_password_reset_token,
)
from app.db.models import CallSession, User
from app.telephony import service as telephony_service


def test_analytics_half_open_date_filter_includes_end_day() -> None:
    """2026-09-01 → 2026-09-03 includes late evening on Sept 3."""
    calls = [
        {
            "sid": "CA1",
            "from": "+10000000001",
            "to": "+10000000002",
            "start_time": "2026-09-01T10:00:00Z",
            "duration_sec": 60,
            "price": 0.01,
        },
        {
            "sid": "CA2",
            "from": "+10000000001",
            "to": "+10000000002",
            "start_time": "2026-09-03T23:30:00Z",
            "duration_sec": 60,
            "price": 0.01,
        },
        {
            "sid": "CA3",
            "from": "+10000000001",
            "to": "+10000000002",
            "start_time": "2026-09-04T00:00:00Z",
            "duration_sec": 60,
            "price": 0.01,
        },
    ]
    result = process_twilio_data(calls, date(2026, 9, 1), date(2026, 9, 3))
    assert result is not None
    assert result["total_calls"] == 2
    assert exclusive_end_datetime(date(2026, 9, 3)) == datetime(
        2026, 9, 4, 0, 0, tzinfo=timezone.utc
    )


def test_twilio_webhook_unknown_account_sid(db_session) -> None:
    result = telephony_service.process_recording_webhook(
        db_session,
        {
            "AccountSid": "ACunknown",
            "CallSid": "CAabc",
            "RecordingSid": "RExyz",
            "RecordingUrl": "https://api.twilio.com/rec",
        },
        enqueue=False,
    )
    assert result["ok"] is True
    assert result["enqueued"] is False


def test_twilio_webhook_uses_twilio_account_sid_field(db_session) -> None:
    user = User(
        username="twilio_user",
        email="twilio@example.com",
        password=hash_password("password123"),
        twilio_account_sid="ACknown",
        twilio_auth_token="secret",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    CallSession.create(
        call_sid="CAknown",
        from_number="+15550001111",
        to_number="+15550002222",
        user_id=user.id,
        session=db_session,
    )

    result = telephony_service.process_recording_webhook(
        db_session,
        {
            "AccountSid": "ACknown",
            "CallSid": "CAknown",
            "RecordingSid": "REknown",
            "RecordingUrl": "https://api.twilio.com/rec",
        },
        enqueue=False,
    )
    assert result["ok"] is True
    cs = db_session.query(CallSession).filter_by(call_sid="CAknown").one()
    assert cs.recording_sid == "REknown"
    assert cs.recording_url == "https://api.twilio.com/rec"


def test_password_reset_generic_message_unknown_email(client) -> None:
    response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "missing@example.com"},
    )
    assert response.status_code == 200
    assert response.json()["message"] == auth_service.GENERIC_RESET_MESSAGE


def test_password_reset_flow(client, db_session) -> None:
    user = User(
        username="resetme",
        email="resetme@example.com",
        password=hash_password("oldpassword"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    req = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "resetme@example.com"},
    )
    assert req.status_code == 200
    assert req.json()["message"] == auth_service.GENERIC_RESET_MESSAGE

    token = create_password_reset_token(user_id=user.id)
    assert verify_password_reset_token(token) == user.id

    bad = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": "not-a-token", "password": "newpassword1"},
    )
    assert bad.status_code == 400

    ok = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "password": "newpassword1"},
    )
    assert ok.status_code == 200

    db_session.refresh(user)
    assert verify_password("newpassword1", user.password)
    assert not verify_password("oldpassword", user.password)

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "resetme@example.com", "password": "newpassword1"},
    )
    assert login.status_code == 200
