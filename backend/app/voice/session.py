"""Voice session: audio queues and Deepgram/Twilio bridging."""

from __future__ import annotations

import asyncio
import base64
import copy
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from pathlib import Path

from app.calendars.tool_schemas import AGENT_SYSTEM_PROMPT, VOICE_TOOL_DEFINITIONS
from app.calendars.tools import FUNCTION_MAP, voice_calendar_service, voice_db, voice_user_id
from app.core.config import settings
from app.core.logging import (
    bind_log_context,
    log_event,
    new_request_id,
    reset_log_context,
    sanitize_for_log,
)
from app.db.models import User
from app.db.session import SessionLocal
from app.telephony import lifecycle as call_lifecycle
from app.voice.context import CallContext, bind_call_context, unbind_call_context
from app.voice.dates import get_current_date_context
from app.voice.latency import LatencyTracker
from app.voice.providers.deepgram import (
    DeepgramAuthError,
    DeepgramTransientError,
    classify_deepgram_error,
    get_deepgram_settings,
    is_retryable_disconnect,
    sts_connect,
    wait_for_message_type,
)

logger = logging.getLogger(__name__)

# Bounded thread pool for voice tool calls (DB + Google Calendar).
_VOICE_TOOL_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="voice-tool")

_DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.json"

AUDIO_QUEUE_MAXSIZE = 50
STREAMSID_QUEUE_MAXSIZE = 1
_AUDIO_END = None  # sentinel: end of inbound audio
_MAX_TRANSCRIPT_LINES = 500

_active_session: ContextVar["VoiceSession | None"] = ContextVar(
    "active_voice_session", default=None
)


def get_call_transcript() -> str:
    """Return the accumulated transcript for the current voice call."""
    sess = _active_session.get()
    if sess is None:
        return ""
    return "\n".join(sess.transcript)


def get_active_latency() -> LatencyTracker | None:
    sess = _active_session.get()
    if sess is None:
        return None
    return sess.latency


def load_default_config_template() -> dict:
    with open(_DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_voice_config(ctx: CallContext) -> dict:
    """Load tenant voice settings from User.config_json; fall back to template."""
    config = load_default_config_template()
    if SessionLocal is not None:
        db = SessionLocal()
        try:
            user = db.get(User, ctx.user_id)
            if user and user.config_json:
                try:
                    overlay = json.loads(user.config_json)
                except json.JSONDecodeError:
                    logger.error(
                        "Invalid config_json for user_id=%s; using defaults",
                        ctx.user_id,
                    )
                else:
                    if isinstance(overlay, dict) and overlay.get("type") == "Settings":
                        config = overlay
                    elif isinstance(overlay, dict):
                        config = _deep_merge(copy.deepcopy(config), overlay)
        finally:
            db.close()

    think = config.setdefault("agent", {}).setdefault("think", {})
    think["functions"] = copy.deepcopy(VOICE_TOOL_DEFINITIONS)

    dg = get_deepgram_settings()
    listen = config.setdefault("agent", {}).setdefault("listen", {}).setdefault(
        "provider", {}
    )
    listen["model"] = dg.model
    if dg.language:
        listen["language"] = dg.language

    current_date_context = get_current_date_context(timezone_name=ctx.timezone)
    think["prompt"] = AGENT_SYSTEM_PROMPT.format(
        current_date_context=current_date_context
    )
    return config


def _deep_merge(base: dict, overlay: dict) -> dict:
    for key, value in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            base[key] = _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def execute_function_call(func_name: str, arguments: dict) -> dict:
    if func_name in FUNCTION_MAP:
        result = FUNCTION_MAP[func_name](**arguments)
        log_event(
            logger,
            "function_call_result",
            operation=func_name,
            result=sanitize_for_log(result),
        )
        return result
    result = {"error": f"Unknown function: {func_name}"}
    log_event(logger, "function_call_unknown", operation=func_name)
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
    decoded, sts_ws, *, ctx: CallContext, latency: LatencyTracker
):
    """Run sync Google/tool work off the event loop with explicit call context."""
    func_id = "unknown"
    func_name = "unknown"
    try:
        for function_call in decoded["functions"]:
            func_name = function_call["name"]
            func_id = function_call["id"]
            arguments = json.loads(function_call["arguments"])
            log_event(
                logger,
                "function_call",
                operation=func_name,
                func_id=func_id,
                arguments=sanitize_for_log(arguments),
            )
            started = time.perf_counter()
            result = await asyncio.to_thread(
                _run_tool_in_thread, func_name, arguments, ctx
            )
            latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
            if "availability" in func_name or "find_" in func_name:
                latency.record_ms("calendar_lookup_ms", latency_ms)
            elif "create_" in func_name:
                latency.record_ms("calendar_create_ms", latency_ms)
            function_result = create_function_call_response(func_id, func_name, result)
            await sts_ws.send(json.dumps(function_result))
            log_event(
                logger,
                "function_call_sent",
                operation=func_name,
                func_id=func_id,
                latency_ms=latency_ms,
            )
    except Exception as e:
        logger.exception("Error calling function operation=%s", func_name)
        error_result = create_function_call_response(
            func_id,
            func_name,
            {"error": f"Function call failed with: {e.__class__.__name__}"},
        )
        await sts_ws.send(json.dumps(error_result))


