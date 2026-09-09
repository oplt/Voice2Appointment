"""Voice session: audio queues and Deepgram/Twilio bridging."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections import deque
from contextvars import ContextVar
from typing import Any

from app.calendars.tools import (
    voice_calendar_service,
    voice_db,
    voice_user_id,
)
from app.core.config import settings
from app.core.correlation import bind_correlation, reset_correlation
from app.core.logging import (
    log_event,
    new_request_id,
    sanitize_for_log,
)
from app.db.session import SessionLocal
from app.industries.clinic import redact_clinic_payload
from app.telephony import lifecycle as call_lifecycle
from app.voice.audio_metrics import (
    estimate_legacy_buffer_latency_ms as estimate_legacy_buffer_latency_ms,
)
from app.voice.config_loader import (
    load_default_config_template as _load_default_config_template,
)
from app.voice.config_loader import load_voice_config_for_context
from app.voice.context import CallContext, bind_call_context, unbind_call_context
from app.voice.function_calls import handle_function_call_request as _handle_function_call_request
from app.voice.latency import LatencyTracker
from app.voice.provider_loop import run_provider_loop
from app.voice.providers.deepgram import (
    DeepgramTransientError,
    sts_connect,
    wait_for_message_type,
)
from app.voice.registry.core import get_tool_registry
from app.voice.registry.validation import (
    is_invalid_arguments_result,
    validate_tool_arguments,
)
from app.voice.transcript import BoundedTranscript
from app.voice.twilio_media import (
    AUDIO_END,
    TwilioMediaMixin,
    audio_queue_maxsize,
)
from app.voice.twilio_media import (
    AUDIO_QUEUE_MAXSIZE as AUDIO_QUEUE_MAXSIZE,
)

logger = logging.getLogger(__name__)

_active_session: ContextVar["VoiceSession | None"] = ContextVar(
    "active_voice_session", default=None
)


def get_call_transcript() -> str:
    """Return the accumulated transcript for the current voice call."""
    sess = _active_session.get()
    if sess is None:
        return ""
    return sess.transcript.text()


def get_active_latency() -> LatencyTracker | None:
    sess = _active_session.get()
    if sess is None:
        return None
    return sess.latency


def load_default_config_template() -> dict:
    return _load_default_config_template()


def load_voice_config(ctx: CallContext) -> dict:
    """Load tenant voice settings while preserving the established public API."""
    return load_voice_config_for_context(ctx, SessionLocal)


def execute_function_call(func_name: str, arguments: dict) -> dict:
    registry = get_tool_registry()
    definition = registry.get(func_name)
    db = voice_db.get()
    user_id = voice_user_id.get()
    if definition is None:
        result: dict[str, Any] = {"error": f"Unknown function: {func_name}"}
        log_event(logger, "function_call_unknown", operation=func_name)
        return result
    if not registry.is_allowed(db, user_id=user_id, tool_name=func_name):
        result = {
            "success": False,
            "error": "tool_not_entitled",
            "message": f"Tool {func_name} is not enabled for this tenant.",
        }
        log_event(logger, "function_call_denied", operation=func_name)
        return result
    validated = validate_tool_arguments(definition, arguments)
    if is_invalid_arguments_result(validated):
        log_event(logger, "function_call_invalid_args", operation=func_name)
        return validated
    result = definition.handler(**validated)
    if definition.redaction.clinic_medical_redact and isinstance(result, dict):
        result = redact_clinic_payload(result)
    log_event(
        logger,
        "function_call_result",
        operation=func_name,
        result=sanitize_for_log(result),
    )
    return result


def _run_tool_in_thread(
    func_name: str,
    arguments: dict,
    ctx: CallContext,
) -> dict:
    """Create a fresh SQLAlchemy Session inside the worker thread (P0-06)."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")
    db = SessionLocal()
    ctx_token = bind_call_context(ctx)
    user_token = voice_user_id.set(ctx.user_id)
    db_token = voice_db.set(db)
    cal_token = voice_calendar_service.set(None)
    try:
        return execute_function_call(func_name, arguments)
    finally:
        voice_calendar_service.reset(cal_token)
        voice_db.reset(db_token)
        voice_user_id.reset(user_token)
        unbind_call_context(ctx_token)
        db.close()


