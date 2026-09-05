"""Twilio-side media ingestion and CallSession persistence."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import time
from collections import deque
from typing import Any

from app.core.config import settings
from app.core.logging import log_event
from app.db.session import SessionLocal
from app.telephony import lifecycle as call_lifecycle
from app.voice.context import CallContext
from app.voice.latency import LatencyTracker
from app.voice.transcript import BoundedTranscript

AUDIO_END = None
AUDIO_QUEUE_MAXSIZE = 50
logger = logging.getLogger(__name__)


def audio_queue_maxsize() -> int:
    try:
        return max(1, int(settings.voice_audio_queue_maxsize))
    except (TypeError, ValueError):
        return AUDIO_QUEUE_MAXSIZE


class TwilioMediaMixin:
    """Media and persistence behavior mixed into the voice orchestrator."""

    twilio_ws: Any
    audio_queue: asyncio.Queue[Any]
    streamsid_queue: asyncio.Queue[str]
    call_context: CallContext | None
    _context_ready: asyncio.Event
    _audio_bytes_forwarded: int
    _media_frames_forwarded: int
    _first_media_at: float | None
    _first_enqueue_at: float | None
    _pending_audio: bytearray
    latency: LatencyTracker
    transcript: BoundedTranscript
    _twilio_done: asyncio.Event
    _terminal_status: str
    _terminal_reason: str
    _outcome: str
    _last_sequence: int | None
    _seq_gaps: int
    _seq_duplicates: int
    _seq_out_of_order: int
    _queue_drops: int
    _queue_overflow_drops: int
    _queue_high_watermark: int
    _oldest_enqueue_at: float | None
    _audio_enqueue_times: deque[float]
    _last_media_chunk: dict[str, int]
    _media_chunk_gaps: int
    _media_chunk_duplicates: int
    _media_chunk_out_of_order: int
    _provider_reconnecting: bool

    def media_metrics(self) -> dict[str, int | float | None]:
        age_ms: float | None = None
        if self._oldest_enqueue_at is not None and self.audio_queue.qsize() > 0:
            age_ms = round((time.perf_counter() - self._oldest_enqueue_at) * 1000, 2)
        return {
            "seq_gaps": self._seq_gaps,
            "seq_duplicates": self._seq_duplicates,
            "seq_out_of_order": self._seq_out_of_order,
            "media_chunk_gaps": self._media_chunk_gaps,
            "media_chunk_duplicates": self._media_chunk_duplicates,
            "media_chunk_out_of_order": self._media_chunk_out_of_order,
            "queue_drops": self._queue_drops,
            "queue_depth": self.audio_queue.qsize(),
            "queue_high_watermark": self._queue_high_watermark,
            "queue_oldest_age_ms": age_ms,
            "frames": self._media_frames_forwarded,
        }

    def _note_media_chunk(self, track: object, raw: object) -> None:
        """Track media chunks per track, independently of sequenceNumber."""
        if raw is None:
            return
        try:
            chunk = int(str(raw))
        except (TypeError, ValueError):
            return
        key = str(track or "unknown")
        previous = self._last_media_chunk.get(key)
        if previous is None:
            self._last_media_chunk[key] = chunk
        elif chunk == previous:
            self._media_chunk_duplicates += 1
            self._record_anomaly("chunk_duplicate")
        elif chunk < previous:
            self._media_chunk_out_of_order += 1
            self._record_anomaly("chunk_reordered")
        elif chunk > previous + 1:
            self._media_chunk_gaps += chunk - previous - 1
            self._last_media_chunk[key] = chunk
            self._record_anomaly("chunk_gap", chunk - previous - 1)
        else:
            self._last_media_chunk[key] = chunk

    def _note_audio_dequeued(self) -> None:
        if self._audio_enqueue_times:
            self._observe_queue(
                bridge_latency_ms=(time.perf_counter() - self._audio_enqueue_times[0])
                * 1000
            )
        if self._audio_enqueue_times:
            self._audio_enqueue_times.popleft()
        self._oldest_enqueue_at = (
            self._audio_enqueue_times[0] if self._audio_enqueue_times else None
        )

    def _drop_audio_timestamp(self) -> None:
        if self._audio_enqueue_times:
            self._audio_enqueue_times.popleft()
        self._oldest_enqueue_at = (
            self._audio_enqueue_times[0] if self._audio_enqueue_times else None
        )

    def _note_sequence(self, raw: object) -> None:
        if raw is None:
            return
        try:
            seq = int(str(raw))
        except (TypeError, ValueError):
            return
        if self._last_sequence is None:
            self._last_sequence = seq
            return
        expected = self._last_sequence + 1
        if seq == self._last_sequence:
            self._seq_duplicates += 1
            self._record_anomaly("sequence_duplicate")
        elif seq < self._last_sequence:
            self._seq_out_of_order += 1
            self._record_anomaly("sequence_reordered")
        elif seq > expected:
            self._seq_gaps += seq - expected
            self._last_sequence = seq
            self._record_anomaly("sequence_gap", seq - expected)
        else:
            self._last_sequence = seq

    def _record_anomaly(self, result: str, amount: int = 1) -> None:
        from app.core.metrics import metrics

        metrics.incr(
            "voice_media_anomalies",
            amount=float(amount),
            labels={"provider": "twilio", "result": result},
        )

    def _observe_queue(self, *, bridge_latency_ms: float | None = None) -> None:
        from app.core.metrics import metrics

        values = self.media_metrics()
        labels = {"provider": "twilio", "result": "sample"}
        metrics.observe("voice_audio_queue_depth", float(values["queue_depth"] or 0), labels=labels)
        age = values.get("queue_oldest_age_ms")
        if age is not None:
            metrics.observe("voice_audio_queue_age_ms", float(age), labels=labels)
        if bridge_latency_ms is not None:
            metrics.observe(
                "voice_audio_bridge_latency_ms", bridge_latency_ms, labels=labels
            )

    def _record_queue_drop(self, *, overflow: bool) -> bool:
        self._queue_drops += 1
        self._record_anomaly("queue_drop")
        if not overflow:
            return False
        self._queue_overflow_drops += 1
        return self._queue_overflow_drops >= max(
            1, int(settings.voice_audio_queue_max_drops)
        )

    def _terminate_for_backpressure(self) -> None:
        self._terminal_status = call_lifecycle.STATUS_PROVIDER_ERROR
        self._terminal_reason = "voice:audio_backpressure"
        self._outcome = "failed"

    async def _enqueue_audio(self, chunk: bytes | bytearray) -> bool:
        if not chunk:
            return True
        if self._first_media_at is None:
            self._first_media_at = time.perf_counter()
            self.latency.note_twilio_audio()
        reconnect_limit = max(1, int(settings.voice_reconnect_buffer_frames))
        if self._provider_reconnecting and self.audio_queue.qsize() >= reconnect_limit:
            self._record_queue_drop(overflow=False)
            self._observe_queue()
            return True
        while self.audio_queue.full():
            try:
                dropped = self.audio_queue.get_nowait()
                if dropped is AUDIO_END:
                    await self.audio_queue.put(AUDIO_END)
                    return False
                terminate = self._record_queue_drop(overflow=True)
                self._drop_audio_timestamp()
                self._observe_queue()
                if terminate:
                    self._terminate_for_backpressure()
                    return False
            except asyncio.QueueEmpty:
                break
        now = time.perf_counter()
        await self.audio_queue.put(bytes(chunk))
        self._audio_enqueue_times.append(now)
        self._oldest_enqueue_at = self._audio_enqueue_times[0]
        depth = self.audio_queue.qsize()
        if depth > self._queue_high_watermark:
            self._queue_high_watermark = depth
        self._observe_queue()
        if self._first_enqueue_at is None:
            self._first_enqueue_at = now
            self.latency.note_audio_enqueued()
        self._audio_bytes_forwarded += len(chunk)
        self._media_frames_forwarded += 1
        return True

    async def _flush_pending_audio(self) -> None:
        if self._pending_audio:
            await self._enqueue_audio(self._pending_audio)
            self._pending_audio.clear()

    async def _signal_audio_end(self) -> None:
        try:
            while self.audio_queue.full():
                try:
                    dropped = self.audio_queue.get_nowait()
                    if dropped is not AUDIO_END:
                        self._record_queue_drop(overflow=False)
                        self._drop_audio_timestamp()
                except asyncio.QueueEmpty:
                    break
            await self.audio_queue.put(AUDIO_END)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed to enqueue audio end sentinel")

    def _persist_connected(self, streamsid: str | None) -> None:
        if SessionLocal is None or self.call_context is None:
            return
        from sqlalchemy import select

        from app.db.models import CallSession

        db = SessionLocal()
        try:
            call_lifecycle.mark_connected(db, self.call_context.call_sid)
            if streamsid:
                call = db.scalar(
                    select(CallSession).where(
                        CallSession.call_sid == self.call_context.call_sid
                    )
                )
                if call is not None:
                    call.stream_sid = streamsid
                    db.commit()
        finally:
            db.close()

    def _persist_terminal(self) -> None:
        if SessionLocal is None or self.call_context is None:
            return
        from app.core.logging import redact_phones
        from app.db.models import User
        from app.users.product_prefs import load_product_prefs

        db = SessionLocal()
        try:
            user = db.get(User, self.call_context.user_id)
            prefs = load_product_prefs(user.config_json if user is not None else None)
            capture = prefs.transcripts
            consented = bool(capture.storage_enabled and capture.consent_at)
            transcript = self.transcript.text() if consented else None
            if transcript is not None and capture.redact_phone_numbers:
                transcript = redact_phones(transcript)
            metadata = self.transcript.metadata()
            metadata.update(
                {
                    "storage": "consented" if consented else "not_stored_no_consent",
                    "redaction_policy": (
                        "phone_numbers" if capture.redact_phone_numbers else "none"
                    ),
                }
            )
            call_lifecycle.finalize_voice_session(
                db,
                call_sid=self.call_context.call_sid,
                status=self._terminal_status,
                terminal_reason=self._terminal_reason,
                transcript=transcript,
                transcript_metadata=metadata,
                outcome=self._outcome,
            )
        finally:
            db.close()

    async def _resolve_start(self, data: dict) -> None:
        start = data.get("start") or {}
        streamsid = start.get("streamSid")
        if streamsid:
            while not self.streamsid_queue.empty():
                try:
                    self.streamsid_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            await self.streamsid_queue.put(streamsid)
        if self.call_context is None:
            raise RuntimeError("CallContext missing after gateway auth")
        await asyncio.to_thread(self._persist_connected, streamsid)
        self._context_ready.set()

    async def _twilio_receiver(self) -> None:
        try:
            while True:
                try:
                    message = await self.twilio_ws.receive_text()
                except Exception:
                    if self._terminal_status != call_lifecycle.STATUS_PROVIDER_ERROR:
                        self._terminal_status = call_lifecycle.STATUS_DISCONNECTED
                        self._terminal_reason = "websocket:peer_disconnect"
                        self._outcome = "disconnected"
                    break
                try:
                    data = json.loads(message)
                    event = data["event"]
                    self._note_sequence(data.get("sequenceNumber"))
                    if event == "start":
                        await self._resolve_start(data)
                    elif event == "connected":
                        continue
                    elif event == "media":
                        media = data["media"]
                        self._note_media_chunk(media.get("track"), media.get("chunk"))
                        chunk = base64.b64decode(media["payload"], validate=True)
                        if media.get("track") == "inbound":
                            if not await self._enqueue_audio(chunk):
                                break
                    elif event == "stop":
                        if self._terminal_status != call_lifecycle.STATUS_PROVIDER_ERROR:
                            self._terminal_status = call_lifecycle.STATUS_COMPLETED
                            self._terminal_reason = "websocket:twilio_stop"
                            self._outcome = "completed"
                        await self._flush_pending_audio()
                        break
                except (KeyError, TypeError, ValueError, binascii.Error):
                    if self._terminal_status != call_lifecycle.STATUS_PROVIDER_ERROR:
                        self._terminal_status = call_lifecycle.STATUS_DISCONNECTED
                        self._terminal_reason = "websocket:malformed_message"
                        self._outcome = "failed"
                    break
                except Exception:
                    self._terminal_status = call_lifecycle.STATUS_PROVIDER_ERROR
                    self._terminal_reason = "voice:receiver_error"
                    self._outcome = "failed"
                    logger.exception("Twilio media receiver failed")
                    break
        finally:
            await self._flush_pending_audio()
            await self._signal_audio_end()
            self._twilio_done.set()
            metrics = self.media_metrics()
            if self._first_media_at and self._first_enqueue_at:
                lag_ms = (self._first_enqueue_at - self._first_media_at) * 1000
                metrics["first_enqueue_lag_ms"] = round(lag_ms, 2)
            log_event(
                logger,
                "voice_audio_forward_stats",
                fields={key: value for key, value in metrics.items() if value is not None},
            )
            self._observe_queue()