async def handle_text_message(
    decoded,
    twilio_ws,
    sts_ws,
    streamsid,
    latency: LatencyTracker,
    *,
    ctx: CallContext,
    transcript: list[str],
):
    latency.ingest_provider_message(decoded)
    await handle_barge_in(decoded, twilio_ws, streamsid)
    if decoded["type"] == "ConversationText":
        role = decoded.get("role", "")
        content = (decoded.get("content") or "").strip()
        if content:
            if len(transcript) < _MAX_TRANSCRIPT_LINES:
                transcript.append(f"{role}: {content}")
    if decoded["type"] == "FunctionCallRequest":
        await handle_function_call_request(decoded, sts_ws, ctx=ctx, latency=latency)


async def sts_sender(sts_ws, audio_queue: asyncio.Queue) -> None:
    log_event(logger, "sts_sender_started")
    try:
        while True:
            chunk = await audio_queue.get()
            if chunk is _AUDIO_END:
                log_event(logger, "sts_sender_end")
                break
            await sts_ws.send(chunk)
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
    transcript: list[str],
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


async def cancel_tasks(*tasks: asyncio.Task) -> None:
    """Cancel pending tasks and await them (Phase 7.3)."""
    pending = [t for t in tasks if t is not None and not t.done()]
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


def _audio_queue_maxsize() -> int:
    try:
        return max(1, int(settings.voice_audio_queue_maxsize))
    except (TypeError, ValueError):
        return AUDIO_QUEUE_MAXSIZE


