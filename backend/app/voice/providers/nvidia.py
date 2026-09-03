"""NVIDIA Speech NIM realtime ASR client.

The GPU model lives in a separate NIM process. This module only speaks the
documented realtime WebSocket protocol from the async voice gateway.
"""

from __future__ import annotations

import asyncio
import base64
import json
import struct
from collections.abc import AsyncIterator
from urllib.parse import urlparse, urlunparse

import httpx
import websockets

from app.core.config import settings
from app.voice.providers.base import TranscriptEvent


class TwilioAudioNormalizer:
    """Convert Twilio mono μ-law 8 kHz frames to mono PCM16 16 kHz."""

    def __init__(self) -> None:
        self._previous_sample: int | None = None

    def normalize(self, chunk: bytes) -> bytes:
        output: list[int] = []
        for encoded in chunk:
            sample = _decode_mulaw(encoded)
            previous = sample if self._previous_sample is None else self._previous_sample
            output.extend(((previous + sample) // 2, sample))
            self._previous_sample = sample
        return struct.pack(f"<{len(output)}h", *output)


def _decode_mulaw(encoded: int) -> int:
    """ITU-T G.711 μ-law byte to signed 16-bit PCM."""
    value = (~encoded) & 0xFF
    magnitude = ((value & 0x0F) << 3) + 0x84
    magnitude <<= (value & 0x70) >> 4
    sample = magnitude - 0x84
    return -sample if value & 0x80 else sample


def _websocket_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = parsed.path.rstrip("/")
    if not path or path == "/":
        path = "/v1/realtime"
    query = parsed.query
    if "intent=" not in query:
        query = f"{query}&intent=transcription" if query else "intent=transcription"
    return urlunparse((scheme, parsed.netloc, path, "", query, ""))


class NvidiaSpeechProvider:
    name = "nvidia"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        language: str | None = None,
    ) -> None:
        self.base_url = (base_url or settings.nvidia_stt_url).rstrip("/")
        self.model = model or settings.nvidia_stt_model
        self.language = language or settings.nvidia_stt_language

    async def available(self) -> bool:
        try:
            async with httpx.AsyncClient(
                timeout=settings.stt_startup_timeout_seconds
            ) as client:
                response = await client.get(f"{self.base_url}/v1/health/ready")
            return response.status_code == 200 and response.json().get("status") in {
                "ok",
                "ready",
            }
        except (httpx.HTTPError, ValueError):
            return False

    async def warmup(self) -> bool:
        """Preflight NIM after its one-time model initialization."""
        if not await self.available():
            return False
        try:
            async with websockets.connect(
                _websocket_url(self.base_url),
                open_timeout=settings.stt_startup_timeout_seconds,
            ) as websocket:
                await asyncio.wait_for(
                    websocket.recv(), timeout=settings.stt_startup_timeout_seconds
                )
            return True
        except (OSError, TimeoutError, websockets.WebSocketException):
            return False

    def _session_update(self) -> str:
        return json.dumps(
            {
                "type": "transcription_session.update",
                "session": {
                    "modalities": ["text"],
                    "input_audio_format": "pcm16",
                    "input_audio_transcription": {
                        "language": self.language,
                        "model": self.model,
                        "prompt": "",
                    },
                    "input_audio_params": {"sample_rate_hz": 16000, "num_channels": 1},
                    "recognition_config": {
                        "max_alternatives": 1,
                        "enable_automatic_punctuation": True,
                        "enable_word_time_offsets": False,
                        "enable_profanity_filter": False,
                        "enable_verbatim_transcripts": False,
                    },
                },
            }
        )

    async def transcribe_stream(
        self, audio: AsyncIterator[bytes]
    ) -> AsyncIterator[TranscriptEvent]:
        normalizer = TwilioAudioNormalizer()
        async with websockets.connect(
            _websocket_url(self.base_url),
            open_timeout=settings.stt_startup_timeout_seconds,
        ) as websocket:
            await websocket.send(self._session_update())

            async def send_audio() -> None:
                async for chunk in audio:
                    message = {
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(normalizer.normalize(chunk)).decode("ascii"),
                    }
                    await websocket.send(json.dumps(message))
                await websocket.send(json.dumps({"type": "input_audio_buffer.done"}))

            sender = asyncio.create_task(send_audio(), name="nvidia_stt_sender")
            try:
                async for raw in websocket:
                    if not isinstance(raw, str):
                        continue
                    message = json.loads(raw)
                    event_type = message.get("type")
                    if event_type == "conversation.item.input_audio_transcription.delta":
                        text = str(message.get("delta") or "").strip()
                        if text:
                            yield TranscriptEvent(text=text, is_final=False)
                    elif event_type == "conversation.item.input_audio_transcription.completed":
                        text = str(message.get("transcript") or "").strip()
                        if text:
                            yield TranscriptEvent(text=text, is_final=True)
                    elif event_type in {
                        "conversation.item.input_audio_transcription.failed",
                        "error",
                    }:
                        raise RuntimeError("NVIDIA transcription failed")
                    if (
                        sender.done()
                        and event_type
                        == "conversation.item.input_audio_transcription.completed"
                    ):
                        break
            finally:
                if not sender.done():
                    sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)
