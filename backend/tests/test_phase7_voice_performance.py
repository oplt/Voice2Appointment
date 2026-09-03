"""PHASE 7 real-time voice performance tests (tasks.txt)."""

from __future__ import annotations

import asyncio
import base64
import inspect
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.voice import session as voice_session
from app.voice.session import (
    AUDIO_QUEUE_MAXSIZE,
    VoiceSession,
    estimate_legacy_buffer_latency_ms,
    handle_function_call_request,
)


def test_legacy_buffer_was_about_400ms() -> None:
    assert estimate_legacy_buffer_latency_ms() == pytest.approx(400.0)


def test_audio_queue_is_bounded() -> None:
    sess = VoiceSession(MagicMock())
    assert sess.audio_queue.maxsize == AUDIO_QUEUE_MAXSIZE
    assert AUDIO_QUEUE_MAXSIZE == 50


def test_forwards_each_media_frame_without_coalesce() -> None:
    """A single 160-byte Twilio frame must enqueue immediately (no 20-frame wait)."""

    async def _run() -> None:
        twilio_ws = MagicMock()
        frame = bytes(160)
        payload = base64.b64encode(frame).decode("ascii")
        messages = [
            json.dumps(
                {
                    "event": "media",
                    "media": {"track": "inbound", "payload": payload},
                }
            ),
            json.dumps({"event": "stop"}),
        ]

        async def _recv():
            if not messages:
                raise RuntimeError("closed")
            return messages.pop(0)

        twilio_ws.receive_text = AsyncMock(side_effect=_recv)
        sess = VoiceSession(twilio_ws)
        sess._context_ready.set()

        await sess._twilio_receiver()

        assert sess._media_frames_forwarded == 1
        first = sess.audio_queue.get_nowait()
        assert first == frame
        assert sess.audio_queue.get_nowait() is None

    asyncio.run(_run())


def test_stop_flushes_pending_residual() -> None:
    async def _run() -> None:
        twilio_ws = MagicMock()
        twilio_ws.receive_text = AsyncMock(
            side_effect=[json.dumps({"event": "stop"}), RuntimeError("closed")]
        )
        sess = VoiceSession(twilio_ws)
        sess._pending_audio.extend(b"\x00\x01\x02")
        await sess._twilio_receiver()
        assert sess.audio_queue.get_nowait() == b"\x00\x01\x02"
        assert sess.audio_queue.get_nowait() is None
        assert sess._pending_audio == bytearray()

    asyncio.run(_run())


def test_cancel_tasks_cancels_pending() -> None:
    async def _run() -> None:
        async def _hang():
            await asyncio.Event().wait()

        task = asyncio.create_task(_hang())
        await voice_session.cancel_tasks(task)
        assert task.cancelled() or task.done()

    asyncio.run(_run())


def test_function_calls_offloaded_to_thread() -> None:
    async def _run() -> None:
        decoded = {
            "functions": [
                {
                    "id": "f1",
                    "name": "check_calendar_availability",
                    "arguments": "{}",
                }
            ]
        }
        sts_ws = MagicMock()
        sts_ws.send = AsyncMock()

        with patch(
            "app.voice.session.asyncio.to_thread", new_callable=AsyncMock
        ) as to_thread:
            to_thread.return_value = {"available": True}
            await handle_function_call_request(decoded, sts_ws)
            to_thread.assert_awaited()
            sts_ws.send.assert_awaited()

    asyncio.run(_run())


def test_no_legacy_buffer_constant_in_source() -> None:
    source = inspect.getsource(voice_session)
    assert "20 * 160" not in source
    assert "BUFFER_SIZE" not in source
