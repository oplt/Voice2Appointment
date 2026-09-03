"""Voice session: audio queues and Deepgram/Twilio bridging."""

from __future__ import annotations

import asyncio
import base64
import copy
import json
import logging
import time
from pathlib import Path

from app.calendars.tool_schemas import AGENT_SYSTEM_PROMPT, VOICE_TOOL_DEFINITIONS
from app.calendars.tools import FUNCTION_MAP, voice_calendar_service, voice_db, voice_user_id
from app.core.logging import (
    bind_log_context,
    log_event,
    new_request_id,
    reset_log_context,
    sanitize_for_log,
)
from app.db.models import User
from app.db.session import SessionLocal
from app.telephony.service import resolve_call_context_from_start
from app.voice.context import CallContext, bind_call_context, unbind_call_context
from app.voice.dates import get_current_date_context
from app.voice.latency import LatencyTracker
from app.voice.providers.deepgram import (
    get_deepgram_settings,
    sts_connect,
    wait_for_message_type,
)

logger = logging.getLogger(__name__)

# Default Deepgram agent settings template only — not per-tenant runtime state.
_DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.json"

# Twilio μ-law 8 kHz frames are typically ~20 ms (160 bytes). Forward each frame
# immediately — do not coalesce into the old 20×160 (~400 ms) buffer.
AUDIO_QUEUE_MAXSIZE = 50
STREAMSID_QUEUE_MAXSIZE = 1
_AUDIO_END = None  # sentinel: end of inbound audio

# ContextVar-friendly holder for the active call's latency tracker.
_active_latency: LatencyTracker | None = None


def get_active_latency() -> LatencyTracker | None:
    return _active_latency


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

    # Always inject Python-owned tool schemas so LLM args match FUNCTION_MAP.
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


async def handle_function_call_request(decoded, sts_ws):
    """Run sync Google/tool work off the event loop (Phase 7.5)."""
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
                execute_function_call, func_name, arguments
            )
            latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
            if _active_latency is not None:
                if "availability" in func_name or "find_" in func_name:
                    _active_latency.record_ms("calendar_lookup_ms", latency_ms)
                elif "create_" in func_name:
                    _active_latency.record_ms("calendar_create_ms", latency_ms)
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


