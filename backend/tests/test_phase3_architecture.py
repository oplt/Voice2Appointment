"""Phase 3: SoT booking, OAuth/settings, errors, rate-limit, reset, prod config."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from app.auth.service import hash_password
from app.core.config import Settings, settings
from app.core.errors import map_exception, voice_error_payload
from app.core.rate_limit import client_ip
from app.core.security import (
    create_access_token,
    create_oauth_state,
    hash_token,
    mint_password_reset_token,
    verify_oauth_state,
)
from app.db.models import Appointment, CallSession, User
from app.appointments import booking as booking_service


def test_alembic_head_phase3() -> None:
    from pathlib import Path
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = Path(__file__).resolve().parents[1] / "migrations"
    cfg = Config()
    cfg.set_main_option("script_location", str(root))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert heads == ["c9d0e1f2a3b4"]


def test_production_rejects_insecure_cookies() -> None:
    s = Settings.__new__(Settings)
    s.app_env = "production"
    s.secret_key = "x" * 32
    s.fernet_key = Fernet.generate_key().decode()
    s.database_url = "postgresql://x"
    s.voice_pipeline = "deepgram_agent"
    s.cookie_secure = False
    s.cookie_samesite = "lax"
    s.public_base_url = "https://example.com"
    s.cors_origins = ["https://example.com"]
    with pytest.raises(RuntimeError, match="COOKIE_SECURE"):
        s.require_runtime_secrets()


def test_client_ip_ignores_spoofed_xff() -> None:
    req = MagicMock()
    req.client.host = "203.0.113.10"
    req.headers = {"x-forwarded-for": "1.2.3.4"}
    # Not a trusted proxy → use direct peer
    assert client_ip(req) == "203.0.113.10"


def test_client_ip_honors_xff_from_trusted_proxy(monkeypatch) -> None:
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "10.0.0.0/8")
    req = MagicMock()
    req.client.host = "10.0.0.5"
    req.headers = {"x-forwarded-for": "198.51.100.7, 10.0.0.5"}
    assert client_ip(req) == "198.51.100.7"


def test_map_exception_hides_vendor_text() -> None:
    class HttpError(Exception):
        pass

    exc = HttpError("https://oauth2.googleapis.com/token secret=abc 401")
    mapped = map_exception(exc)
    payload = voice_error_payload(exc)
    assert "googleapis" not in payload["error"].lower()
    assert "secret" not in payload["error"].lower()
    assert mapped.code in {"provider_auth", "provider_unavailable", "internal_error"}


def test_oauth_state_roundtrip() -> None:
    state = create_oauth_state(user_id=42, code_verifier="verifier-xyz")
    out = verify_oauth_state(state)
    assert out == (42, "verifier-xyz")
    assert verify_oauth_state("tampered") is None


def test_booking_cancel_soft(db_session) -> None:
    user = User(
        username="cancelu",
        email="cancelu@example.com",
        password=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    start = datetime.now(timezone.utc) + timedelta(days=2)
    end = start + timedelta(minutes=30)
    row = booking_service.book_appointment(
        db_session,
        user.id,
        summary="Cancel me",
        start_datetime=start,
        end_datetime=end,
        timezone_name="UTC",
    )
    cancelled = booking_service.cancel_appointment(
        db_session, user.id, appointment_id=row.id, reason="client request"
    )
    assert cancelled.status == "cancelled"
    assert "client request" in (cancelled.notes or "")


def test_patch_clears_nullable_and_rejects_bad_status(client, db_session) -> None:
    user = User(
        username="patchu",
        email="patchu@example.com",
        password=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(subject=str(user.id), auth_version=0)
    client.cookies.set("access_token", token)

    start = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat().replace("+00:00", "Z")
    end = (datetime.now(timezone.utc) + timedelta(days=3, minutes=30)).isoformat().replace("+00:00", "Z")
    created = client.post(
        "/api/v1/appointments",
        json={
            "summary": "Patch me",
            "start_datetime": start,
            "end_datetime": end,
            "timezone": "UTC",
            "notes": "keep",
            "client_name": "Ada",
        },
    )
    assert created.status_code == 201, created.text
    appt_id = created.json()["id"]

    cleared = client.patch(
        f"/api/v1/appointments/{appt_id}",
        json={"client_name": None, "notes": None},
    )
    assert cleared.status_code == 200, cleared.text
    body = cleared.json()
    assert body["client_name"] is None
    assert body["notes"] is None

    bad = client.patch(
        f"/api/v1/appointments/{appt_id}",
        json={"status": "confirmed"},
    )
    # pending -> confirmed allowed
    assert bad.status_code == 200

    illegal = client.patch(
        f"/api/v1/appointments/{appt_id}",
        json={"status": "pending"},
    )
    assert illegal.status_code == 422


def test_booking_policy_roundtrip(client, db_session) -> None:
    user = User(
        username="policyu",
        email="policyu@example.com",
        password=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(subject=str(user.id), auth_version=0)
    client.cookies.set("access_token", token)

    payload = {
        "default_service_duration_minutes": 45,
        "service_durations_minutes": {"Consult": 45},
        "buffer_before_minutes": 5,
        "buffer_after_minutes": 5,
        "business_hours": {
            "monday": [{"start": "09:00", "end": "17:00"}],
        },
    }
    put = client.put("/api/v1/users/me/booking-policy", json=payload)
    assert put.status_code == 200, put.text
    got = client.get("/api/v1/users/me/booking-policy")
    assert got.status_code == 200
    assert got.json()["default_service_duration_minutes"] == 45
    assert got.json()["service_durations_minutes"]["Consult"] == 45


def test_password_reset_revokes_sessions(client, db_session) -> None:
    user = User(
        username="revokeme",
        email="revokeme@example.com",
        password=hash_password("oldpassword"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    old_token = create_access_token(subject=str(user.id), auth_version=0)
    client.cookies.set("access_token", old_token)
    assert client.get("/api/v1/auth/me").status_code == 200

    reset_token = mint_password_reset_token(db_session, user)
    ok = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": reset_token, "password": "brandnewpass1"},
    )
    assert ok.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_compose_migrate_once() -> None:
    from pathlib import Path

    text = Path(__file__).resolve().parents[2].joinpath("compose.yaml").read_text()
    assert "migrate:" in text
    assert "RUN_DB_MIGRATE" in text or "MIGRATE_ONLY" in Path(
        __file__
    ).resolve().parents[2].joinpath("docker/entrypoint.backend.sh").read_text()
    assert "service_completed_successfully" in text
    entry = Path(__file__).resolve().parents[2].joinpath("docker/entrypoint.backend.sh").read_text()
    assert "RUN_DB_MIGRATE" in entry
    assert entry.count("alembic upgrade head") == 1


def test_google_authenticate_no_local_server() -> None:
    from pathlib import Path as P

    text = P(__file__).resolve().parents[1].joinpath(
        "app/calendars/providers/google.py"
    ).read_text()
    assert "InstalledAppFlow" not in text
    assert "run_local_server" not in text
    assert "build_authorization_url" in text
