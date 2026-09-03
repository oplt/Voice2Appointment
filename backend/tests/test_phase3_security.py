"""PHASE 3 security hardening tests (tasks.txt)."""

from __future__ import annotations

from sqlalchemy import text

from app.core.config import Settings, settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.redirects import safe_next_path
from app.core.security import hash_password
from app.db.models import GoogleCalendarAuth, User


def test_require_runtime_secrets_rejects_empty() -> None:
    s = Settings(
        secret_key="",
        database_url="",
        fernet_key="",
    )
    try:
        s.require_runtime_secrets()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        msg = str(exc)
        assert "SECRET_KEY" in msg
        assert "FERNET_KEY" in msg
        assert "DATABASE_URL" in msg


def test_safe_next_path_blocks_open_redirects() -> None:
    assert safe_next_path("/dashboard") == "/dashboard"
    assert safe_next_path("/settings?tab=twilio") == "/settings?tab=twilio"
    assert safe_next_path("//evil.com") == "/dashboard"
    assert safe_next_path("https://evil.com") == "/dashboard"
    assert safe_next_path("/\\evil.com") == "/dashboard"
    assert safe_next_path(None) == "/dashboard"


def test_encrypt_decrypt_roundtrip(monkeypatch) -> None:
    from cryptography.fernet import Fernet

    from app.core.config import settings

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "fernet_key", key)
    cipher = encrypt_secret("twilio-secret")
    assert cipher is not None
    assert cipher.startswith("enc:")
    assert decrypt_secret(cipher) == "twilio-secret"
    assert decrypt_secret("legacy-plaintext") == "legacy-plaintext"


def test_provider_secrets_encrypted_at_rest(db_session) -> None:
    user = User(
        username="secuser",
        email="sec@example.com",
        password=hash_password("password123"),
        twilio_auth_token="twilio-plain-token",
        deepgram_api_key="deepgram-plain-key",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    raw = db_session.execute(
        text("SELECT twilio_auth_token, deepgram_api_key FROM res_user WHERE id = :id"),
        {"id": user.id},
    ).one()
    assert raw[0].startswith("enc:")
    assert raw[1].startswith("enc:")
    assert user.twilio_auth_token == "twilio-plain-token"
    assert user.deepgram_api_key == "deepgram-plain-key"

    auth = GoogleCalendarAuth(
        user_id=user.id,
        credentials_json='{"client_id":"x"}',
        token_json='{"access_token":"y"}',
    )
    db_session.add(auth)
    db_session.commit()
    raw_g = db_session.execute(
        text(
            "SELECT credentials_json, token_json FROM google_calendar_auth WHERE id = :id"
        ),
        {"id": auth.id},
    ).one()
    assert raw_g[0].startswith("enc:")
    assert raw_g[1].startswith("enc:")


def test_security_headers_present(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "Content-Security-Policy" in response.headers


def test_csrf_rejects_mutating_without_token(raw_client) -> None:
    response = raw_client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "password123"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF validation failed"


def test_csrf_allows_matching_header(client) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "wrong"},
    )
    # CSRF ok; credentials wrong
    assert response.status_code == 401


def test_access_cookie_flags(client) -> None:
    client.post(
        "/api/v1/auth/register",
        json={
            "username": "cookietest",
            "email": "cookie@example.com",
            "password": "password123",
        },
    )
    set_cookie = client.cookies.get("access_token")
    assert set_cookie
    # Inspect Set-Cookie from last register via raw jar is hard; hit logout/login.
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "cookie@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    # Starlette TestClient stores cookie; header flags checked on response
    header = login.headers.get("set-cookie", "")
    assert "HttpOnly" in header or "httponly" in header.lower()
    assert "SameSite=lax" in header or "samesite=lax" in header.lower()


def test_login_rate_limit(client) -> None:
    for _ in range(10):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "rate@example.com", "password": "wrong"},
        )
        assert response.status_code in {401, 429}
    limited = client.post(
        "/api/v1/auth/login",
        json={"email": "rate@example.com", "password": "wrong"},
    )
    assert limited.status_code == 429


def test_twilio_webhook_csrf_exempt(client, monkeypatch) -> None:
    # Webhooks stay CSRF-exempt; Twilio signature is enforced separately (403 if missing).
    monkeypatch.setattr(settings, "twilio_auth_token", "tok")
    response = client.post(
        "/api/v1/telephony/twilio/recording",
        data={
            "AccountSid": "ACunknown",
            "CallSid": "CAabc",
            "RecordingSid": "RExyz",
            "RecordingUrl": "https://api.twilio.com/rec",
        },
    )
    # Missing Twilio signature → 403 Forbidden (not CSRF cookie failure message)
    assert response.status_code == 403
    assert response.json()["detail"] == "Forbidden"
