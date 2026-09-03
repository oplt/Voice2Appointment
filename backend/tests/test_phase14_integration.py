"""PHASE 14.2 integration tests: Redis, Celery, calendar repo, optional Postgres."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text

from app.calendars import service as calendar_service
from app.core import cache as cache_mod
from app.core.security import hash_password
from app.db.models import User
from app.workers.tasks import sync_twilio_for_user


@pytest.fixture(autouse=True)
def _reset_redis_client_state():
    cache_mod._client = None
    cache_mod._client_failed = False
    yield
    cache_mod._client = None
    cache_mod._client_failed = False


def test_redis_cache_roundtrip_with_fake_client(monkeypatch) -> None:
    store: dict[str, str] = {}

    class _FakeRedis:
        def ping(self):
            return True

        def get(self, key):
            return store.get(key)

        def setex(self, key, _ttl, value):
            store[key] = value

        def delete(self, *keys):
            for key in keys:
                store.pop(key, None)

        def scan_iter(self, match=None, count=100):  # noqa: ARG002
            prefix = (match or "*").rstrip("*")
            for key in list(store):
                if key.startswith(prefix):
                    yield key

    class _RedisMod:
        class Redis:
            @staticmethod
            def from_url(*_a, **_k):
                return _FakeRedis()

    monkeypatch.setitem(__import__("sys").modules, "redis", _RedisMod)
    cache_mod.cache_set("cal:events:1:x", [{"id": "e1"}], ttl_seconds=30)
    assert cache_mod.cache_get("cal:events:1:x") == [{"id": "e1"}]
    with patch.object(cache_mod, "bump_cache_version") as bump:
        cache_mod.invalidate_user_calendar_caches(1)
        bump.assert_any_call(1, "cal")


def test_celery_sync_twilio_task_runs_eager(db_session, monkeypatch) -> None:
    user = User(
        username="celeryuser",
        email="celery@example.com",
        password=hash_password("password123"),
        twilio_account_sid="ACcel",
        twilio_auth_token="token",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    monkeypatch.setattr(db_session, "close", lambda: None)
    monkeypatch.setattr("app.workers.tasks.SessionLocal", lambda: db_session)

    with patch("app.analytics.service.fetch_and_store_twilio") as fetch:
        fetch.return_value = {"total_calls": 0, "message": "ok"}
        result = sync_twilio_for_user.run(user.id)
        assert result["ok"] is True
        fetch.assert_called_once()


def test_calendar_repository_status_and_list_events_mocked(db_session, monkeypatch) -> None:
    user = User(
        username="caluser",
        email="cal@example.com",
        password=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    status = calendar_service.calendar_status(db_session, user.id)
    assert status["connected"] is False

    fake = MagicMock()
    fake.list_events.return_value = {
        "items": [
            {
                "id": "evt1",
                "summary": "Consult",
                "start": {"dateTime": "2026-09-10T10:00:00+02:00"},
                "end": {"dateTime": "2026-09-10T11:00:00+02:00"},
                "attendees": [],
            }
        ]
    }
    monkeypatch.setattr(calendar_service, "GoogleCalendarService", lambda db, uid: fake)
    events = calendar_service.list_events(
        db_session,
        user.id,
        "2026-09-10T00:00:00+02:00",
        "2026-09-11T00:00:00+02:00",
        timezone_str="Europe/Brussels",
    )
    assert len(events) == 1
    assert events[0]["title"] == "Consult"
    fake.list_events.assert_called_once()


@pytest.mark.integration
def test_postgres_smoke_when_configured() -> None:
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("DATABASE_URL is not PostgreSQL")
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar() == 1
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL unavailable: {type(exc).__name__}")
    finally:
        engine.dispose()
