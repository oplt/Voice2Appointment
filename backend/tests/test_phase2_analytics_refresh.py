"""Phase 2.2 — Twilio analytics refresh is queued and coalesced."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.analytics import router as analytics_router
from app.db.models import User


class _Task:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def delay(self, user_id: int) -> None:
        self.calls.append(user_id)


def _user() -> User:
    now = datetime.now(timezone.utc)
    user = User(id=7, username="u", email="u@example.test", password="x")
    user.twilio_last_synced_at = now - timedelta(minutes=5)
    user.twilio_sync_lease_token = None
    user.twilio_sync_lease_expires_at = None
    user.config_json = "{}"
    return user


def test_sync_status_reports_syncing_when_lease_active() -> None:
    user = _user()
    user.twilio_sync_lease_token = "lease"
    user.twilio_sync_lease_expires_at = datetime.now(timezone.utc) + timedelta(minutes=1)
    payload = analytics_router._twilio_sync_status_for_user(user)
    assert payload["status"] == "syncing"


def test_fetch_twilio_returns_202_and_enqueues(monkeypatch) -> None:
    task = _Task()
    monkeypatch.setattr(analytics_router, "_claim_sync_chain", lambda _uid: True)
    monkeypatch.setattr(analytics_router, "_is_sync_queued", lambda _uid: True)
    async def _inline(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(analytics_router, "to_thread_db", _inline)
    monkeypatch.setattr(analytics_router, "_enqueue_twilio_sync", task.delay)

    user = _user()
    user.twilio_account_sid = "AC123"
    user.twilio_auth_token = "token"

    response = asyncio.run(analytics_router.fetch_twilio(current_user=user))
    assert response.status_code == 202
    assert task.calls == [user.id]


def test_fetch_twilio_coalesces_duplicate_requests(monkeypatch) -> None:
    task = _Task()
    monkeypatch.setattr(analytics_router, "_claim_sync_chain", lambda _uid: False)
    monkeypatch.setattr(analytics_router, "_is_sync_queued", lambda _uid: True)
    async def _inline(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(analytics_router, "to_thread_db", _inline)
    monkeypatch.setattr(analytics_router, "_enqueue_twilio_sync", task.delay)

    user = _user()
    user.twilio_account_sid = "AC123"
    user.twilio_auth_token = "token"

    response = asyncio.run(analytics_router.fetch_twilio(current_user=user))
    assert response.status_code == 202
    assert task.calls == []