def create_function_call_response(func_id: str, func_name: str, result: dict) -> dict:
    return {
        "type": "FunctionCallResponse",
        "id": func_id,
        "name": func_name,
        "content": json.dumps(result),
    }


async def handle_barge_in(decoded, twilio_ws, streamsid):
    if decoded["type"] == "UserStartedSpeaking":
        clear_message = {"event": "clear", "streamSid": streamsid}
        await twilio_ws.send_text(json.dumps(clear_message))


async def handle_function_call_request(
    decoded,
    sts_ws,
    *,
    ctx: CallContext,
    latency: LatencyTracker,
    tool_results: dict[str, dict] | None = None,
    inflight_tool_ids: set[str] | None = None,
):
    await _handle_function_call_request(
        decoded,
        sts_ws,
        ctx=ctx,
        latency=latency,
        run_tool_in_thread=_run_tool_in_thread,
        create_response=create_function_call_response,
        logger=logger,
        tool_results=tool_results,
        inflight_tool_ids=inflight_tool_ids,
    )


async def handle_text_message(
    decoded,
    twilio_ws,
    sts_ws,
    streamsid,
    latency: LatencyTracker,
    *,
    ctx: CallContext,
    transcript: BoundedTranscript | list[str],
    tool_results: dict[str, dict] | None = None,
    inflight_tool_ids: set[str] | None = None,
):
    latency.ingest_provider_message(decoded)
    await handle_barge_in(decoded, twilio_ws, streamsid)
    if decoded["type"] == "ConversationText":
        role = decoded.get("role", "")
        content = (decoded.get("content") or "").strip()
        if content:
            if isinstance(transcript, BoundedTranscript):
                transcript.append_message(role, content)
            elif len(transcript) < 500:
                transcript.append(f"{role}: {content}")
    if decoded["type"] == "FunctionCallRequest":
        await handle_function_call_request(
            decoded,
            sts_ws,
            ctx=ctx,
            latency=latency,
            tool_results=tool_results,
            inflight_tool_ids=inflight_tool_ids,
        )


async def sts_sender(
    sts_ws, audio_queue: asyncio.Queue, *, on_audio_dequeued=None
) -> None:
    log_event(logger, "sts_sender_started")
    try:
        while True:
            chunk = await audio_queue.get()
            if chunk is AUDIO_END:
                log_event(logger, "sts_sender_end")
                break
            await sts_ws.send(chunk)
            if on_audio_dequeued is not None:
                on_audio_dequeued()
    except asyncio.CancelledError:
        log_event(logger, "sts_sender_cancelled")
        raise


async def sts_receiver(
    sts_ws,
    twilio_ws,
    streamsid_queue: asyncio.Queue,
    latency: LatencyTracker,
    *,
    ctx: CallContext,
    transcript: BoundedTranscript | list[str],
    tool_results: dict[str, dict] | None = None,
    inflight_tool_ids: set[str] | None = None,
) -> None:
    log_event(logger, "sts_receiver_started")
    try:
        streamsid = await streamsid_queue.get()
        # Put streamsid back so reconnects can re-read it.
        await streamsid_queue.put(streamsid)
        async for message in sts_ws:
            if isinstance(message, str):
                decoded = json.loads(message)
                msg_type = decoded.get("type", "unknown")
                log_event(logger, "deepgram_event", message_type=msg_type)
                await handle_text_message(
                    decoded,
                    twilio_ws,
                    sts_ws,
                    streamsid,
                    latency,
                    ctx=ctx,
                    transcript=transcript,
                    tool_results=tool_results,
                    inflight_tool_ids=inflight_tool_ids,
                )
                continue
            if latency is not None:
                latency.note_tts_first_audio()
            media_message = {
                "event": "media",
                "streamSid": streamsid,
                "media": {"payload": base64.b64encode(message).decode("ascii")},
            }
            await twilio_ws.send_text(json.dumps(media_message))
    except asyncio.CancelledError:
        log_event(logger, "sts_receiver_cancelled")
        raise


async def cancel_tasks(*tasks: asyncio.Task[Any] | None) -> None:
    """Cancel pending tasks and await them (Phase 7.3)."""
    pending = [t for t in tasks if t is not None and not t.done()]
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


