"""PHASE 1 performance / DB / cache tests."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.analytics import service as analytics_service
from app.core.config import settings
from app.core.security import hash_password
from app.dashboard.service import dashboard_summary
from app.db.models import Appointment, CallSession, TwilioCall, User
from app.telephony.phones import canonical_e164
from app.telephony.service import find_user_by_twilio_phone


def test_canonical_e164_variants() -> None:
    assert canonical_e164("+32 470 12 34 56") == "+32470123456"
    assert canonical_e164("+1 (925) 396-5839") == "+19253965839"
    assert canonical_e164("not-a-phone") is None


def test_phone_lookup_uses_e164_index(db_session) -> None:
    user = User(
        username="e164u",
        email="e164u@example.com",
        password=hash_password("password123"),
        twilio_phone_number="+32 470 12 34 56",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    assert user.twilio_phone_e164 == "+32470123456"
    found = find_user_by_twilio_phone(db_session, "+32470123456")
    assert found is not None and found.id == user.id


def test_bulk_upsert_twilio_calls(db_session) -> None:
    user = User(
        username="bulk",
        email="bulk@example.com",
        password=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    payload = [
        {
            "sid": f"CA{i:032d}",
            "from": "+1",
            "to": "+2",
            "start_time": f"2026-09-01T{i:02d}:00:00Z",
            "duration_sec": i,
            "price": 0.01,
            "price_unit": "USD",
            "status": "completed",
        }
        for i in range(5)
    ]
    assert analytics_service.upsert_twilio_calls(db_session, user.id, payload) == 5
    payload[0]["duration_sec"] = 99
    assert analytics_service.upsert_twilio_calls(db_session, user.id, payload) == 5
    row = db_session.query(TwilioCall).filter_by(user_id=user.id, sid="CA00000000000000000000000000000000").one()
    assert row.duration_sec == 99


def test_sync_pagination_and_nonterminal_refresh(db_session, monkeypatch) -> None:
    user = User(
        username="page",
        email="page@example.com",
        password=hash_password("password123"),
        twilio_account_sid="ACxxx",
        twilio_auth_token="tok",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    db_session.add(
        TwilioCall(
            user_id=user.id,
            sid="CAinprog",
            start_time=datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc),
            status="in-progress",
        )
    )
    db_session.commit()

    class FakeProvider:
        def __init__(self, **kwargs):
            pass

        def fetch_calls(self, limit=100, *, start_time_after=None, page_size=None, max_pages=None):
            return [
                {
                    "sid": f"CApage{i}",
                    "from": "+1",
                    "to": "+2",
                    "start_time": f"2026-09-02T{i:02d}:00:00+00:00",
                    "duration_sec": 10,
                    "price": 0.01,
                    "price_unit": "USD",
                    "status": "completed",
                }
                for i in range(3)
            ]

        def fetch_calls_by_sids(self, sids):
            assert "CAinprog" in list(sids)
            return [
                {
                    "sid": "CAinprog",
                    "from": "+1",
                    "to": "+2",
                    "start_time": "2026-09-01T10:00:00+00:00",
                    "duration_sec": 42,
                    "price": 0.02,
                    "price_unit": "USD",
                    "status": "completed",
                }
            ]

    monkeypatch.setattr("app.analytics.service.TwilioProvider", FakeProvider)
    result = analytics_service.fetch_and_store_twilio(
        db_session, user_id=user.id, account_sid="ACxxx", auth_token="tok"
    )
    assert result["synced"] >= 3
    refreshed = db_session.query(TwilioCall).filter_by(sid="CAinprog").one()
    assert refreshed.status == "completed"
    assert refreshed.duration_sec == 42


def test_analytics_mixed_currency(db_session) -> None:
    user = User(
        username="cur",
        email="cur@example.com",
        password=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    for sid, unit, price in [
        ("CAu1", "USD", "0.10"),
        ("CAe1", "EUR", "0.20"),
    ]:
        db_session.add(
            TwilioCall(
                user_id=user.id,
                sid=sid,
                start_time=datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
                duration_sec=60,
                price=Decimal(price),
                price_unit=unit,
                status="completed",
            )
        )
    db_session.commit()
    summary = analytics_service.analytics_summary(
        db_session, user.id, start=date(2026, 9, 1), end=date(2026, 9, 3)
    )
    assert summary["total_calls"] == 2
    assert summary["total_cost"] is None
    assert "USD" in summary["totals_by_currency"]
    assert "EUR" in summary["totals_by_currency"]


def test_dashboard_excludes_cancelled_local_day(db_session) -> None:
    user = User(
        username="dash",
        email="dash@example.com",
        password=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            Appointment(
                user_id=user.id,
                summary="live",
                start_datetime=now + timedelta(hours=1),
                end_datetime=now + timedelta(hours=2),
                timezone="UTC",
                status="confirmed",
            ),
            Appointment(
                user_id=user.id,
                summary="gone",
                start_datetime=now + timedelta(hours=3),
                end_datetime=now + timedelta(hours=4),
                timezone="UTC",
                status="cancelled",
            ),
        ]
    )
    db_session.commit()
    summary = dashboard_summary(db_session, user.id)
    assert summary["appointments_today"] >= 1
    assert all(u["summary"] != "gone" for u in summary["upcoming"])


def test_appointment_cursor_pagination(db_session) -> None:
    from app.appointments import service as appt

    user = User(
        username="pagea",
        email="pagea@example.com",
        password=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    base = datetime.now(timezone.utc) + timedelta(days=1)
    for i in range(5):
        db_session.add(
            Appointment(
                user_id=user.id,
                summary=f"A{i}",
                start_datetime=base + timedelta(hours=i),
                end_datetime=base + timedelta(hours=i, minutes=30),
                timezone="UTC",
                status="confirmed",
            )
        )
    db_session.commit()
    page1, cursor = appt.list_appointments_page(
        db_session, user.id, scope="upcoming", limit=2
    )
    assert len(page1) == 2
    assert cursor
    page2, cursor2 = appt.list_appointments_page(
        db_session, user.id, scope="upcoming", limit=2, cursor=cursor
    )
    assert len(page2) == 2
    assert {a.id for a in page1}.isdisjoint({a.id for a in page2})


def test_redis_client_resets_on_timeout() -> None:
    import app.core.cache as cache_mod

    mock_client = MagicMock()
    mock_client.get.side_effect = TimeoutError("stalled")
    cache_mod._client = mock_client
    cache_mod._retry_after = 0
    assert cache_mod.cache_get("k") is None
    assert cache_mod._client is None
    counts = cache_mod.cache_failure_counts()
    assert counts["failures"] >= 1


def test_versioned_key_includes_user_and_version(monkeypatch) -> None:
    from app.core import cache as cache_mod

    monkeypatch.setattr(cache_mod, "cache_version", lambda user_id, ns: 7)
    key = cache_mod.versioned_key(42, "analytics", "2026-01-01", "2026-01-31", "UTC")
    assert key.startswith("analytics:v7:42:")
    assert "42" in key