class VoiceSession:
    """Coordinates Twilio media WS <-> Deepgram STS audio queues."""

    def __init__(self, twilio_ws, *, call_context: CallContext | None = None):
        self.twilio_ws = twilio_ws
        self.audio_queue: asyncio.Queue[bytes | bytearray | None] = asyncio.Queue(
            maxsize=_audio_queue_maxsize()
        )
        self.streamsid_queue: asyncio.Queue[str] = asyncio.Queue(
            maxsize=STREAMSID_QUEUE_MAXSIZE
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
        self.transcript: list[str] = []
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
        self._queue_high_watermark = 0
        self._oldest_enqueue_at: float | None = None

    def media_metrics(self) -> dict[str, int | float | None]:
        age_ms: float | None = None
        if self._oldest_enqueue_at is not None and self.audio_queue.qsize() > 0:
            age_ms = round((time.perf_counter() - self._oldest_enqueue_at) * 1000, 2)
        return {
            "seq_gaps": self._seq_gaps,
            "seq_duplicates": self._seq_duplicates,
            "seq_out_of_order": self._seq_out_of_order,
            "queue_drops": self._queue_drops,
            "queue_depth": self.audio_queue.qsize(),
            "queue_high_watermark": self._queue_high_watermark,
            "queue_oldest_age_ms": age_ms,
            "frames": self._media_frames_forwarded,
        }

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
        elif seq < self._last_sequence:
            self._seq_out_of_order += 1
        elif seq > expected:
            self._seq_gaps += seq - expected
            self._last_sequence = seq
        else:
            self._last_sequence = seq

    async def _enqueue_audio(self, chunk: bytes | bytearray) -> None:
        if not chunk:
            return
        if self._first_media_at is None:
            self._first_media_at = time.perf_counter()
            self.latency.note_twilio_audio()
        # Bounded queue: drop oldest inbound frame under backpressure (P2-06).
        while self.audio_queue.full():
            try:
                dropped = self.audio_queue.get_nowait()
                if dropped is _AUDIO_END:
                    # Preserve end sentinel — put back and stop enqueue.
                    await self.audio_queue.put(_AUDIO_END)
                    return
                self._queue_drops += 1
                # Dropped the oldest frame; refresh watermark clock.
                self._oldest_enqueue_at = time.perf_counter()
            except asyncio.QueueEmpty:
                break
        now = time.perf_counter()
        await self.audio_queue.put(bytes(chunk))
        if self._oldest_enqueue_at is None:
            self._oldest_enqueue_at = now
        depth = self.audio_queue.qsize()
        if depth > self._queue_high_watermark:
            self._queue_high_watermark = depth
        if self._first_enqueue_at is None:
            self._first_enqueue_at = now
            self.latency.note_audio_enqueued()
        self._audio_bytes_forwarded += len(chunk)
        self._media_frames_forwarded += 1

    async def _flush_pending_audio(self) -> None:
        if self._pending_audio:
            await self._enqueue_audio(self._pending_audio)
            self._pending_audio.clear()

    async def _signal_audio_end(self) -> None:
        try:
            # Ensure end sentinel fits even when queue is full.
            while self.audio_queue.full():
                try:
                    dropped = self.audio_queue.get_nowait()
                    if dropped is not _AUDIO_END:
                        self._queue_drops += 1
                        self._oldest_enqueue_at = time.perf_counter()
                except asyncio.QueueEmpty:
                    break
            await self.audio_queue.put(_AUDIO_END)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed to enqueue audio end sentinel")

    def _persist_connected(self, streamsid: str | None) -> None:
        if SessionLocal is None or self.call_context is None:
            return
        ctx = self.call_context

        def _store() -> None:
            from sqlalchemy import select

            from app.db.models import CallSession

            db = SessionLocal()
            try:
                call_lifecycle.mark_connected(db, ctx.call_sid)
                if streamsid:
                    cs = db.scalar(
                        select(CallSession).where(CallSession.call_sid == ctx.call_sid)
                    )
                    if cs is not None:
                        cs.stream_sid = streamsid
                        db.commit()
            finally:
                db.close()

        _store()

    def _persist_terminal(self) -> None:
        if SessionLocal is None or self.call_context is None:
            return
        ctx = self.call_context
        transcript = "\n".join(self.transcript)
        status = self._terminal_status
        reason = self._terminal_reason
        outcome = self._outcome

        def _store() -> None:
            db = SessionLocal()
            try:
                call_lifecycle.finalize_voice_session(
                    db,
                    call_sid=ctx.call_sid,
                    status=status,
                    terminal_reason=reason,
                    transcript=transcript,
                    outcome=outcome,
                )
            finally:
                db.close()

        _store()

    async def _resolve_start(self, data: dict) -> None:
        start = data.get("start") or {}
        streamsid = start.get("streamSid")
        if streamsid:
            # Replace any stale streamsid for reconnect-safe receiver.
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
                    break
                try:
                    data = json.loads(message)
                    event = data["event"]
                    if event == "start":
                        await self._resolve_start(data)
                    elif event == "connected":
                        continue
                    elif event == "media":
                        media = data["media"]
                        self._note_sequence(data.get("sequenceNumber") or media.get("chunk"))
                        chunk = base64.b64decode(media["payload"])
                        if media.get("track") == "inbound":
                            await self._enqueue_audio(chunk)
                    elif event == "stop":
                        await self._flush_pending_audio()
                        break
                except (KeyError, TypeError, ValueError):
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
                fields={k: v for k, v in metrics.items() if v is not None},
            )

    async def _run_deepgram_once(self, config: dict, ctx: CallContext) -> None:
        """One Deepgram agent session until Twilio ends or the socket fails."""
        async with sts_connect() as sts_ws:
            await wait_for_message_type(sts_ws, "Welcome", timeout=15)
            await sts_ws.send(json.dumps(config))
            await wait_for_message_type(sts_ws, "SettingsApplied", timeout=15)

            sender_task = asyncio.create_task(
                sts_sender(sts_ws, self.audio_queue), name="sts_sender"
            )
            receiver_task = asyncio.create_task(
                sts_receiver(
                    sts_ws,
                    self.twilio_ws,
                    self.streamsid_queue,
                    self.latency,
                    ctx=ctx,
                    transcript=self.transcript,
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

                if twilio_wait in done and self._twilio_done.is_set():
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

    async def _announce_degraded(self) -> None:
        """Best-effort brief fallback message to caller (no Deepgram)."""
        if self.streamsid_queue.empty():
            return
        try:
            streamsid = self.streamsid_queue.get_nowait()
            await self.streamsid_queue.put(streamsid)
            # Clear remote buffer; TTS announce requires provider — skip audio.
            clear_message = {"event": "clear", "streamSid": streamsid}
            await self.twilio_ws.send_text(json.dumps(clear_message))
            log_event(logger, "voice_degraded_reconnect")
        except Exception:
            logger.debug("Degraded announce skipped", exc_info=True)

    async def run(self) -> None:
        self.transcript.clear()
        request_id = new_request_id()
        log_tokens = bind_log_context(
            request_id=request_id, operation="voice_session"
        )
        session_token = _active_session.set(self)
        twilio_task = asyncio.create_task(
            self._twilio_receiver(), name="twilio_receiver"
        )
        try:
            await asyncio.wait_for(self._context_ready.wait(), timeout=30)
        except TimeoutError:
            logger.error("Timed out waiting for Twilio start / CallContext")
            self._terminal_status = call_lifecycle.STATUS_DISCONNECTED
            self._terminal_reason = "websocket:start_timeout"
            self._outcome = "failed"
            await cancel_tasks(twilio_task)
            try:
                await asyncio.to_thread(self._persist_terminal)
            except Exception:
                logger.exception("Failed to persist terminal CallSession")
            reset_log_context(log_tokens)
            _active_session.reset(session_token)
            return

        assert self.call_context is not None
        ctx = self.call_context
        log_tokens.update(
            bind_log_context(call_sid=ctx.call_sid, user_id=ctx.user_id)
        )
        config = await asyncio.to_thread(load_voice_config, ctx)

        max_attempts = max(0, int(settings.deepgram_reconnect_max_attempts))
        backoff = max(0.05, float(settings.deepgram_reconnect_backoff_seconds))
        deadline = max(1.0, float(settings.deepgram_reconnect_deadline_seconds))
        reconnect_started = time.perf_counter()
        attempts = 0

        try:
            while True:
                try:
                    await self._run_deepgram_once(config, ctx)
                    if self._twilio_done.is_set():
                        self._terminal_status = call_lifecycle.STATUS_COMPLETED
                        self._terminal_reason = "websocket:twilio_stop"
                        self._outcome = "completed"
                        break
                except DeepgramAuthError as exc:
                    logger.error("Deepgram auth failure: %s", exc)
                    self._terminal_status = call_lifecycle.STATUS_PROVIDER_ERROR
                    self._terminal_reason = "deepgram:auth"
                    self._outcome = "failed"
                    break
                except Exception as exc:
                    kind = classify_deepgram_error(exc)
                    if kind is DeepgramAuthError or not is_retryable_disconnect(exc):
                        if kind is DeepgramAuthError:
                            self._terminal_reason = "deepgram:auth"
                        else:
                            self._terminal_reason = f"deepgram:{type(exc).__name__}"
                        self._terminal_status = call_lifecycle.STATUS_PROVIDER_ERROR
                        self._outcome = "failed"
                        logger.error("Deepgram terminal failure: %s", exc)
                        break

                    attempts += 1
                    elapsed = time.perf_counter() - reconnect_started
                    if attempts > max_attempts or elapsed >= deadline:
                        logger.error(
                            "Deepgram reconnect budget exhausted attempts=%s elapsed=%.2f",
                            attempts,
                            elapsed,
                        )
                        self._terminal_status = call_lifecycle.STATUS_PROVIDER_ERROR
                        self._terminal_reason = "deepgram:reconnect_exhausted"
                        self._outcome = "failed"
                        await self._announce_degraded()
                        break

                    sleep_for = min(backoff * (2 ** (attempts - 1)), 5.0)
                    log_event(
                        logger,
                        "deepgram_reconnect",
                        attempt=attempts,
                        sleep_seconds=sleep_for,
                        error=type(exc).__name__,
                    )
                    await self._announce_degraded()
                    await asyncio.sleep(sleep_for)
                    if self._twilio_done.is_set():
                        self._terminal_status = call_lifecycle.STATUS_DISCONNECTED
                        self._terminal_reason = "websocket:twilio_during_reconnect"
                        self._outcome = "disconnected"
                        break
        finally:
            self.latency.emit_summary()
            log_event(logger, "voice_media_metrics", fields=self.media_metrics())
            await cancel_tasks(twilio_task)
            try:
                await asyncio.to_thread(self._persist_terminal)
            except Exception:
                logger.exception("Failed to persist terminal CallSession")
            self.transcript.clear()
            reset_log_context(log_tokens)
            _active_session.reset(session_token)


def estimate_legacy_buffer_latency_ms(
    frames: int = 20, frame_bytes: int = 160, sample_rate: int = 8000
) -> float:
    """Document the old 20×160 μ-law coalesce cost (~400 ms at 8 kHz)."""
    return frames * frame_bytes / sample_rate * 1000
