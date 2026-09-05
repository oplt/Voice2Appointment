"""Deepgram speech-to-speech connection and settings (Phase 8 / P2)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlparse

import websockets
from websockets.exceptions import (
    ConnectionClosed,
    InvalidHandshake,
    InvalidStatus,
    InvalidURI,
)
from websockets.typing import Subprotocol

from app.core.config import settings

logger = logging.getLogger(__name__)

_GLOBAL_AGENT = "wss://agent.deepgram.com/v1/agent/converse"
_EU_AGENT = "wss://api.eu.deepgram.com/v1/agent/converse"


class DeepgramAuthError(RuntimeError):
    """Permanent credential/configuration failure — do not retry."""


class DeepgramTransientError(RuntimeError):
    """Network/service failure — may reconnect within budget."""


@dataclass(frozen=True)
class DeepgramSettings:
    """Central speech-provider configuration (global app credential only)."""

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
            language="en",  # P6-V05 gate: ignore DEEPGRAM_LANGUAGE until multilingual enabled
            endpoint=endpoint,
        )


def get_deepgram_settings() -> DeepgramSettings:
    return DeepgramSettings.from_settings()


def classify_deepgram_error(exc: BaseException) -> type[Exception]:
    """Return DeepgramAuthError or DeepgramTransientError class for ``exc``."""
    if isinstance(exc, DeepgramAuthError):
        return DeepgramAuthError
    if isinstance(exc, InvalidURI):
        return DeepgramAuthError
    if isinstance(exc, InvalidStatus):
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None) or getattr(
            response, "status", None
        )
        if status in {401, 403}:
            return DeepgramAuthError
        if status == 429 or (isinstance(status, int) and status >= 500):
            return DeepgramTransientError
        # Other upgrade rejections are malformed endpoint/configuration errors.
        return DeepgramAuthError
    if isinstance(exc, InvalidHandshake):
        return DeepgramTransientError
    if isinstance(exc, ConnectionClosed) and getattr(exc, "code", None) == 1008:
        return DeepgramAuthError
    text = str(exc).lower()
    if any(
        needle in text
        for needle in ("401", "403", "unauthorized", "forbidden", "invalid api key")
    ):
        return DeepgramAuthError
    return DeepgramTransientError


def sts_connect():
    """Return an awaitable Deepgram agent websocket connection context manager."""
    dg = get_deepgram_settings()
    if not dg.api_key:
        raise DeepgramAuthError("DEEPGRAM_API_KEY not found")
    parsed = urlparse(dg.endpoint)
    if parsed.scheme != "wss" or not parsed.netloc:
        raise DeepgramAuthError("DEEPGRAM_AGENT_URL must be an absolute wss URL")
    logger.info("Connecting Deepgram agent region=%s endpoint=%s", dg.region, dg.endpoint)
    return websockets.connect(  # type: ignore[attr-defined]
        dg.endpoint,
        subprotocols=[Subprotocol("token"), Subprotocol(dg.api_key)],
        open_timeout=10,
        close_timeout=5,
    )


def is_retryable_disconnect(exc: BaseException | None) -> bool:
    if exc is None:
        return False
    if classify_deepgram_error(exc) is DeepgramAuthError:
        return False
    return isinstance(
        exc,
        (
            ConnectionClosed,
            DeepgramTransientError,
            InvalidHandshake,
            InvalidStatus,
            OSError,
            TimeoutError,
        ),
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
        raise DeepgramTransientError(f"Deepgram socket closed before {expected_type}")

    return await asyncio.wait_for(_loop(), timeout=timeout)
