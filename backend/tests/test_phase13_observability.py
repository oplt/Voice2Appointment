"""PHASE 13: structured logging, latency, optional Sentry."""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

from app.core.logging import (
    StructuredFormatter,
    bind_log_context,
    mask_phone,
    reset_log_context,
    sanitize_for_log,
    setup_logging,
)
from app.core.sentry import init_sentry
from app.voice.latency import LatencyTracker


def test_mask_phone_keeps_last_four() -> None:
    assert mask_phone("+32470123456") == "***3456"
    assert mask_phone("123") == "****"


def test_sanitize_redacts_secrets_and_transcripts() -> None:
    payload = {
        "api_key": "secret-key",
        "twilio_auth_token": "tok",
        "transcript": "Book me a dentist appointment tomorrow at three",
        "description": "Patient notes that should not appear in logs forever",
        "from": "+32470123456",
        "ok": True,
    }
    safe = sanitize_for_log(payload)
    assert safe["api_key"] == "[redacted]"
    assert safe["twilio_auth_token"] == "[redacted]"
    assert str(safe["transcript"]).startswith("[redacted:")
    assert str(safe["description"]).startswith("[redacted:")
    assert safe["from"] == "***3456"
    assert safe["ok"] is True


def test_structured_formatter_includes_context_fields() -> None:
    setup_logging()
    tokens = bind_log_context(
        request_id="req123",
        call_sid="CAabc",
        user_id=42,
        operation="test_op",
    )
    try:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        # Apply filter fields.
        from app.core.logging import ContextFilter

        ContextFilter().filter(record)
        line = StructuredFormatter().format(record)
        data = json.loads(line)
        assert data["request_id"] == "req123"
        assert data["call_sid"] == "CAabc"
        assert data["user_id"] == 42
        assert data["operation"] == "test_op"
        assert data["msg"] == "hello"
    finally:
        reset_log_context(tokens)


def test_latency_tracker_records_pipeline_stages() -> None:
    tracker = LatencyTracker()
    tracker.note_twilio_audio()
    tracker.note_audio_enqueued()
    tracker.ingest_provider_message(
        {"type": "ConversationText", "role": "user", "content": "secret transcript"}
    )
    tracker.ingest_provider_message(
        {"type": "ConversationText", "role": "assistant", "content": "ok"}
    )
    tracker.note_tts_first_audio()
    tracker.ingest_provider_message(
        {"type": "Metrics", "latencies": {"stt": 120.5, "llm": 200, "tts": 80}}
    )
    snap = tracker.snapshot()
    assert "twilio_audio_to_stt_queue_ms" in snap["latencies_ms"]
    assert "twilio_audio_to_stt_final_ms" in snap["latencies_ms"]
    assert "llm_response_ms" in snap["latencies_ms"]
    assert "tts_first_audio_ms" in snap["latencies_ms"]
    assert snap["provider_latencies_ms"]["provider_stt_ms"] == 120.5
    assert snap["full_interaction_ms"] >= 0


def test_http_request_sets_request_id_header(client) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")


def test_init_sentry_noop_without_dsn(monkeypatch) -> None:
    from app.core import sentry as sentry_mod
    from app.core.config import settings

    monkeypatch.setattr(settings, "sentry_dsn", "")
    sentry_mod._initialized = False
    assert init_sentry() is False


def test_init_sentry_optional_when_dsn_set(monkeypatch) -> None:
    from app.core import sentry as sentry_mod
    from app.core.config import settings

    monkeypatch.setattr(settings, "sentry_dsn", "https://example@sentry.io/1")
    monkeypatch.setattr(settings, "sentry_traces_sample_rate", 0.0)
    sentry_mod._initialized = False
    fake_sdk = MagicMock()
    with patch.dict(
        "sys.modules",
        {
            "sentry_sdk": fake_sdk,
            "sentry_sdk.integrations.fastapi": MagicMock(FastApiIntegration=MagicMock),
            "sentry_sdk.integrations.logging": MagicMock(LoggingIntegration=MagicMock),
            "sentry_sdk.integrations.starlette": MagicMock(
                StarletteIntegration=MagicMock
            ),
        },
    ):
        assert init_sentry() is True
        fake_sdk.init.assert_called_once()
    sentry_mod._initialized = False
