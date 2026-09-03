"""Phase 4 UX contracts: calls pagination, dashboard fields, tenant isolation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.security import create_access_token, hash_password
from app.dashboard.service import dashboard_summary
from app.db.models import CallSession, User


def _login(client, user_id: int) -> None:
    token = create_access_token(subject=str(user_id), auth_version=0)
    client.cookies.set("access_token", token)


def _user(db_session, *, username: str, email: str) -> User:
    user = User(
        username=username,
        email=email,
        password=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_calls_list_paginates_and_hides_transcript(client, db_session) -> None:
    owner = _user(db_session, username="caller", email="caller@example.com")
    other = _user(db_session, username="other", email="other@example.com")
    now = datetime.now(timezone.utc)

    for i in range(3):
        CallSession.create(
            call_sid=f"CAown{i}",
            from_number="+10000000001",
            to_number="+10000000002",
            user_id=owner.id,
            session=db_session,
        )
    owned = (
        db_session.query(CallSession)
        .filter(CallSession.user_id == owner.id)
        .order_by(CallSession.id.asc())
        .all()
    )
    for idx, row in enumerate(owned):
        row.started_at = now - timedelta(minutes=idx)
        row.transcript = f"secret transcript {idx}"
    CallSession.create(
        call_sid="CAother",
        from_number="+19999999999",
        to_number="+18888888888",
        user_id=other.id,
        session=db_session,
    )
    db_session.commit()

    _login(client, owner.id)
    first = client.get("/api/v1/calls", params={"limit": 2})
    assert first.status_code == 200, first.text
    body = first.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"]
    assert all("transcript" not in item or item.get("transcript") is None for item in body["items"])
    assert all(item["has_transcript"] is True for item in body["items"])
    assert all(item["call_sid"].startswith("CAown") for item in body["items"])

    second = client.get(
        "/api/v1/calls",
        params={"limit": 2, "cursor": body["next_cursor"]},
    )
    assert second.status_code == 200, second.text
    page2 = second.json()
    assert len(page2["items"]) == 1
    assert page2["next_cursor"] is None

    detail = client.get(f"/api/v1/calls/{owned[0].id}")
    assert detail.status_code == 200
    assert detail.json()["transcript"] is None
    assert detail.json()["has_transcript"] is True

    with_tx = client.get(
        f"/api/v1/calls/{owned[0].id}",
        params={"include_transcript": True},
    )
    assert with_tx.status_code == 200
    assert with_tx.json()["transcript"] == "secret transcript 0"

    foreign = client.get(f"/api/v1/calls/{db_session.query(CallSession).filter_by(call_sid='CAother').one().id}")
    assert foreign.status_code == 404


def test_calls_invalid_cursor(client, db_session) -> None:
    user = _user(db_session, username="badcur", email="badcur@example.com")
    _login(client, user.id)
    resp = client.get("/api/v1/calls", params={"cursor": "not-a-cursor"})
    assert resp.status_code in (400, 422)


def test_dashboard_summary_includes_phase4_fields(db_session, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "deepgram_api_key", "dg-test-key")
    user = _user(db_session, username="dash", email="dash@example.com")
    user.twilio_account_sid = "ACdash"
    user.twilio_auth_token = "tok"
    db_session.commit()

    CallSession.create(
        call_sid="CAdash",
        from_number="+1",
        to_number="+2",
        user_id=user.id,
        session=db_session,
    )

    summary = dashboard_summary(db_session, user.id)
    assert isinstance(summary["recent_calls"], int)
    assert summary["recent_calls"] >= 1
    assert "calls_today" in summary["call_statistics"]
    assert summary["provider_status"]["twilio"] is True
    assert summary["provider_status"]["deepgram"] is True
    assert "timezone" in summary
    assert "generated_at" in summary
