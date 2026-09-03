"""Smoke tests for FastAPI app wiring and domain APIs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.security import hash_password
from app.db.models import User


def test_health(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_health(client) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_me_requires_auth(client) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_dashboard_summary_requires_auth(client) -> None:
    response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 401


def test_login_without_user(client) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401


def _register(client, *, username: str, email: str, password: str = "password123") -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_appointments_tenant_isolation(client, db_session) -> None:
    _register(client, username="alice", email="alice@example.com")
    from app.main import app
    from fastapi.testclient import TestClient

    alice_login = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "password123"},
    )
    assert alice_login.status_code == 200
    alice_cookies = client.cookies

    bob = User(
        username="bob",
        email="bob@example.com",
        password=hash_password("password123"),
    )
    db_session.add(bob)
    db_session.commit()
    db_session.refresh(bob)

    with TestClient(app) as bob_raw:
        # Reuse the same CSRF-aware wrapper type as the client fixture.
        bob_client = type(client)(bob_raw)
        bob_login = bob_client.post(
            "/api/v1/auth/login",
            json={"email": "bob@example.com", "password": "password123"},
        )
        assert bob_login.status_code == 200

        start = datetime.now(timezone.utc) + timedelta(days=1)
        end = start + timedelta(hours=1)
        create = bob_client.post(
            "/api/v1/appointments",
            json={
                "summary": "Bob private",
                "start_datetime": start.isoformat(),
                "end_datetime": end.isoformat(),
                "timezone": "UTC",
            },
        )
        assert create.status_code == 201, create.text
        bob_appt_id = create.json()["id"]

        bob_list = bob_client.get("/api/v1/appointments")
        assert bob_list.status_code == 200
        bob_items = bob_list.json()["items"]
        assert any(a["id"] == bob_appt_id for a in bob_items)

    client.cookies = alice_cookies
    alice_list = client.get("/api/v1/appointments")
    assert alice_list.status_code == 200
    assert all(a["id"] != bob_appt_id for a in alice_list.json()["items"])

    alice_get = client.get(f"/api/v1/appointments/{bob_appt_id}")
    assert alice_get.status_code == 404


def test_dashboard_summary_authenticated(client) -> None:
    _register(client, username="dana", email="dana@example.com")
    response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 200
    body = response.json()
    assert "appointments_today" in body
    assert "appointments_week" in body
    assert "calendar_connected" in body
    assert "upcoming" in body
    assert "recent_calls" in body
