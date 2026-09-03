"""P7-02 adversarial regressions for Phase 0 boundaries."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from twilio.request_validator import RequestValidator

from app.appointments import booking as booking_service
from app.appointments import service as appointments_service
from app.appointments.policy import BookingPolicy, save_booking_policy
from app.core.config import settings
from app.core.security import hash_password
from app.db.models import CallSession, User
from app.telephony import service as telephony_service
from app.telephony.stream_tokens import issue_stream_token

# Twilio SID shape: 2-char prefix + 32 alnum (assert_valid_twilio_sid).
AC_SIG = "ACadvsigxxxxxxxxxxxxxxxxxxxxxxxxxx"
CA_FORGED = "CAadvforgedxxxxxxxxxxxxxxxxxxxxxxx"
CA_TOKA = "CAadvtokaxxxxxxxxxxxxxxxxxxxxxxxxx"
CA_TOKB = "CAadvtokbxxxxxxxxxxxxxxxxxxxxxxxxx"
AC_SSRF = "ACadvssrfxxxxxxxxxxxxxxxxxxxxxxxxx"
CA_SSRF = "CAadvssrfxxxxxxxxxxxxxxxxxxxxxxxxx"
RE_SSRF = "RExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"


def _sign(auth_token: str, url: str, params: dict[str, str]) -> str:
    return RequestValidator(auth_token).compute_signature(url, params)


def test_forged_twilio_signature_rejected(client, db_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "twilio_auth_token", "real-token")
    monkeypatch.setattr(settings, "public_base_url", "http://localhost:8000")
    user = User(
        username="adv_sig",
        email="adv_sig@example.com",
        password=hash_password("password123"),
        twilio_phone_number="+15550001111",
        twilio_account_sid=AC_SIG,
        twilio_auth_token="real-token",
    )
    db_session.add(user)
    db_session.commit()

    params = {
        "CallSid": CA_FORGED,
        "AccountSid": AC_SIG,
        "To": "+15550001111",
        "From": "+15551230000",
    }
    url = "http://localhost:8000/api/v1/telephony/twilio/voice"
    forged = _sign("wrong-token", url, params)
    response = client.post(
        "/api/v1/telephony/twilio/voice",
        data=params,
        headers={"X-Twilio-Signature": forged},
    )
    assert response.status_code == 403


def test_stream_token_wrong_call_sid_rejected(db_session) -> None:
    user = User(
        username="adv_tok",
        email="adv_tok@example.com",
        password=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    a = CallSession.create(
        call_sid=CA_TOKA,
        from_number="+1",
        to_number="+2",
        user_id=user.id,
        session=db_session,
    )
    b = CallSession.create(
        call_sid=CA_TOKB,
        from_number="+1",
        to_number="+2",
        user_id=user.id,
        session=db_session,
    )
    raw = issue_stream_token(db_session, a)
    with pytest.raises(ValueError):
        telephony_service.resolve_call_context_from_start(
            db_session,
            call_sid=b.call_sid,
            custom_parameters={"stream_token": raw},
        )


def test_cross_tenant_appointment_isolation(client, db_session) -> None:
    owner = User(
        username="adv_owner",
        email="adv_owner@example.com",
        password=hash_password("password123"),
    )
    other = User(
        username="adv_other",
        email="adv_other@example.com",
        password=hash_password("password123"),
    )
    save_booking_policy(
        owner,
        BookingPolicy(
            default_service_duration_minutes=30,
            business_hours={"monday": [{"start": "09:00", "end": "17:00"}]},
        ),
    )
    db_session.add_all([owner, other])
    db_session.commit()
    db_session.refresh(owner)
    db_session.refresh(other)

    start = datetime(2026, 9, 7, 11, 0, tzinfo=timezone.utc)
    appt = booking_service.book_appointment(
        db_session,
        owner.id,
        summary="Private",
        start_datetime=start,
    )
    assert appointments_service.get_appointment(db_session, other.id, appt.id) is None

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "adv_other@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    response = client.get(f"/api/v1/appointments/{appt.id}")
    assert response.status_code == 404


def test_recording_ignores_webhook_supplied_host(db_session) -> None:
    user = User(
        username="adv_ssrf",
        email="adv_ssrf@example.com",
        password=hash_password("password123"),
        twilio_account_sid=AC_SSRF,
        twilio_auth_token="tok",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    CallSession.create(
        call_sid=CA_SSRF,
        from_number="+1",
        to_number="+2",
        user_id=user.id,
        session=db_session,
    )
    result = telephony_service.process_recording_webhook(
        db_session,
        {
            "AccountSid": user.twilio_account_sid,
            "CallSid": CA_SSRF,
            "RecordingSid": RE_SSRF,
            "RecordingUrl": "https://169.254.169.254/latest/meta-data",
        },
        enqueue=False,
    )
    assert result["ok"] is True
    cs = db_session.query(CallSession).filter_by(call_sid=CA_SSRF).one()
    assert cs.recording_url is not None
    assert "169.254" not in cs.recording_url
    assert cs.recording_url.startswith("https://api.twilio.com/")
