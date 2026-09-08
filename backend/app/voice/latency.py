"""Voice / Deepgram latency recording (Phase 13.2–13.3 / Phase 12 metrics)."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.core.logging import log_event

logger = logging.getLogger(__name__)


class LatencyTracker:
    """Tracks interaction stages for one voice call."""

    def __init__(self) -> None:
        self.t0 = time.perf_counter()
        self._marks: dict[str, float] = {"interaction_start": self.t0}
        self._latencies_ms: dict[str, float] = {}
        self._provider: dict[str, float] = {}

    def mark(self, name: str, *, at: float | None = None) -> None:
        if name in self._marks:
            return
        self._marks[name] = at if at is not None else time.perf_counter()

    def measure(self, name: str, start_mark: str, end_mark: str | None = None) -> float | None:
        start = self._marks.get(start_mark)
        end = self._marks.get(end_mark) if end_mark else time.perf_counter()
        if start is None or end is None:
            return None
        ms = (end - start) * 1000.0
        self._latencies_ms[name] = round(ms, 2)
        return self._latencies_ms[name]

    def record_ms(self, name: str, ms: float, *, provider: bool = False) -> None:
        value = round(float(ms), 2)
        if provider:
            self._provider[name] = value
        else:
            self._latencies_ms[name] = value

    def note_twilio_audio(self) -> None:
        self.mark("twilio_audio")

    def note_audio_enqueued(self) -> None:
        self.mark("audio_enqueued")
        self.measure("twilio_audio_to_stt_queue_ms", "twilio_audio", "audio_enqueued")

    def note_stt_final(self) -> None:
        self.mark("stt_final")
        if "twilio_audio" in self._marks:
            self.measure("twilio_audio_to_stt_final_ms", "twilio_audio", "stt_final")
        self.measure("stt_final_ms", "interaction_start", "stt_final")

    def note_llm_response(self) -> None:
        self.mark("llm_response")
        if "stt_final" in self._marks:
            self.measure("llm_response_ms", "stt_final", "llm_response")
        else:
            self.measure("llm_response_ms", "interaction_start", "llm_response")

    def note_tts_first_audio(self) -> None:
        self.mark("tts_first_audio")
        if "llm_response" in self._marks:
            self.measure("tts_first_audio_ms", "llm_response", "tts_first_audio")
        elif "stt_final" in self._marks:
            self.measure("tts_first_audio_ms", "stt_final", "tts_first_audio")
        else:
            self.measure("tts_first_audio_ms", "interaction_start", "tts_first_audio")

    def note_calendar(self, operation: str, started_at: float) -> None:
        ms = (time.perf_counter() - started_at) * 1000.0
        key = f"calendar_{operation}_ms"
        self.record_ms(key, ms)
        log_event(
            logger,
            "latency",
            operation=f"calendar_{operation}",
            latency_ms=round(ms, 2),
        )
        try:
            from app.core.metrics import metrics

            label = "lookup" if operation in {"availability", "list", "get"} else operation
            if operation in {"create", "insert", "update", "delete"}:
                label = "create" if operation == "insert" else operation
            metrics.observe(
                "calendar_request_latency_ms",
                ms,
                labels={"operation": label[:32], "result": "success"},
            )
        except Exception:  # noqa: BLE001
            pass

    def ingest_provider_message(self, decoded: dict[str, Any]) -> None:
        """Capture Deepgram latency fields when present (Phase 13.3)."""
        msg_type = decoded.get("type")
        for key in ("latency", "latency_ms", "total_latency", "total_latency_ms"):
            value = decoded.get(key)
            if isinstance(value, (int, float)):
                self.record_ms(f"provider_{key}", float(value), provider=True)

        nested = decoded.get("latencies") or decoded.get("timing") or decoded.get("metrics")
        if isinstance(nested, dict):
            mapping = {
                "stt": "provider_stt_ms",
                "stt_latency": "provider_stt_ms",
                "llm": "provider_llm_ms",
                "llm_latency": "provider_llm_ms",
                "tts": "provider_tts_ms",
                "tts_latency": "provider_tts_ms",
            }
            for src, dest in mapping.items():
                value = nested.get(src)
                if isinstance(value, (int, float)):
                    self.record_ms(dest, float(value), provider=True)

        if msg_type == "ConversationText":
            role = (decoded.get("role") or "").lower()
            if role == "user":
                self.note_stt_final()
            elif role in {"assistant", "agent"}:
                self.note_llm_response()
        elif msg_type in {"AgentStartedSpeaking", "AgentAudioDone"}:
            if msg_type == "AgentStartedSpeaking":
                self.note_llm_response()
        elif msg_type == "UserStartedSpeaking":
            self.mark("user_started_speaking")

    def snapshot(self) -> dict[str, Any]:
        full_ms = round((time.perf_counter() - self.t0) * 1000.0, 2)
        return {
            "full_interaction_ms": full_ms,
            "latencies_ms": dict(self._latencies_ms),
            "provider_latencies_ms": dict(self._provider),
            "marks": sorted(self._marks.keys()),
        }

    def emit_summary(self) -> None:
        snap = self.snapshot()
        log_event(logger, "voice_latency_summary", **snap)
        try:
            from app.core.metrics import metrics

            first = self._latencies_ms.get("tts_first_audio_ms")
            if first is None:
                first = self._latencies_ms.get("llm_response_ms")
            if first is not None:
                metrics.observe("voice_first_response_ms", float(first))
            for key, metric_name in (
                ("stt_final_ms", "voice_stt_final_ms"),
                ("llm_response_ms", "voice_llm_response_ms"),
                ("tts_first_audio_ms", "voice_tts_first_audio_ms"),
                ("twilio_audio_to_stt_queue_ms", "voice_audio_to_stt_queue_ms"),
            ):
                value = self._latencies_ms.get(key)
                if value is not None:
                    metrics.observe(metric_name, float(value))
            for key, value in self._provider.items():
                metrics.observe(
                    "voice_provider_latency_ms",
                    float(value),
                    labels={"stage": key[:40]},
                )
        except Exception:  # noqa: BLE001
            pass
