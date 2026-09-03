"""PHASE 12: production runtime — process split, debug, health probes."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.factory import create_app


def test_production_disables_debug(monkeypatch) -> None:
    monkeypatch.setenv("DEBUG", "true")
    cfg = Settings(app_env="production")
    assert cfg.is_production is True
    assert cfg.debug is False


def test_development_honors_debug(monkeypatch) -> None:
    monkeypatch.setenv("DEBUG", "true")
    cfg = Settings(app_env="development")
    assert cfg.is_production is False
    assert cfg.debug is True


def test_web_app_excludes_voice_websocket() -> None:
    web = create_app(include_api=True, include_voice=False)
    paths = {getattr(r, "path", None) for r in web.routes}
    assert "/ws/voice" not in paths
    assert any(str(p).startswith("/api/v1/") for p in paths if p)
    assert "/health/live" in paths
    assert "/health/ready" in paths


def test_voice_app_excludes_http_api() -> None:
    voice = create_app(include_api=False, include_voice=True)
    paths = {getattr(r, "path", None) for r in voice.routes}
    assert "/ws/voice" in paths
    assert "/api/v1/auth/login" not in paths
    assert "/health/live" in paths


def test_health_live_and_ready(client, monkeypatch) -> None:
    live = client.get("/health/live")
    assert live.status_code == 200
    assert live.json() == {"status": "ok"}

    with (
        patch("app.health.router.check_database", return_value=(True, "ok")),
        patch("app.health.router.check_redis", return_value=(True, "ok")),
    ):
        ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert ready.json()["checks"]["database"] == "ok"
    assert ready.json()["checks"]["redis"] == "ok"

    with (
        patch("app.health.router.check_database", return_value=(True, "ok")),
        patch("app.health.router.check_redis", return_value=(False, "error:Timeout")),
    ):
        not_ready = client.get("/health/ready")
    assert not_ready.status_code == 503
    assert not_ready.json()["status"] == "not_ready"


def test_asgi_modules_import() -> None:
    import asgi
    import voice_asgi

    assert asgi.app.title.startswith("Voice2Appointment")
    assert voice_asgi.app.title.startswith("Voice2Appointment")
    web_paths = {getattr(r, "path", None) for r in asgi.app.routes}
    voice_paths = {getattr(r, "path", None) for r in voice_asgi.app.routes}
    assert "/ws/voice" not in web_paths
    assert "/ws/voice" in voice_paths


def test_ready_does_not_call_third_parties() -> None:
    """Readiness must only touch database + Redis (no provider SDKs)."""
    import ast
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "app" / "health" / "router.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "twilio" not in imported
    assert "google" not in imported
    assert "websockets" not in imported


def test_voice_health_with_testclient(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.factory.settings.require_runtime_secrets", lambda: None
    )
    voice = create_app(include_api=False, include_voice=True)
    with TestClient(voice) as tc:
        assert tc.get("/health/live").status_code == 200
        assert tc.get("/health").json() == {"status": "ok"}
