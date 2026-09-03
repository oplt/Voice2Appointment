"""Ensure `backend/` is on sys.path when pytest collects tests."""

from __future__ import annotations

import sys
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


@pytest.fixture(autouse=True)
def _test_runtime_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings
    from app.core.rate_limit import limiter

    monkeypatch.setattr(settings, "secret_key", "test-secret-key-at-least-32-chars!!")
    monkeypatch.setattr(settings, "database_url", "sqlite://")
    monkeypatch.setattr(settings, "fernet_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "cookie_secure", False)
    monkeypatch.setattr(settings, "cookie_samesite", "lax")
    monkeypatch.setattr(settings, "public_base_url", "http://localhost:8000")
    limiter._hits.clear()


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.db.base import Base
    import app.db.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def db_session(db_engine) -> Generator[Session, None, None]:
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


class CsrfClient:
    """TestClient wrapper that auto-attaches the double-submit CSRF header."""

    def __init__(self, client: TestClient) -> None:
        self._client = client

    @property
    def cookies(self):  # noqa: ANN201
        return self._client.cookies

    @cookies.setter
    def cookies(self, value: Any) -> None:
        self._client.cookies = value

    def _csrf_headers(self) -> dict[str, str]:
        if not self._client.cookies.get("csrf_token"):
            response = self._client.get("/api/v1/auth/csrf")
            assert response.status_code == 200, response.text
        token = self._client.cookies.get("csrf_token")
        assert token
        return {"X-CSRF-Token": token}

    def get(self, *args: Any, **kwargs: Any):
        return self._client.get(*args, **kwargs)

    def post(self, url: str, **kwargs: Any):
        headers = {**self._csrf_headers(), **(kwargs.pop("headers", None) or {})}
        return self._client.post(url, headers=headers, **kwargs)

    def put(self, url: str, **kwargs: Any):
        headers = {**self._csrf_headers(), **(kwargs.pop("headers", None) or {})}
        return self._client.put(url, headers=headers, **kwargs)

    def patch(self, url: str, **kwargs: Any):
        headers = {**self._csrf_headers(), **(kwargs.pop("headers", None) or {})}
        return self._client.patch(url, headers=headers, **kwargs)

    def delete(self, url: str, **kwargs: Any):
        headers = {**self._csrf_headers(), **(kwargs.pop("headers", None) or {})}
        return self._client.delete(url, headers=headers, **kwargs)


@pytest.fixture()
def raw_client(
    db_engine, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> Generator[TestClient, None, None]:
    """Bare TestClient (no automatic CSRF) for negative CSRF tests."""
    import app.db.session as db_session_mod
    from app.auth.deps import require_db
    from app.main import app

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    monkeypatch.setattr(db_session_mod, "engine", db_engine)
    monkeypatch.setattr(db_session_mod, "SessionLocal", TestingSessionLocal)

    def _override_db() -> Generator[Session, None, None]:
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[require_db] = _override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def client(raw_client: TestClient) -> CsrfClient:
    return CsrfClient(raw_client)
