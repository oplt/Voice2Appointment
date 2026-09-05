"""Reconnect policy for a live voice provider session."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.core.config import settings
from app.core.logging import log_event
from app.telephony import lifecycle as call_lifecycle
from app.voice.providers.deepgram import (
    DeepgramAuthError,
    DeepgramTransientError,
    classify_deepgram_error,
    is_retryable_disconnect,
)

logger = logging.getLogger(__name__)


async def run_provider_loop(session: Any, config: dict, ctx: Any) -> None:
    max_attempts = max(0, int(settings.deepgram_reconnect_max_attempts))
    backoff = max(0.05, float(settings.deepgram_reconnect_backoff_seconds))
    deadline = max(1.0, float(settings.deepgram_reconnect_deadline_seconds))
    outage_deadline: float | None = None
    attempts = 0
    while True:
        try:
            remaining = (
                None
                if outage_deadline is None
                else outage_deadline - time.perf_counter()
            )
            if remaining is not None and remaining <= 0:
                raise DeepgramTransientError("Deepgram reconnect deadline exceeded")
            if remaining is None:
                await session._run_deepgram_once(config, ctx)
            else:
                await asyncio.wait_for(
                    session._run_deepgram_once(config, ctx), timeout=remaining
                )
            if session._twilio_done.is_set():
                # The receiver records whether this was an explicit Twilio
                # stop, malformed media, or a peer disconnect.  Do not turn
                # every completed receiver task into a successful call.
                return
        except DeepgramAuthError as exc:
            if session._twilio_done.is_set():
                return
            logger.error("Deepgram auth failure type=%s", type(exc).__name__)
            session._terminal_status = call_lifecycle.STATUS_PROVIDER_ERROR
            session._terminal_reason = "deepgram:auth"
            session._outcome = "failed"
            return
        except Exception as exc:
            if session._twilio_done.is_set():
                return
            kind = classify_deepgram_error(exc)
            if kind is DeepgramAuthError or not is_retryable_disconnect(exc):
                session._terminal_reason = (
                    "deepgram:auth"
                    if kind is DeepgramAuthError
                    else f"deepgram:{type(exc).__name__}"
                )
                session._terminal_status = call_lifecycle.STATUS_PROVIDER_ERROR
                session._outcome = "failed"
                logger.error("Deepgram terminal failure type=%s", type(exc).__name__)
                return
            if outage_deadline is None:
                outage_deadline = time.perf_counter() + deadline
            attempts += 1
            remaining = outage_deadline - time.perf_counter()
            if attempts > max_attempts or remaining <= 0:
                logger.error(
                    "Deepgram reconnect budget exhausted attempts=%s remaining=%.2f",
                    attempts,
                    max(0.0, remaining),
                )
                result = await session._announce_degraded()
                action = result.get("action", "unavailable")
                success = bool(result.get("success"))
                session._terminal_status = call_lifecycle.STATUS_PROVIDER_ERROR
                session._terminal_reason = (
                    f"deepgram:fallback_{action}" if success else "deepgram:fallback_failed"
                )
                session._outcome = f"fallback_{action}" if success else "fallback_failed"
                return
            session._begin_reconnect_buffering()
            sleep_for = min(backoff * (2 ** (attempts - 1)), 5.0, remaining)
            log_event(
                logger,
                "deepgram_reconnect",
                attempt=attempts,
                sleep_seconds=sleep_for,
                error=type(exc).__name__,
            )
            await asyncio.sleep(sleep_for)
            if session._twilio_done.is_set():
                return
