"""FastAPI WebSocket gateway for Twilio media streams."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.logging import log_event
from app.core.metrics import metrics
from app.db.session import SessionLocal
from app.telephony.service import build_call_context
from app.telephony.stream_tokens import consume_stream_token
from app.voice.admission import admission
from app.voice.session import VoiceSession

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voice"])


@router.websocket("/ws/voice/{call_sid}/{stream_token}")
async def voice_websocket(
    websocket: WebSocket,
    call_sid: str,
    stream_token: str,
) -> None:
    """Verify path-bound stream credentials before accepting the socket."""
    call_sid = (call_sid or "").strip()
    stream_token = (stream_token or "").strip()

    if not call_sid or not stream_token or SessionLocal is None:
        await websocket.close(code=1008)
        log_event(
            logger,
            "voice_websocket_rejected",
            operation="voice_websocket",
            reason="missing_token",
        )
        return

    def _verify():
        db = SessionLocal()
        try:
            cs = consume_stream_token(db, call_sid=call_sid, raw_token=stream_token)
            return build_call_context(db, call_sid=cs.call_sid, user_id=cs.user_id)
        finally:
            db.close()

    try:
        call_context = await asyncio.to_thread(_verify)
    except ValueError as exc:
        await websocket.close(code=1008)
        log_event(
            logger,
            "voice_websocket_rejected",
            operation="voice_websocket",
            reason=type(exc).__name__,
        )
        return
    except Exception:
        logger.exception("Voice websocket auth error")
        await websocket.close(code=1011)
        return

    # Sync cap from settings (tests may monkeypatch voice_max_concurrent_calls).
    from app.core.config import settings

    admission.configure(max_concurrent=settings.voice_max_concurrent_calls)

    if not admission.try_acquire(call_context.call_sid):
        def _persist_rejection() -> None:
            from app.telephony.lifecycle import STATUS_REJECTED, finalize_voice_session

            db = SessionLocal()
            try:
                finalize_voice_session(
                    db,
                    call_sid=call_context.call_sid,
                    status=STATUS_REJECTED,
                    terminal_reason="admission:capacity",
                    outcome="rejected",
                )
            finally:
                db.close()

        try:
            await asyncio.to_thread(_persist_rejection)
        except Exception:
            logger.exception("Failed to persist voice admission rejection")
        metrics.incr("voice_admission", labels={"result": "rejected"})
        log_event(
            logger,
            "voice_admission_rejected",
            operation="voice_websocket",
            call_sid=call_context.call_sid,
            fields=admission.snapshot(),
        )
        # 1013 = Try Again Later — predictable degrade under saturation.
        await websocket.close(code=1013)
        return

    metrics.incr("voice_admission", labels={"result": "accepted"})
    await websocket.accept()
    log_event(
        logger,
        "voice_websocket_accepted",
        operation="voice_websocket",
        call_sid=call_context.call_sid,
        user_id=call_context.user_id,
    )
    session = VoiceSession(websocket, call_context=call_context)
    try:
        await session.run()
    except WebSocketDisconnect:
        log_event(logger, "voice_websocket_disconnected", operation="voice_websocket")
    except Exception:
        logger.exception("Voice websocket error")
    finally:
        admission.release(call_context.call_sid)
        try:
            await websocket.close()
        except Exception:
            pass
