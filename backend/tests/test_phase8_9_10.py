"""PHASE 8–10: Deepgram config, calendar cache/busy, Twilio analytics."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.analytics import service as analytics_service
from app.calendars.tools import generate_alternative_slots
from app.core.config import settings
from app.core.security import hash_password
from app.db.models import TwilioCall, TwilioCallAnalytics, User
from app.voice.providers.deepgram import DeepgramSettings, get_deepgram_settings
from app.voice.session import load_default_config_template


def test_deepgram_settings_eu_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(settings, "deepgram_region", "eu")
    monkeypatch.setattr(settings, "deepgram_agent_url", "")
    monkeypatch.setattr(settings, "deepgram_model", "nova-3")
    monkeypatch.setattr(settings, "deepgram_language", "en")
    monkeypatch.setattr(settings, "deepgram_api_key", "dg-test")
    dg = get_deepgram_settings()
    assert isinstance(dg, DeepgramSettings)
    assert dg.region == "eu"
    assert "eu.deepgram.com" in dg.endpoint
    assert dg.model == "nova-3"


def test_deepgram_settings_global_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(settings, "deepgram_region", "global")
    monkeypatch.setattr(settings, "deepgram_agent_url", "")
    monkeypatch.setattr(settings, "deepgram_api_key", "dg-test")
    dg = get_deepgram_settings()
    assert dg.region == "global"
    assert dg.endpoint.startswith("wss://agent.deepgram.com/")


def test_wait_for_message_type_handshake() -> None:
    async def _run() -> None:
        class FakeWs:
            def __init__(self):
                self._msgs = [
                    json.dumps({"type": "Other"}),
                    json.dumps({"type": "Welcome"}),
                ]

            def __aiter__(self):
                return self

            async def __anext__(self):
                if not self._msgs:
                    raise StopAsyncIteration
                return self._msgs.pop(0)

        from app.voice.providers.deepgram import wait_for_message_type

        msg = await wait_for_message_type(FakeWs(), "Welcome", timeout=2)
        assert msg["type"] == "Welcome"

    asyncio.run(_run())


def test_alternative_slots_uses_single_freebusy() -> None:
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
    # +1h candidate overlaps busy block and must be skipped
    starts = {a["start"] for a in alts}
    assert (start + timedelta(hours=1)).isoformat() not in starts


def test_twilio_call_is_tenant_scoped(db_session) -> None:
    user = User(
        username="twuser",
        email="tw@example.com",
        password=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    row = TwilioCall(
        user_id=user.id,
        sid="CAtest1",
        from_number="+10000000001",
        to_number="+10000000002",
        start_time=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
        duration_sec=60,
        price=Decimal("0.0100"),
        price_unit="USD",
        direction="inbound",
    )
    db_session.add(row)
    db_session.commit()

    summary = analytics_service.analytics_summary(db_session, user.id)
    assert summary["total_calls"] == 1

    other = analytics_service.analytics_summary(db_session, user.id + 999)
    assert other["total_calls"] == 0


def test_upsert_twilio_calls_idempotent(db_session) -> None:
    user = User(
        username="upuser",
        email="up@example.com",
        password=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    payload = [
        {
            "sid": "CAdup",
            "from": "+111",
            "to": "+222",
            "start_time": "2026-09-01T12:00:00Z",
            "duration_sec": 30,
            "price": 0.02,
            "price_unit": "USD",
            "direction": "inbound",
        }
    ]
    assert analytics_service.upsert_twilio_calls(db_session, user.id, payload) == 1
    payload[0]["duration_sec"] = 45
    assert analytics_service.upsert_twilio_calls(db_session, user.id, payload) == 1
    rows = db_session.query(TwilioCall).filter_by(user_id=user.id, sid="CAdup").all()
    assert len(rows) == 1
    assert rows[0].duration_sec == 45


def test_incremental_sync_advances_cursor(db_session, monkeypatch) -> None:
    user = User(
        username="syncuser",
        email="sync@example.com",
        password=hash_password("password123"),
        twilio_account_sid="ACxxx",
        twilio_auth_token="token",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    class FakeProvider:
        def __init__(self, **kwargs):
            pass

        def fetch_calls(self, limit=100, *, start_time_after=None, page_size=None, max_pages=None):
            return [
                {
                    "sid": "CAnew",
                    "from": "+1",
                    "to": "+2",
                    "start_time": "2026-09-02T15:00:00+00:00",
                    "duration_sec": 10,
                    "price": 0.01,
                    "price_unit": "USD",
                    "direction": "inbound",
                    "status": "completed",
                }
            ]

        def fetch_calls_by_sids(self, sids):
            return []

    monkeypatch.setattr(
        "app.analytics.service.TwilioProvider", FakeProvider
    )
    analytics_service.fetch_and_store_twilio(
        db_session,
        user_id=user.id,
        account_sid="ACxxx",
        auth_token="token",
    )
    db_session.refresh(user)
    assert user.twilio_last_synced_at is not None
    assert user.twilio_last_synced_at.year == 2026

    analytics = (
        db_session.query(TwilioCallAnalytics)
        .filter_by(user_id=user.id, date=date.today())
        .one()
    )
    assert isinstance(analytics.call_data, dict)
    assert analytics.call_data.get("calls")


def test_celery_beat_has_twilio_sync() -> None:
    from app.workers.celery_app import celery_app

    assert "sync-all-twilio-analytics" in celery_app.conf.beat_schedule
    assert celery_app.conf.beat_schedule["sync-all-twilio-analytics"]["task"] == (
        "sync_all_twilio_analytics"
    )


def test_appointment_create_invalidates_calendar_cache(db_session) -> None:
    from app.appointments import service as appointments_service
    from app.core import cache as cache_mod

    user = User(
        username="cacheuser",
        email="cache@example.com",
        password=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    with patch.object(cache_mod, "invalidate_user_calendar_caches") as inv:
        appointments_service.create_appointment(
            db_session,
            user.id,
            summary="Meet",
            start_datetime=datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc),
            end_datetime=datetime(2026, 9, 20, 11, 0, tzinfo=timezone.utc),
            timezone="UTC",
        )
        inv.assert_called_once_with(user.id)
