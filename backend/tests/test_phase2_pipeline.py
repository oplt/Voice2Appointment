"""Phase 2: call lifecycle, Deepgram reconnect, pipeline contract, media metrics."""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from twilio.request_validator import RequestValidator

from app.auth.service import hash_password
from app.core.config import Settings, settings
from app.db.models import CallSession, User
from app.telephony import lifecycle as call_lifecycle
from app.voice.context import CallContext
from app.voice.providers import deepgram as deepgram_mod
from app.voice.session import VoiceSession


def _sign(token: str, url: str, params: dict[str, str]) -> str:
    return RequestValidator(token).compute_signature(url, params)


# --- P2-01 lifecycle ---


def test_lifecycle_transition_table(db_session) -> None:
    user = User(
        username="lifeuser",
        email="life@example.com",
        password=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    cs = CallSession.create(
        call_sid="CAlifecycle000000000000000000001",
        from_number="+1",
        to_number="+2",
        user_id=user.id,
        session=db_session,
    )
    assert cs.status == "active"

    call_lifecycle.mark_connected(db_session, cs.call_sid)
    db_session.refresh(cs)
    assert cs.status == "connected"

    call_lifecycle.finalize_voice_session(
        db_session,
        call_sid=cs.call_sid,
        status=call_lifecycle.STATUS_COMPLETED,
        terminal_reason="websocket:twilio_stop",
        transcript="user: hello\nassistant: hi",
        outcome="completed",
    )
    db_session.refresh(cs)
    assert cs.status == "completed"
    assert cs.transcript is not None
    assert "hello" in cs.transcript
    assert cs.ended_at is not None
    assert (cs.duration_seconds or 0) >= 0

    # Replay is harmless
    again = call_lifecycle.finalize_voice_session(
        db_session,
        call_sid=cs.call_sid,
        status=call_lifecycle.STATUS_COMPLETED,
        terminal_reason="websocket:twilio_stop",
        transcript="ignored",
        outcome="completed",
    )
    assert again is not None
    assert again.status == "completed"
    assert "hello" in (again.transcript or "")


def test_lifecycle_rejects_illegal_transition(db_session) -> None:
    user = User(
        username="rejuser",
        email="rej@example.com",
        password=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    cs = CallSession.create(
        call_sid="CAlifecycle000000000000000000002",
        from_number="+1",
        to_number="+2",
        user_id=user.id,
        session=db_session,
    )
    call_lifecycle.finalize_voice_session(
        db_session,
        call_sid=cs.call_sid,
        status=call_lifecycle.STATUS_REJECTED,
        terminal_reason="inbound:unconfigured",
        outcome="rejected",
    )
    db_session.refresh(cs)
    assert cs.status == "rejected"
    call_lifecycle.transition_call_session(
        db_session, call_sid=cs.call_sid, new_status=call_lifecycle.STATUS_CONNECTED
    )
    db_session.refresh(cs)
    assert cs.status == "rejected"


def test_twilio_status_callback_and_reconcile(db_session, client, monkeypatch) -> None:
    token = "statustoken"
    monkeypatch.setattr(settings, "twilio_auth_token", token)
    monkeypatch.setattr(settings, "public_base_url", "http://localhost:8000")

    user = User(
        username="statususer",
        email="status@example.com",
        password=hash_password("password123"),
        twilio_account_sid="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        twilio_auth_token=token,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    cs = CallSession.create(
        call_sid="CAstatus000000000000000000000001",
        from_number="+1",
        to_number="+2",
        user_id=user.id,
        session=db_session,
    )
    call_lifecycle.mark_connected(db_session, cs.call_sid)

    params = {
        "AccountSid": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "CallSid": cs.call_sid,
        "CallStatus": "completed",
        "CallDuration": "42",
    }
    url = "http://localhost:8000/api/v1/telephony/twilio/status"
    sig = _sign(token, url, params)
    response = client.post(
        "/api/v1/telephony/twilio/status",
        data=params,
        headers={"X-Twilio-Signature": sig},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    db_session.refresh(cs)
    assert cs.status == "completed"
    assert cs.duration_seconds == 42

    stale = CallSession.create(
        call_sid="CAstatus000000000000000000000002",
        from_number="+1",
        to_number="+2",
        user_id=user.id,
        session=db_session,
    )
    stale.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    result = call_lifecycle.reconcile_expired_calls(db_session)
    assert result["marked"] >= 1
    db_session.refresh(stale)
    assert stale.status == "expired"


def test_transcript_bound(db_session) -> None:
    user = User(
        username="truncuser",
        email="trunc@example.com",
        password=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    cs = CallSession.create(
        call_sid="CAtrunc0000000000000000000000001",
        from_number="+1",
        to_number="+2",
        user_id=user.id,
        session=db_session,
    )
    huge = "x" * 40_000
    call_lifecycle.finalize_voice_session(
        db_session,
        call_sid=cs.call_sid,
        status=call_lifecycle.STATUS_COMPLETED,
        terminal_reason="test",
        transcript=huge,
        outcome="completed",
    )
    db_session.refresh(cs)
    assert cs.transcript is not None
    assert len(cs.transcript) < 40_000
    assert cs.transcript.endswith("…[truncated]")


# --- P2-02 reconnect classification ---


def test_classify_deepgram_auth_vs_transient() -> None:
    assert (
        deepgram_mod.classify_deepgram_error(deepgram_mod.DeepgramAuthError("no key"))
        is deepgram_mod.DeepgramAuthError
    )
    assert (
        deepgram_mod.classify_deepgram_error(RuntimeError("401 unauthorized"))
        is deepgram_mod.DeepgramAuthError
    )
    assert (
        deepgram_mod.classify_deepgram_error(TimeoutError("timed out"))
        is deepgram_mod.DeepgramTransientError
    )
    assert deepgram_mod.is_retryable_disconnect(TimeoutError("x")) is True
    assert deepgram_mod.is_retryable_disconnect(deepgram_mod.DeepgramAuthError("x")) is False


def test_sts_connect_requires_global_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "deepgram_api_key", None)
    with pytest.raises(deepgram_mod.DeepgramAuthError):
        deepgram_mod.sts_connect()


def test_voice_session_reconnect_exhaustion(monkeypatch) -> None:
    monkeypatch.setattr(settings, "deepgram_reconnect_max_attempts", 1)
    monkeypatch.setattr(settings, "deepgram_reconnect_backoff_seconds", 0.01)
    monkeypatch.setattr(settings, "deepgram_reconnect_deadline_seconds", 5.0)

    async def _run() -> None:
        twilio_ws = MagicMock()
        twilio_ws.send_text = AsyncMock()
        ctx = CallContext("CAreconnect1", 1, "UTC", "primary")
        sess = VoiceSession(twilio_ws, call_context=ctx)
        sess._context_ready.set()

        async def _fail_once(*_a, **_k):
            raise deepgram_mod.DeepgramTransientError("boom")

        async def _idle_twilio():
            await asyncio.sleep(30)

        with (
            patch.object(sess, "_run_deepgram_once", side_effect=_fail_once),
            patch.object(sess, "_persist_terminal") as persist,
            patch.object(sess, "_twilio_receiver", _idle_twilio),
            patch(
                "app.voice.session.load_voice_config",
                return_value={"type": "Settings"},
            ),
        ):
            await sess.run()
            persist.assert_called()
            assert sess._terminal_reason == "deepgram:reconnect_exhausted"
            assert sess._terminal_status == call_lifecycle.STATUS_PROVIDER_ERROR

    asyncio.run(_run())


def test_voice_session_auth_fails_fast(monkeypatch) -> None:
    monkeypatch.setattr(settings, "deepgram_reconnect_max_attempts", 3)

    async def _run() -> None:
        twilio_ws = MagicMock()
        twilio_ws.send_text = AsyncMock()
        ctx = CallContext("CAauthfail1", 1, "UTC", "primary")
        sess = VoiceSession(twilio_ws, call_context=ctx)
        sess._context_ready.set()

        async def _auth(*_a, **_k):
            raise deepgram_mod.DeepgramAuthError("bad key")

        async def _idle_twilio():
            await asyncio.sleep(30)

        with (
            patch.object(sess, "_run_deepgram_once", side_effect=_auth),
            patch.object(sess, "_persist_terminal") as persist,
            patch.object(sess, "_twilio_receiver", _idle_twilio),
            patch(
                "app.voice.session.load_voice_config",
                return_value={"type": "Settings"},
            ),
        ):
            await sess.run()
            assert sess._terminal_reason == "deepgram:auth"
            persist.assert_called_once()

    asyncio.run(_run())


# --- P2-03 pipeline contract ---


def test_voice_pipeline_only_deepgram_agent() -> None:
    from cryptography.fernet import Fernet

    ok = Settings.__new__(Settings)
    ok.voice_pipeline = "deepgram_agent"
    ok.secret_key = "x" * 32
    ok.fernet_key = Fernet.generate_key().decode()
    ok.database_url = "postgresql://x"
    ok.require_runtime_secrets()

    bad = Settings.__new__(Settings)
    bad.voice_pipeline = "hybrid"
    bad.secret_key = "x" * 32
    bad.fernet_key = ok.fernet_key
    bad.database_url = "postgresql://x"
    with pytest.raises(RuntimeError, match="Unsupported VOICE_PIPELINE"):
        bad.require_runtime_secrets()


# --- P2-05 credentials ---


def test_settings_ignore_tenant_deepgram_key(db_session, monkeypatch) -> None:
    from app.users import service as users_service

    monkeypatch.setattr(settings, "deepgram_api_key", "global-key")
    user = User(
        username="dguser",
        email="dg@example.com",
        password=hash_password("password123"),
        deepgram_api_key="tenant-old",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    payload = users_service.get_settings(user)
    assert payload["has_deepgram"] is True
    assert payload["deepgram_api_key"] is None

    users_service.update_settings(db_session, user, {"deepgram_api_key": "tenant-new"})
    db_session.refresh(user)
    assert user.deepgram_api_key == "tenant-old"


# --- P2-06 media metrics ---


def test_sequence_gaps_and_queue_drops() -> None:
    async def _run() -> None:
        twilio_ws = MagicMock()
        frame = bytes(160)
        payload = base64.b64encode(frame).decode("ascii")

        def media(seq: int) -> str:
            return json.dumps(
                {
                    "event": "media",
                    "sequenceNumber": str(seq),
                    "media": {
                        "track": "inbound",
                        "payload": payload,
                        "chunk": str(seq),
                    },
                }
            )

        messages = [
            media(1),
            media(2),
            media(4),  # gap of 1 (missing 3)
            media(4),  # duplicate
            media(3),  # out of order
            json.dumps({"event": "stop"}),
        ]

        async def _recv():
            if not messages:
                raise RuntimeError("closed")
            return messages.pop(0)

        twilio_ws.receive_text = AsyncMock(side_effect=_recv)
        sess = VoiceSession(twilio_ws)
        sess.audio_queue = asyncio.Queue(maxsize=2)
        sess._context_ready.set()
        await sess._twilio_receiver()
        metrics = sess.media_metrics()
        assert metrics["seq_gaps"] >= 1
        assert metrics["seq_duplicates"] >= 1
        assert metrics["seq_out_of_order"] >= 1
        assert metrics["queue_drops"] >= 1
        assert metrics["queue_high_watermark"] >= 1

    asyncio.run(_run())
