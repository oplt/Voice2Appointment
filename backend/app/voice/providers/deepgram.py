"""Deepgram speech-to-speech connection and settings (Phase 8)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import websockets
from websockets.typing import Subprotocol

from app.core.config import settings

logger = logging.getLogger(__name__)

_GLOBAL_AGENT = "wss://agent.deepgram.com/v1/agent/converse"
_EU_AGENT = "wss://api.eu.deepgram.com/v1/agent/converse"


@dataclass(frozen=True)
class DeepgramSettings:
    """Central speech-provider configuration (keep small)."""

    api_key: str | None
    region: str
    model: str
    language: str
    endpoint: str

    @classmethod
    def from_settings(cls) -> DeepgramSettings:
        explicit = (settings.deepgram_agent_url or "").strip()
        region = (settings.deepgram_region or "").strip().lower()
        if not region:
            tz = (settings.default_timezone or "").strip()
            region = "eu" if tz.startswith("Europe/") else "global"
        if region in {"eu", "europe"}:
            region = "eu"
            endpoint = explicit or _EU_AGENT
        elif region in {"us", "usa"}:
            region = "us"
            endpoint = explicit or _GLOBAL_AGENT
        else:
            region = "global"
            endpoint = explicit or _GLOBAL_AGENT
        return cls(
            api_key=settings.deepgram_api_key,
            region=region,
            model=settings.deepgram_model,
            language=settings.deepgram_language,
            endpoint=endpoint,
        )


def get_deepgram_settings() -> DeepgramSettings:
    return DeepgramSettings.from_settings()


def sts_connect():
    """Return an awaitable Deepgram agent websocket connection context manager."""
    dg = get_deepgram_settings()
    if not dg.api_key:
        raise RuntimeError("DEEPGRAM_API_KEY not found")
    logger.info("Connecting Deepgram agent region=%s endpoint=%s", dg.region, dg.endpoint)
    return websockets.connect(  # type: ignore[attr-defined]
        dg.endpoint,
        subprotocols=[Subprotocol("token"), Subprotocol(dg.api_key)],
    )


async def wait_for_message_type(sts_ws, expected_type: str, *, timeout: float = 15.0):
    """Read Deepgram JSON messages until ``type`` matches (handshake helper)."""
    import asyncio
    import json

    async def _loop():
        async for raw in sts_ws:
            if not isinstance(raw, str):
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == expected_type:
                return msg
            logger.debug("Deepgram handshake skip type=%s", msg.get("type"))
        raise RuntimeError(f"Deepgram socket closed before {expected_type}")

    return await asyncio.wait_for(_loop(), timeout=timeout)
