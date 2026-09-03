"""Text-to-speech output for the local hybrid pipeline."""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.voice.providers.deepgram import get_deepgram_settings


class DeepgramTextToSpeech:
    """Synthesize Twilio-ready μ-law 8 kHz audio without an extra conversion."""

    async def synthesize(self, text: str) -> bytes:
        if not settings.deepgram_api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is required for hybrid TTS")
        params = {
            "model": settings.deepgram_tts_model,
            "encoding": "mulaw",
            "sample_rate": "8000",
            "container": "none",
        }
        dg = get_deepgram_settings()
        endpoint = (
            "https://api.eu.deepgram.com/v1/speak"
            if dg.region == "eu"
            else "https://api.deepgram.com/v1/speak"
        )
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                endpoint,
                params=params,
                headers={
                    "Authorization": f"Token {settings.deepgram_api_key}",
                    "Content-Type": "application/json",
                },
                json={"text": text},
            )
            response.raise_for_status()
        return response.content
