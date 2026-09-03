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
    deepgram_tts_model: str = os.getenv("DEEPGRAM_TTS_MODEL", "aura-asteria-en")

    # Supported voice pipeline (P2-03): deepgram_agent only.
    voice_pipeline: str = os.getenv("VOICE_PIPELINE", "deepgram_agent").strip().lower()

    # Deepgram reconnect budget (P2-02)
    deepgram_reconnect_max_attempts: int = int(
        os.getenv("DEEPGRAM_RECONNECT_MAX_ATTEMPTS", "3")
    )
    deepgram_reconnect_backoff_seconds: float = float(
        os.getenv("DEEPGRAM_RECONNECT_BACKOFF_SECONDS", "0.5")
    )
    deepgram_reconnect_deadline_seconds: float = float(
        os.getenv("DEEPGRAM_RECONNECT_DEADLINE_SECONDS", "20")
    )
    voice_audio_queue_maxsize: int = int(os.getenv("VOICE_AUDIO_QUEUE_MAXSIZE", "50"))
    voice_reconnect_buffer_frames: int = int(
        os.getenv("VOICE_RECONNECT_BUFFER_FRAMES", "50")
    )
    # Per-process media session cap (P8-01). Scale horizontally for larger N.
    voice_max_concurrent_calls: int = int(os.getenv("VOICE_MAX_CONCURRENT_CALLS", "25"))

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
    frontend_base_url: str = os.getenv(
        "FRONTEND_BASE_URL",
        os.getenv("PUBLIC_BASE_URL", "http://localhost:5173"),
    )

    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_redirect_uri: str = os.getenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/api/v1/calendars/google/callback",
    )

    # Comma-separated CIDRs of reverse proxies allowed to set X-Forwarded-For.
    trusted_proxy_cidrs: str = os.getenv(
        "TRUSTED_PROXY_CIDRS", "127.0.0.1/32,::1/128,10.0.0.0/8,172.16.0.0/12"
    )

    call_expires_in: int = int(os.getenv("CALL_EXPIRES_IN", "5"))
    stream_token_ttl_seconds: int = int(os.getenv("STREAM_TOKEN_TTL_SECONDS", "300"))
    default_timezone: str = os.getenv("DEFAULT_TIMEZONE", "Europe/Brussels")

    # Recording download hardening (P0-04)
    recording_max_bytes: int = int(os.getenv("RECORDING_MAX_BYTES", str(50 * 1024 * 1024)))
    recording_download_timeout_seconds: float = float(
        os.getenv("RECORDING_DOWNLOAD_TIMEOUT_SECONDS", "30")
    )
    twilio_media_hosts: frozenset[str] = field(
        default_factory=lambda: frozenset(
            h.strip().lower()
            for h in os.getenv(
                "TWILIO_MEDIA_HOSTS",
                "api.twilio.com,api.ashburn.us1.twilio.com,"
                "api.dublin.ie1.twilio.com,api.sydney.au1.twilio.com,"
                "api.tokyo.jp1.twilio.com,api.singapore.sg1.twilio.com",
            ).split(",")
            if h.strip()
        )
    )

    twilio_sync_page_size: int = int(os.getenv("TWILIO_SYNC_PAGE_SIZE", "100"))
    twilio_sync_max_pages: int = int(os.getenv("TWILIO_SYNC_MAX_PAGES", "50"))
    twilio_sync_lookback_seconds: int = int(
        os.getenv("TWILIO_SYNC_LOOKBACK_SECONDS", "300")
    )

    analytics_max_range_days: int = int(os.getenv("ANALYTICS_MAX_RANGE_DAYS", "366"))
    analytics_default_range_days: int = int(
        os.getenv("ANALYTICS_DEFAULT_RANGE_DAYS", "30")
    )
    reporting_currency: str = os.getenv("REPORTING_CURRENCY", "").strip().upper()

    redis_socket_connect_timeout: float = float(
        os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "0.5")
    )
    redis_socket_timeout: float = float(os.getenv("REDIS_SOCKET_TIMEOUT", "1.0"))
    redis_retry_after_seconds: float = float(
        os.getenv("REDIS_RETRY_AFTER_SECONDS", "30")
    )

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
        if self.voice_pipeline != "deepgram_agent":
            raise RuntimeError(
                f"Unsupported VOICE_PIPELINE={self.voice_pipeline!r}. "
                "Only 'deepgram_agent' is supported."
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

        if self.is_production:
            problems: list[str] = []
            if len((self.secret_key or "").strip()) < 32:
                problems.append("SECRET_KEY must be at least 32 characters")
            if not self.cookie_secure:
                problems.append("COOKIE_SECURE must be true in production")
            if self.cookie_samesite == "none" and not self.cookie_secure:
                problems.append("COOKIE_SAMESITE=none requires COOKIE_SECURE=true")
            pub = (self.public_base_url or "").strip().lower()
            if not pub.startswith("https://"):
                problems.append("PUBLIC_BASE_URL must be https:// in production")
            if not self.cors_origins:
                problems.append("CORS_ORIGINS must be non-empty in production")
            if problems:
                raise RuntimeError(
                    "Unsafe production configuration: " + "; ".join(problems)
                )


settings = Settings()
