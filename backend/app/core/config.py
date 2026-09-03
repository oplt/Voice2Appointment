"""Application settings for the FastAPI modular monolith."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_ROOT.parent

load_dotenv(_REPO_ROOT / ".env")
load_dotenv(_BACKEND_ROOT / ".env", override=True)

_SAME_SITE = frozenset({"lax", "strict", "none"})


def _cookie_samesite() -> Literal["lax", "strict", "none"]:
    raw = os.getenv("COOKIE_SAMESITE", "lax").strip().lower()
    if raw not in _SAME_SITE:
        return "lax"
    return raw  # type: ignore[return-value]


@dataclass
class Settings:
    secret_key: str = os.getenv("SECRET_KEY", "")
    database_url: str = os.getenv("DATABASE_URL", "")
    fernet_key: str = os.getenv("FERNET_KEY", "")
    app_env: str = os.getenv("APP_ENV", "development").strip().lower()
    debug: bool = field(default=False)

    twilio_account_sid: str | None = os.getenv("TWILIO_ACCOUNT_SID")
    twilio_auth_token: str | None = os.getenv("TWILIO_AUTH_TOKEN")
    twilio_phone_number: str | None = os.getenv("TWILIO_PHONE_NUMBER")

    deepgram_api_key: str | None = os.getenv("DEEPGRAM_API_KEY")
    deepgram_region: str = os.getenv("DEEPGRAM_REGION", "")
    deepgram_model: str = os.getenv("DEEPGRAM_MODEL", "nova-3")
    deepgram_language: str = os.getenv("DEEPGRAM_LANGUAGE", "en")
    deepgram_agent_url: str = os.getenv("DEEPGRAM_AGENT_URL", "")

    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    celery_broker_url: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    celery_result_backend: str = os.getenv(
        "CELERY_RESULT_BACKEND", "redis://localhost:6379/0"
    )

    cors_origins: list[str] = field(
        default_factory=lambda: [
            origin.strip()
            for origin in os.getenv(
                "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
            ).split(",")
            if origin.strip()
        ]
    )

    # Local HTTP needs secure=False so the auth cookie is stored.
    cookie_secure: bool = os.getenv("COOKIE_SECURE", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    cookie_samesite: Literal["lax", "strict", "none"] = field(
        default_factory=_cookie_samesite
    )

    mail_username: str | None = os.getenv("EMAIL_USER")
    mail_password: str | None = os.getenv("EMAIL_PASSWORD")
    mail_server: str = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    mail_port: int = int(os.getenv("MAIL_PORT", "587"))
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:5173")

    call_expires_in: int = int(os.getenv("CALL_EXPIRES_IN", "5"))
    default_timezone: str = os.getenv("DEFAULT_TIMEZONE", "Europe/Brussels")

    log_format: str = os.getenv("LOG_FORMAT", "json").strip().lower()
    sentry_dsn: str = os.getenv("SENTRY_DSN", "")
    sentry_traces_sample_rate: float = float(
        os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")
    )

    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # DEBUG is ignored in production — never run with debug=True there.
        raw_debug = os.getenv("DEBUG", "false").lower() in {"1", "true", "yes"}
        if self.is_production:
            object.__setattr__(self, "debug", False)
        else:
            object.__setattr__(self, "debug", raw_debug)

    @property
    def is_production(self) -> bool:
        return self.app_env in {"prod", "production"}

    def require_runtime_secrets(self) -> None:
        """Fail startup if required secrets are missing or invalid."""
        missing: list[str] = []
        if not (self.secret_key or "").strip():
            missing.append("SECRET_KEY")
        if not (self.fernet_key or "").strip():
            missing.append("FERNET_KEY")
        if not (self.database_url or "").strip():
            missing.append("DATABASE_URL")
        if missing:
            raise RuntimeError(
                "Missing required settings: "
                + ", ".join(missing)
                + ". Set them in the environment or .env before starting."
            )
        try:
            from cryptography.fernet import Fernet

            Fernet(self.fernet_key.encode("utf-8"))
        except Exception as exc:  # noqa: BLE001 — surface clear startup error
            raise RuntimeError(
                "FERNET_KEY is invalid. Generate one with: "
                "python -c \"from cryptography.fernet import Fernet; "
                'print(Fernet.generate_key().decode())"'
            ) from exc


settings = Settings()
