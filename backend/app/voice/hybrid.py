"""NVIDIA/Deepgram STT → local LLM/tools → Deepgram TTS orchestration."""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator

from app.core.config import settings
from app.voice.orchestration import OpenAICompatibleOrchestrator
from app.voice.providers.base import SpeechToTextProvider
from app.voice.providers.deepgram import DeepgramSpeechProvider
from app.voice.providers.nvidia import NvidiaSpeechProvider
from app.voice.tts import DeepgramTextToSpeech


async def audio_from_queue(audio_queue) -> AsyncIterator[bytes]:
    while True:
        chunk = await audio_queue.get()
        if chunk is None:
            return
        yield bytes(chunk)


async def select_stt_provider() -> SpeechToTextProvider:
    """Resolve provider once at call startup; never switch mid-utterance."""
    configured: SpeechToTextProvider
    if settings.stt_provider == "nvidia":
        configured = NvidiaSpeechProvider()
    else:
        configured = DeepgramSpeechProvider()
    if await configured.available():
        return configured

    fallback = settings.stt_fallback_provider
    if fallback == "none" or fallback == settings.stt_provider:
        raise RuntimeError(f"Configured STT provider unavailable: {configured.name}")
    alternate: SpeechToTextProvider
    if fallback == "nvidia":
        alternate = NvidiaSpeechProvider()
    else:
        alternate = DeepgramSpeechProvider()
    if not await alternate.available():
        raise RuntimeError(
            f"STT providers unavailable: {configured.name}, {alternate.name}"
        )
    return alternate


async def run_hybrid_pipeline(
    *,
    provider: SpeechToTextProvider,
    audio_queue,
    twilio_ws,
    streamsid_queue,
    timezone_name: str,
    latency=None,
) -> None:
    stream_sid = await streamsid_queue.get()
    orchestrator = OpenAICompatibleOrchestrator(timezone_name=timezone_name)
    tts = DeepgramTextToSpeech()
    speaking_detected = False
    async for event in provider.transcribe_stream(audio_from_queue(audio_queue)):
        if not event.is_final:
            if not speaking_detected:
                await twilio_ws.send_text(
                    json.dumps({"event": "clear", "streamSid": stream_sid})
                )
                speaking_detected = True
            continue
        speaking_detected = False
        if latency is not None:
            latency.note_stt_final()
        response_text = await orchestrator.respond(event.text)
        if latency is not None:
            latency.note_llm_response()
        audio = await tts.synthesize(response_text)
        if latency is not None:
            latency.note_tts_first_audio()
        for offset in range(0, len(audio), 160):
            payload = base64.b64encode(audio[offset : offset + 160]).decode("ascii")
            await twilio_ws.send_text(
                json.dumps(
                    {
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {"payload": payload},
                    }
                )
            )
