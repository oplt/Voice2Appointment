"""FastAPI WebSocket gateway for Twilio media streams."""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.logging import log_event
from app.voice.session import VoiceSession

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voice"])


@router.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    log_event(logger, "voice_websocket_accepted", operation="voice_websocket")
    session = VoiceSession(websocket)
    try:
        await session.run()
    except WebSocketDisconnect:
        log_event(logger, "voice_websocket_disconnected", operation="voice_websocket")
    except Exception:
        logger.exception("Voice websocket error")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
