"""Application settings for the FastAPI modular monolith."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from dotenv import load_dotenv

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_ROOT.parent

load_dotenv(_REPO_ROOT / ".env")
load_dotenv(_BACKEND_ROOT / ".env", override=True)

_SAME_SITE = frozenset({"lax", "strict", "none"})
_GOOGLE_CALLBACK_PATH = "/api/v1/calendars/google/callback"


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
    # Supported voice pipeline (P2-03): deepgram_agent only.
    voice_pipeline: str = field(
        default_factory=lambda: os.getenv("VOICE_PIPELINE", "deepgram_agent")
        .strip()
        .lower()
    )

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
    voice_audio_queue_max_drops: int = int(
        os.getenv("VOICE_AUDIO_QUEUE_MAX_DROPS", "50")
    )
    voice_reconnect_buffer_frames: int = int(
        os.getenv("VOICE_RECONNECT_BUFFER_FRAMES", "50")
    )
    # Per-process media session cap (P8-01). Scale horizontally for larger N.
    voice_max_concurrent_calls: int = int(os.getenv("VOICE_MAX_CONCURRENT_CALLS", "25"))
    voice_transcript_max_bytes: int = int(
        os.getenv("VOICE_TRANSCRIPT_MAX_BYTES", "32768")
    )
    voice_transcript_message_max_bytes: int = int(
        os.getenv("VOICE_TRANSCRIPT_MESSAGE_MAX_BYTES", "4096")
    )

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
    allowed_hosts: list[str] = field(
        default_factory=lambda: [
            host.strip().lower()
            for host in os.getenv(
                "ALLOWED_HOSTS", "localhost,127.0.0.1,testserver"
            ).split(",")
            if host.strip()
        ]
    )
    request_max_body_bytes: int = int(
        os.getenv("REQUEST_MAX_BODY_BYTES", str(2 * 1024 * 1024))
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
    password_reset_enabled: bool = os.getenv(
        "PASSWORD_RESET_ENABLED", "true"
    ).lower() in {"1", "true", "yes"}
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
    twilio_active_refresh_batch_size: int = int(
        os.getenv("TWILIO_ACTIVE_REFRESH_BATCH_SIZE", "100")
    )
    twilio_active_refresh_interval_seconds: int = int(
        os.getenv("TWILIO_ACTIVE_REFRESH_INTERVAL_SECONDS", "60")
    )

    analytics_max_range_days: int = int(os.getenv("ANALYTICS_MAX_RANGE_DAYS", "366"))
    analytics_default_range_days: int = int(
        os.getenv("ANALYTICS_DEFAULT_RANGE_DAYS", "30")
    )
    analytics_legacy_max_calls: int = int(
        os.getenv("ANALYTICS_LEGACY_MAX_CALLS", "10000")
    )
    calendar_max_range_days: int = int(
        os.getenv("CALENDAR_MAX_RANGE_DAYS", "366")
    )
    reporting_currency: str = os.getenv("REPORTING_CURRENCY", "").strip().upper()

    redis_socket_connect_timeout: float = float(
        os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "0.5")
    )
    redis_socket_timeout: float = float(os.getenv("REDIS_SOCKET_TIMEOUT", "1.0"))
    redis_retry_after_seconds: float = float(
        os.getenv("REDIS_RETRY_AFTER_SECONDS", "30")
    )
    redis_max_connections: int = int(os.getenv("REDIS_MAX_CONNECTIONS", "20"))
    redis_pool_timeout: float = float(os.getenv("REDIS_POOL_TIMEOUT", "0.5"))

    log_format: str = os.getenv("LOG_FORMAT", "json").strip().lower()
    sentry_dsn: str = os.getenv("SENTRY_DSN", "")
    sentry_traces_sample_rate: float = float(
        os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")
    )

    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # DEBUG is ignored in production — never run with debug=True there.
        object.__setattr__(self, "voice_pipeline", self.voice_pipeline.strip().lower())
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
        positive_limits = {
            "TWILIO_SYNC_PAGE_SIZE": self.twilio_sync_page_size,
            "TWILIO_SYNC_MAX_PAGES": self.twilio_sync_max_pages,
            "TWILIO_ACTIVE_REFRESH_BATCH_SIZE": self.twilio_active_refresh_batch_size,
            "TWILIO_ACTIVE_REFRESH_INTERVAL_SECONDS": self.twilio_active_refresh_interval_seconds,
            "ANALYTICS_LEGACY_MAX_CALLS": self.analytics_legacy_max_calls,
            "CALENDAR_MAX_RANGE_DAYS": self.calendar_max_range_days,
            "REDIS_MAX_CONNECTIONS": self.redis_max_connections,
            "REDIS_POOL_TIMEOUT": self.redis_pool_timeout,
            "REDIS_SOCKET_CONNECT_TIMEOUT": self.redis_socket_connect_timeout,
            "REDIS_SOCKET_TIMEOUT": self.redis_socket_timeout,
            "REDIS_RETRY_AFTER_SECONDS": self.redis_retry_after_seconds,
        }
        invalid_limits = [name for name, value in positive_limits.items() if value <= 0]
        if self.request_max_body_bytes <= 0:
            invalid_limits.append("REQUEST_MAX_BODY_BYTES")
        if invalid_limits:
            raise RuntimeError(
                "Settings must be positive: " + ", ".join(sorted(invalid_limits))
            )
        if self.redis_max_connections > 1_000:
            raise RuntimeError("REDIS_MAX_CONNECTIONS must not exceed 1000")
        redis_timeouts = {
            "REDIS_POOL_TIMEOUT": self.redis_pool_timeout,
            "REDIS_SOCKET_CONNECT_TIMEOUT": self.redis_socket_connect_timeout,
            "REDIS_SOCKET_TIMEOUT": self.redis_socket_timeout,
            "REDIS_RETRY_AFTER_SECONDS": self.redis_retry_after_seconds,
        }
        too_large_timeouts = [
            name for name, value in redis_timeouts.items() if value > 60
        ]
        if too_large_timeouts:
            raise RuntimeError(
                "Redis timeouts must not exceed 60 seconds: "
                + ", ".join(sorted(too_large_timeouts))
            )
        voice_buffers = {
            "VOICE_AUDIO_QUEUE_MAXSIZE": self.voice_audio_queue_maxsize,
            "VOICE_AUDIO_QUEUE_MAX_DROPS": self.voice_audio_queue_max_drops,
            "VOICE_RECONNECT_BUFFER_FRAMES": self.voice_reconnect_buffer_frames,
        }
        invalid_voice_buffers = [
            name for name, value in voice_buffers.items() if not 1 <= value <= 500
        ]
        if invalid_voice_buffers:
            raise RuntimeError(
                "Voice buffer limits must be between 1 and 500: "
                + ", ".join(sorted(invalid_voice_buffers))
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
            def https_url(value: str, name: str, *, origin_only: bool = False) -> Any:
                parsed = urlparse((value or "").strip())
                if (
                    parsed.scheme != "https"
                    or not parsed.hostname
                    or parsed.username
                    or parsed.password
                    or (origin_only and parsed.path not in {"", "/"})
                    or parsed.query
                    or parsed.fragment
                ):
                    problems.append(f"{name} must be an HTTPS origin in production")
                return parsed

            if not self.allowed_hosts or any(
                host == "*" or "://" in host or "/" in host
                for host in self.allowed_hosts
            ):
                problems.append("ALLOWED_HOSTS must contain explicit host names in production")
            pub = https_url(self.public_base_url, "PUBLIC_BASE_URL", origin_only=True)
            frontend = https_url(
                self.frontend_base_url, "FRONTEND_BASE_URL", origin_only=True
            )
            callback = https_url(self.google_redirect_uri, "GOOGLE_REDIRECT_URI")
            if callback.path != _GOOGLE_CALLBACK_PATH:
                problems.append("GOOGLE_REDIRECT_URI must use the configured callback path")
            for origin in self.cors_origins:
                https_url(origin, "CORS_ORIGINS", origin_only=True)
                if origin.strip() == "*":
                    problems.append("CORS_ORIGINS must not contain wildcard origins")
            if pub.hostname and pub.hostname not in self.allowed_hosts:
                problems.append("PUBLIC_BASE_URL host must be in ALLOWED_HOSTS")
            if callback.hostname and callback.hostname not in self.allowed_hosts:
                problems.append("GOOGLE_REDIRECT_URI host must be in ALLOWED_HOSTS")
            if frontend.hostname and frontend.geturl().rstrip("/") not in {
                origin.rstrip("/") for origin in self.cors_origins
            }:
                problems.append("FRONTEND_BASE_URL must be included in CORS_ORIGINS")
            if not self.cors_origins:
                problems.append("CORS_ORIGINS must be non-empty in production")
            if bool(self.google_client_id) != bool(self.google_client_secret):
                problems.append("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured together")
            if not (self.deepgram_api_key or "").strip():
                problems.append("DEEPGRAM_API_KEY is required for the enabled voice pipeline")
            if self.password_reset_enabled and (
                not self.mail_username or not self.mail_password
            ):
                problems.append(
                    "EMAIL_USER and EMAIL_PASSWORD are required when password reset is enabled"
                )
            if problems:
                raise RuntimeError(
                    "Unsafe production configuration: " + "; ".join(problems)
                )


settings = Settings()
