"""Phase 17: provider selection, audio normalization, and hybrid turns."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

from app.core.config import Settings, settings
from app.voice import hybrid
from app.voice.providers.base import TranscriptEvent
from app.voice.providers.nvidia import NvidiaSpeechProvider, TwilioAudioNormalizer
from scripts.benchmark_stt import summarize, word_error_rate


def test_deepgram_agent_remains_default(monkeypatch) -> None:
    monkeypatch.delenv("VOICE_PIPELINE", raising=False)
    monkeypatch.delenv("STT_PROVIDER", raising=False)
    config = Settings()
    assert config.voice_pipeline == "deepgram_agent"
    assert config.stt_provider == "deepgram"


def test_nvidia_normalizes_mulaw_8khz_to_pcm16_16khz() -> None:
    output = TwilioAudioNormalizer().normalize(bytes([0xFF] * 160))
    assert len(output) == 160 * 2 * 2
    assert output == bytes(len(output))


def test_nvidia_session_uses_current_streaming_model() -> None:
    provider = NvidiaSpeechProvider(
        base_url="http://nvidia:9000",
        model="nemotron-3.5-asr-streaming-0.6b",
        language="auto",
    )
    event = json.loads(provider._session_update())
    session = event["session"]
    assert session["input_audio_format"] == "pcm16"
    assert session["input_audio_params"] == {"sample_rate_hz": 16000, "num_channels": 1}
    assert session["input_audio_transcription"]["model"] == (
        "nemotron-3.5-asr-streaming-0.6b"
    )


def test_provider_fallback_happens_at_call_start(monkeypatch) -> None:
    class UnavailableNvidia:
        name = "nvidia"

        async def available(self) -> bool:
            return False

    class AvailableDeepgram:
        name = "deepgram"

        async def available(self) -> bool:
            return True

    monkeypatch.setattr(settings, "stt_provider", "nvidia")
    monkeypatch.setattr(settings, "stt_fallback_provider", "deepgram")
    monkeypatch.setattr(hybrid, "NvidiaSpeechProvider", UnavailableNvidia)
    monkeypatch.setattr(hybrid, "DeepgramSpeechProvider", AvailableDeepgram)
    provider = asyncio.run(hybrid.select_stt_provider())
    assert provider.name == "deepgram"


def test_hybrid_pipeline_runs_final_transcript_through_llm_and_tts(monkeypatch) -> None:
    class Provider:
        name = "nvidia"

        async def available(self) -> bool:
            return True

        async def transcribe_stream(self, _audio):
            yield TranscriptEvent("Book", is_final=False)
            yield TranscriptEvent("Book a consultation tomorrow", is_final=True)

    orchestrator = AsyncMock()
    orchestrator.respond.return_value = "What time works for you?"
    tts = AsyncMock()
    tts.synthesize.return_value = bytes(200)
    monkeypatch.setattr(
        hybrid, "OpenAICompatibleOrchestrator", lambda **_kwargs: orchestrator
    )
    monkeypatch.setattr(hybrid, "DeepgramTextToSpeech", lambda: tts)

    async def run() -> list[dict]:
        audio_queue: asyncio.Queue = asyncio.Queue()
        stream_queue: asyncio.Queue = asyncio.Queue()
        await audio_queue.put(None)
        await stream_queue.put("MZ1")
        websocket = AsyncMock()
        await hybrid.run_hybrid_pipeline(
            provider=Provider(),
            audio_queue=audio_queue,
            twilio_ws=websocket,
            streamsid_queue=stream_queue,
            timezone_name="Europe/Brussels",
        )
        return [json.loads(call.args[0]) for call in websocket.send_text.await_args_list]

    messages = asyncio.run(run())
    assert messages[0] == {"event": "clear", "streamSid": "MZ1"}
    assert [message["event"] for message in messages[1:]] == ["media", "media"]
    orchestrator.respond.assert_awaited_once_with("Book a consultation tomorrow")


def test_benchmark_scores_quality_latency_resources_and_cost() -> None:
    assert word_error_rate("book at three", "book at four") == 1 / 3
    report = summarize(
        [
            {
                "provider": "nvidia_nemotron_3_5",
                "language": "tr-TR",
                "reference": "yarın saat üç",
                "transcript": "yarın saat üç",
                "entities": ["üç"],
                "date_times": ["yarın", "üç"],
                "first_partial_ms": 90,
                "final_transcript_ms": 420,
                "gpu_utilization_percent": 40,
                "ram_mb": 8000,
                "cost_per_minute": 0.004,
            }
        ]
    )["nvidia_nemotron_3_5:tr-TR"]
    assert report["wer"] == 0
    assert report["entity_accuracy"] == 1
    assert report["date_time_accuracy"] == 1
    assert report["first_partial_ms"] == 90
    assert report["gpu_utilization_percent"] == 40
