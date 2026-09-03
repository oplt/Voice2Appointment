"""P7-05 end-to-end receptionist journey (vendor fakes only)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from twilio.request_validator import RequestValidator

from app.appointments import booking as booking_service
from app.appointments.policy import BookingPolicy, save_booking_policy
from app.calls import service as calls_service
from app.core.config import settings
from app.core.security import hash_password
from app.dashboard.service import dashboard_summary
from app.db.models import CallSession, User
from app.telephony.lifecycle import STATUS_COMPLETED, transition_call_session


def _sign(auth_token: str, url: str, params: dict[str, str]) -> str:
    return RequestValidator(auth_token).compute_signature(url, params)


@pytest.mark.e2e
def test_receptionist_journey_book_and_dashboard(client, db_session, monkeypatch) -> None:
    token = "e2e-voice-token"
    monkeypatch.setattr(settings, "twilio_auth_token", token)
    monkeypatch.setattr(settings, "public_base_url", "http://localhost:8000")

    user = User(
        username="e2e_owner",
        email="e2e_owner@example.com",
        password=hash_password("password123"),
        twilio_phone_number="+15550002222",
        twilio_account_sid="ACe2e00000000000000000000000000000",
        twilio_auth_token=token,
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

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "e2e_owner@example.com", "password": "password123"},
    )
    assert login.status_code == 200

    params = {
        "CallSid": "CAe2ejourney0000000000000000000000",
        "AccountSid": "ACe2e00000000000000000000000000000",
        "To": "+15550002222",
        "From": "+15559876543",
    }
    url = "http://localhost:8000/api/v1/telephony/twilio/voice"
    voice = client.post(
        "/api/v1/telephony/twilio/voice",
        data=params,
        headers={"X-Twilio-Signature": _sign(token, url, params)},
    )
    assert voice.status_code == 200
    assert "stream_token=" in voice.text
    assert 'name="user_id"' not in voice.text

    cs = db_session.query(CallSession).filter_by(call_sid=params["CallSid"]).one()
    assert cs.user_id == user.id

    # Replay must not create a duplicate session (idempotent inbound).
    replay = client.post(
        "/api/v1/telephony/twilio/voice",
        data=params,
        headers={"X-Twilio-Signature": _sign(token, url, params)},
    )
    assert replay.status_code == 200
    assert (
        db_session.query(CallSession).filter_by(call_sid=params["CallSid"]).count() == 1
    )

    start = datetime(2026, 9, 7, 14, 0, tzinfo=timezone.utc)
    appt = booking_service.book_appointment(
        db_session,
        user.id,
        summary="E2E consult",
        start_datetime=start,
        call_sid=params["CallSid"],
        client_phone="+15559876543",
    )
    again = booking_service.book_appointment(
        db_session,
        user.id,
        summary="E2E consult",
        start_datetime=start,
        call_sid=params["CallSid"],
        client_phone="+15559876543",
    )
    assert again.id == appt.id

    transition_call_session(
        db_session,
        call_sid=params["CallSid"],
        new_status=STATUS_COMPLETED,
        outcome="booked",
        duration_seconds=120,
    )

    summary = dashboard_summary(db_session, user.id)
    assert summary["appointments_today"] >= 0
    assert summary["recent_calls"] >= 1

    rows, _ = calls_service.list_call_sessions(db_session, user.id, limit=10)
    assert any(r.call_sid == params["CallSid"] for r in rows)
    listed = client.get("/api/v1/calls")
    assert listed.status_code == 200
    body = listed.json()
    assert body["items"]
    assert "transcript" not in body["items"][0]

    # Forged-tenant negative: other user cannot see the appointment.
    other = User(
        username="e2e_other",
        email="e2e_other@example.com",
        password=hash_password("password123"),
    )
    db_session.add(other)
    db_session.commit()
    other_login = client.post(
        "/api/v1/auth/login",
        json={"email": "e2e_other@example.com", "password": "password123"},
    )
    assert other_login.status_code == 200
    denied = client.get(f"/api/v1/appointments/{appt.id}")
    assert denied.status_code == 404