async def handle_text_message(decoded, twilio_ws, sts_ws, streamsid, latency: LatencyTracker):
    latency.ingest_provider_message(decoded)
    await handle_barge_in(decoded, twilio_ws, streamsid)
    if decoded["type"] == "FunctionCallRequest":
        await handle_function_call_request(decoded, sts_ws)


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
    sts_ws, twilio_ws, streamsid_queue: asyncio.Queue, latency: LatencyTracker
) -> None:
    log_event(logger, "sts_receiver_started")
    try:
        streamsid = await streamsid_queue.get()
        async for message in sts_ws:
            if isinstance(message, str):
                decoded = json.loads(message)
                msg_type = decoded.get("type", "unknown")
                # Never log full provider payloads (may include transcripts).
                log_event(logger, "deepgram_event", message_type=msg_type)
                await handle_text_message(
                    decoded, twilio_ws, sts_ws, streamsid, latency
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


class VoiceSession:
    """Coordinates Twilio media WS <-> Deepgram STS audio queues."""

    def __init__(self, twilio_ws):
        self.twilio_ws = twilio_ws
        self.audio_queue: asyncio.Queue[bytes | bytearray | None] = asyncio.Queue(
            maxsize=AUDIO_QUEUE_MAXSIZE
        )
        self.streamsid_queue: asyncio.Queue[str] = asyncio.Queue(
            maxsize=STREAMSID_QUEUE_MAXSIZE
        )
        self.call_context: CallContext | None = None
        self._context_ready = asyncio.Event()
        self._audio_bytes_forwarded = 0
        self._media_frames_forwarded = 0
        self._first_media_at: float | None = None
        self._first_enqueue_at: float | None = None
        # Residual only for trailing bytes after stop (usually empty with per-frame forward).
        self._pending_audio = bytearray()
        self.latency = LatencyTracker()

    async def _enqueue_audio(self, chunk: bytes | bytearray) -> None:
        if not chunk:
            return
        if self._first_media_at is None:
            self._first_media_at = time.perf_counter()
            self.latency.note_twilio_audio()
        # Bounded queue: await applies backpressure when Deepgram is slow.
        await self.audio_queue.put(bytes(chunk))
        if self._first_enqueue_at is None:
            self._first_enqueue_at = time.perf_counter()
            self.latency.note_audio_enqueued()
        self._audio_bytes_forwarded += len(chunk)
        self._media_frames_forwarded += 1

    async def _flush_pending_audio(self) -> None:
        """Flush any residual audio on Twilio stop (Phase 7.4)."""
        if self._pending_audio:
            await self._enqueue_audio(self._pending_audio)
            self._pending_audio.clear()

    async def _signal_audio_end(self) -> None:
        try:
            await self.audio_queue.put(_AUDIO_END)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed to enqueue audio end sentinel")

    async def _resolve_start(self, data: dict) -> None:
        start = data.get("start") or {}
        streamsid = start.get("streamSid")
        if streamsid:
            await self.streamsid_queue.put(streamsid)

        call_sid = start.get("callSid")
        custom = start.get("customParameters") or {}
        custom_params = {str(k): str(v) for k, v in custom.items()}

        if SessionLocal is None:
            raise RuntimeError("DATABASE_URL is not configured")

        def _load_context() -> CallContext:
            db = SessionLocal()
            try:
                ctx = resolve_call_context_from_start(
                    db,
                    call_sid=call_sid,
                    custom_parameters=custom_params,
                )
                if streamsid:
                    from sqlalchemy import select

                    from app.db.models import CallSession

                    cs = db.scalar(
                        select(CallSession).where(CallSession.call_sid == ctx.call_sid)
                    )
                    if cs is not None:
                        cs.stream_sid = streamsid
                        db.commit()
                return ctx
            finally:
                db.close()

        self.call_context = await asyncio.to_thread(_load_context)
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
                        chunk = base64.b64decode(media["payload"])
                        if media.get("track") == "inbound":
                            # Forward each Twilio frame immediately (no 400 ms coalesce).
                            await self._enqueue_audio(chunk)
                    elif event == "stop":
                        await self._flush_pending_audio()
                        break
                except (KeyError, TypeError, ValueError):
                    break
        finally:
            await self._flush_pending_audio()
            await self._signal_audio_end()
            if self._first_media_at and self._first_enqueue_at:
                lag_ms = (self._first_enqueue_at - self._first_media_at) * 1000
                log_event(
                    logger,
                    "voice_audio_forward_stats",
                    frames=self._media_frames_forwarded,
                    bytes=self._audio_bytes_forwarded,
                    first_enqueue_lag_ms=round(lag_ms, 2),
                )

    async def run(self) -> None:
        global _active_latency
        request_id = new_request_id()
        log_tokens = bind_log_context(
            request_id=request_id, operation="voice_session"
        )
        _active_latency = self.latency
        twilio_task = asyncio.create_task(
            self._twilio_receiver(), name="twilio_receiver"
        )
        try:
            await asyncio.wait_for(self._context_ready.wait(), timeout=30)
        except TimeoutError:
            logger.error("Timed out waiting for Twilio start / CallContext")
            await cancel_tasks(twilio_task)
            reset_log_context(log_tokens)
            _active_latency = None
            return

        assert self.call_context is not None
        ctx = self.call_context
        log_tokens.update(
            bind_log_context(call_sid=ctx.call_sid, user_id=ctx.user_id)
        )
        config = load_voice_config(ctx)

        ctx_token = bind_call_context(ctx)
        user_token = voice_user_id.set(ctx.user_id)
        db = SessionLocal() if SessionLocal is not None else None
        db_token = voice_db.set(db) if db is not None else None
        cal_token = voice_calendar_service.set(None)
        sender_task: asyncio.Task | None = None
        receiver_task: asyncio.Task | None = None
        try:
            async with sts_connect() as sts_ws:
                # Phase 8.1: Welcome → Settings → SettingsApplied → audio
                await wait_for_message_type(sts_ws, "Welcome", timeout=15)
                await sts_ws.send(json.dumps(config))
                await wait_for_message_type(sts_ws, "SettingsApplied", timeout=15)

                sender_task = asyncio.create_task(
                    sts_sender(sts_ws, self.audio_queue), name="sts_sender"
                )
                receiver_task = asyncio.create_task(
                    sts_receiver(
                        sts_ws, self.twilio_ws, self.streamsid_queue, self.latency
                    ),
                    name="sts_receiver",
                )
                # First completion (usually Twilio stop) cancels siblings.
                done, pending = await asyncio.wait(
                    {sender_task, receiver_task, twilio_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for task in done:
                    exc = task.exception() if not task.cancelled() else None
                    if exc is not None:
                        logger.error(
                            "Voice task %s failed: %s", task.get_name(), exc
                        )
        finally:
            self.latency.emit_summary()
            await cancel_tasks(
                *(t for t in (sender_task, receiver_task, twilio_task) if t)
            )
            unbind_call_context(ctx_token)
            voice_user_id.reset(user_token)
            voice_calendar_service.reset(cal_token)
            if db_token is not None:
                voice_db.reset(db_token)
            if db is not None:
                db.close()
            reset_log_context(log_tokens)
            _active_latency = None


def estimate_legacy_buffer_latency_ms(
    frames: int = 20, frame_bytes: int = 160, sample_rate: int = 8000
) -> float:
    """Document the old 20×160 μ-law coalesce cost (~400 ms at 8 kHz)."""
    return frames * frame_bytes / sample_rate * 1000