class VoiceSession(TwilioMediaMixin):
    """Coordinates Twilio media WS <-> Deepgram STS audio queues."""

    def __init__(self, twilio_ws, *, call_context: CallContext | None = None):
        self.twilio_ws = twilio_ws
        self.audio_queue: asyncio.Queue[bytes | bytearray | None] = asyncio.Queue(
            maxsize=audio_queue_maxsize()
        )
        self.streamsid_queue: asyncio.Queue[str] = asyncio.Queue(
            maxsize=1
        )
        self.call_context: CallContext | None = call_context
        self._context_ready = asyncio.Event()
        if call_context is not None:
            self._context_ready.set()
        self._audio_bytes_forwarded = 0
        self._media_frames_forwarded = 0
        self._first_media_at: float | None = None
        self._first_enqueue_at: float | None = None
        self._pending_audio = bytearray()
        self.latency = LatencyTracker()
        self.transcript = BoundedTranscript(
            max_bytes=settings.voice_transcript_max_bytes,
            max_message_bytes=settings.voice_transcript_message_max_bytes,
        )
        self._twilio_done = asyncio.Event()
        self._terminal_status = call_lifecycle.STATUS_COMPLETED
        self._terminal_reason = "websocket:normal"
        self._outcome = "completed"
        # P2-06 media metrics (no payload content)
        self._last_sequence: int | None = None
        self._seq_gaps = 0
        self._seq_duplicates = 0
        self._seq_out_of_order = 0
        self._queue_drops = 0
        self._queue_overflow_drops = 0
        self._queue_high_watermark = 0
        self._oldest_enqueue_at: float | None = None
        self._audio_enqueue_times: deque[float] = deque()
        self._last_media_chunk: dict[str, int] = {}
        self._media_chunk_gaps = 0
        self._media_chunk_duplicates = 0
        self._media_chunk_out_of_order = 0
        self._provider_reconnecting = False
        self._tool_results: dict[str, dict] = {}
        self._inflight_tool_ids: set[str] = set()

    def _begin_reconnect_buffering(self) -> None:
        """Bound outage audio separately, then discard it for a new Agent turn."""
        self._provider_reconnecting = True
        limit = max(1, int(settings.voice_reconnect_buffer_frames))
        while self.audio_queue.qsize() > limit:
            try:
                dropped = self.audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if dropped is not AUDIO_END:
                self._record_queue_drop(overflow=False)
                self._drop_audio_timestamp()

    def _finish_reconnect_buffering(self) -> None:
        """A replacement Agent starts clean; never replay prior-turn audio."""
        if not self._provider_reconnecting:
            return
        while not self.audio_queue.empty():
            try:
                dropped = self.audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if dropped is not AUDIO_END:
                self._record_queue_drop(overflow=False)
                self._drop_audio_timestamp()
        self._provider_reconnecting = False

    async def _run_deepgram_once(self, config: dict, ctx: CallContext) -> None:
        """One Deepgram agent session until Twilio ends or the socket fails."""
        async with sts_connect() as sts_ws:
            await wait_for_message_type(sts_ws, "Welcome", timeout=15)
            await sts_ws.send(json.dumps(config))
            await wait_for_message_type(sts_ws, "SettingsApplied", timeout=15)
            self._finish_reconnect_buffering()

            sender_task = asyncio.create_task(
                sts_sender(
                    sts_ws,
                    self.audio_queue,
                    on_audio_dequeued=self._note_audio_dequeued,
                ),
                name="sts_sender",
            )
            receiver_task = asyncio.create_task(
                sts_receiver(
                    sts_ws,
                    self.twilio_ws,
                    self.streamsid_queue,
                    self.latency,
                    ctx=ctx,
                    transcript=self.transcript,
                    tool_results=self._tool_results,
                    inflight_tool_ids=self._inflight_tool_ids,
                ),
                name="sts_receiver",
            )
            twilio_wait = asyncio.create_task(
                self._twilio_done.wait(), name="twilio_done_wait"
            )
            try:
                done, pending = await asyncio.wait(
                    {sender_task, receiver_task, twilio_wait},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

                if self._twilio_done.is_set():
                    return

                for task in done:
                    if task is twilio_wait:
                        continue
                    if task.cancelled():
                        continue
                    exc = task.exception()
                    if exc is not None:
                        raise exc
                # Clean close of sender/receiver without Twilio stop → treat transient.
                raise DeepgramTransientError("Deepgram bridge task ended early")
            finally:
                await cancel_tasks(sender_task, receiver_task, twilio_wait)

    async def _announce_degraded(self) -> dict[str, str | bool]:
        """Time-bounded, idempotent fallback independent of Deepgram."""
        if self._twilio_done.is_set() or self.call_context is None or SessionLocal is None:
            return {"success": False, "action": "disconnected"}
        ctx = self.call_context

        def _fallback() -> dict[str, str | bool]:
            from app.db.models import User
            from app.telephony.transfer import execute_controlled_fallback

            db = SessionLocal()
            try:
                user = db.get(User, ctx.user_id)
                if user is None:
                    return {"success": False, "action": "unavailable"}
                return execute_controlled_fallback(
                    db, user=user, call_sid=ctx.call_sid
                )
            finally:
                db.close()

        try:
            return await asyncio.wait_for(asyncio.to_thread(_fallback), timeout=5)
        except asyncio.TimeoutError:
            return {"success": False, "action": "timeout"}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Voice fallback failed error=%s", type(exc).__name__)
            return {"success": False, "action": "unavailable"}

    async def run(self) -> None:
        self.transcript.clear()
        log_tokens = {}
        session_token = None
        twilio_task = None
        context_wait = None
        twilio_wait = None
        try:
            request_id = new_request_id()
            log_tokens = bind_correlation(
                request_id=request_id, operation="voice_session"
            )
            session_token = _active_session.set(self)
            twilio_task = asyncio.create_task(
                self._twilio_receiver(), name="twilio_receiver"
            )
            context_wait = asyncio.create_task(
                self._context_ready.wait(), name="voice_context_wait"
            )
            twilio_wait = asyncio.create_task(
                self._twilio_done.wait(), name="voice_start_twilio_wait"
            )
            done, pending = await asyncio.wait(
                {context_wait, twilio_wait},
                timeout=30,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            if twilio_wait in done:
                return
            if context_wait not in done:
                logger.error("Timed out waiting for Twilio start / CallContext")
                self._terminal_status = call_lifecycle.STATUS_DISCONNECTED
                self._terminal_reason = "websocket:start_timeout"
                self._outcome = "failed"
                return
            assert self.call_context is not None
            ctx = self.call_context
            reset_correlation(log_tokens)
            log_tokens = bind_correlation(
                request_id=request_id,
                call_sid=ctx.call_sid,
                user_id=ctx.user_id,
                operation="voice_session",
            )
            config = await asyncio.to_thread(load_voice_config, ctx)
            await run_provider_loop(self, config, ctx)
        except asyncio.CancelledError:
            if self._terminal_status != call_lifecycle.STATUS_PROVIDER_ERROR:
                self._terminal_status = call_lifecycle.STATUS_DISCONNECTED
                self._terminal_reason = "session:cancelled"
                self._outcome = "disconnected"
            raise
        except Exception:
            if self._terminal_status == call_lifecycle.STATUS_COMPLETED:
                self._terminal_status = call_lifecycle.STATUS_PROVIDER_ERROR
                self._terminal_reason = "voice:startup_error"
                self._outcome = "failed"
            raise
        finally:
            self.latency.emit_summary()
            log_event(logger, "voice_media_metrics", fields=self.media_metrics())
            await cancel_tasks(twilio_task, context_wait, twilio_wait)
            if self.call_context is not None:
                for attempt in range(3):
                    try:
                        await asyncio.to_thread(self._persist_terminal)
                        break
                    except Exception as exc:  # noqa: BLE001
                        if attempt == 2:
                            logger.error(
                                "Voice terminal persistence failed attempts=%s error=%s",
                                attempt + 1,
                                type(exc).__name__,
                            )
                        else:
                            await asyncio.sleep(0.05 * (attempt + 1))
            self.transcript.clear()
            if self.call_context is not None:
                from app.calendars.tools import clear_voice_credential_snapshot

                clear_voice_credential_snapshot(self.call_context.call_sid)
            reset_correlation(log_tokens)
            if session_token is not None:
                _active_session.reset(session_token)
