"""PHASE 4 multi-user / CallContext tests (tasks.txt)."""

from __future__ import annotations

import json

from app.core.security import hash_password
from app.db.models import CallSession, GoogleCalendarAuth, User
from app.telephony import service as telephony_service
from app.voice.context import CallContext, bind_call_context, current_call_context
from app.voice.session import load_voice_config


def test_resolve_inbound_user_by_phone_not_first_user(db_session) -> None:
    other = User(
        username="other",
        email="other@example.com",
        password=hash_password("password123"),
        twilio_phone_number="+11111111111",
        twilio_account_sid="ACother",
    )
    target = User(
        username="target",
        email="target@example.com",
        password=hash_password("password123"),
        twilio_phone_number="+19253965839",
        twilio_account_sid="ACtarget",
    )
    db_session.add_all([other, target])
    db_session.commit()

    resolved = telephony_service.resolve_inbound_user(
        db_session, to_number="+19253965839", account_sid="ACother"
    )
    assert resolved is not None
    assert resolved.id == target.id


def test_resolve_inbound_user_by_account_sid(db_session) -> None:
    user = User(
        username="acct",
        email="acct@example.com",
        password=hash_password("password123"),
        twilio_account_sid="AConly",
    )
    db_session.add(user)
    db_session.commit()

    resolved = telephony_service.resolve_inbound_user(
        db_session, to_number="+19999999999", account_sid="AConly"
    )
    assert resolved is not None
    assert resolved.id == user.id


def test_inbound_voice_creates_callsession_and_twiml(client, db_session) -> None:
    user = User(
        username="voiceuser",
        email="voice@example.com",
        password=hash_password("password123"),
        twilio_phone_number="+19253965839",
        twilio_account_sid="ACvoice",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    response = client.post(
        "/api/v1/telephony/twilio/voice",
        data={
            "CallSid": "CAphase4test",
            "AccountSid": "ACvoice",
            "To": "+19253965839",
            "From": "+15551234567",
        },
    )
    assert response.status_code == 200
    assert "application/xml" in response.headers.get("content-type", "")
    body = response.text
    assert "/ws/voice" in body
    assert f'value="{user.id}"' in body
    assert "CAphase4test" in body

    from sqlalchemy import select

    cs = db_session.scalar(
        select(CallSession).where(CallSession.call_sid == "CAphase4test")
    )
    assert cs is not None
    assert cs.user_id == user.id


def test_inbound_voice_unknown_number(client) -> None:
    response = client.post(
        "/api/v1/telephony/twilio/voice",
        data={
            "CallSid": "CAunknown",
            "AccountSid": "ACmissing",
            "To": "+10000000000",
            "From": "+15551234567",
        },
    )
    assert response.status_code == 200
    assert "not configured" in response.text.lower()


def test_resolve_call_context_from_custom_params(db_session) -> None:
    user = User(
        username="ctxuser",
        email="ctx@example.com",
        password=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    auth = GoogleCalendarAuth(
        user_id=user.id,
        calendar_id="cal-xyz",
        time_zone="Europe/Brussels",
        credentials_json="{}",
    )
    db_session.add(auth)
    db_session.commit()

    ctx = telephony_service.resolve_call_context_from_start(
        db_session,
        call_sid="CActx",
        custom_parameters={"user_id": str(user.id), "call_sid": "CActx"},
    )
    assert isinstance(ctx, CallContext)
    assert ctx.user_id == user.id
    assert ctx.calendar_id == "cal-xyz"
    assert ctx.timezone == "Europe/Brussels"


def test_load_voice_config_uses_user_config_json(db_session, monkeypatch) -> None:
    from app.voice import session as voice_session

    class _SessionProxy:
        def get(self, *args, **kwargs):
            return db_session.get(*args, **kwargs)

        def close(self) -> None:
            return None

    monkeypatch.setattr(voice_session, "SessionLocal", lambda: _SessionProxy())

    user = User(
        username="cfguser",
        email="cfg@example.com",
        password=hash_password("password123"),
        config_json=json.dumps(
            {
                "type": "Settings",
                "agent": {
                    "greeting": "Tenant hello",
                    "think": {"prompt": "Hi {current_date_context}"},
                },
            }
        ),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    ctx = CallContext(
        call_sid="CAcfg",
        user_id=user.id,
        timezone="UTC",
        calendar_id="primary",
    )
    config = load_voice_config(ctx)
    assert config["agent"]["greeting"] == "Tenant hello"
    assert "Current Date" in config["agent"]["think"]["prompt"]


def test_call_context_binding() -> None:
    ctx = CallContext(
        call_sid="CA1", user_id=7, timezone="UTC", calendar_id="primary"
    )
    token = bind_call_context(ctx)
    assert current_call_context.get() is ctx
    from app.voice.context import unbind_call_context

    unbind_call_context(token)
    assert current_call_context.get() is None


def test_google_calendar_service_requires_user_id() -> None:
    from app.calendars.providers.google import GoogleCalendarService

    assert GoogleCalendarService.__init__.__code__.co_varnames[:3] == (
        "self",
        "db",
        "user_id",
    )
