"""Telephony HTTP routes (Twilio webhooks)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.thread_db import to_thread_db
from app.telephony import service as telephony_service
from app.telephony.security import validate_twilio_signature, webhook_public_url

router = APIRouter(prefix="/telephony", tags=["telephony"])


async def _form_payload(request: Request, **fields: str | None) -> dict[str, str]:
    form = await request.form()
    payload = {k: str(v) for k, v in form.items()}
    for key, value in fields.items():
        if value:
            payload.setdefault(key, value)
    return payload


def _twilio_auth_parts(request: Request) -> tuple[str, str | None]:
    signature = request.headers.get("X-Twilio-Signature") or request.headers.get(
        "x-twilio-signature"
    )
    return webhook_public_url(request), signature


def _voice_work(
    db: Session, payload: dict[str, str], *, url: str, signature: str | None
) -> Response:
    validate_twilio_signature(db, url=url, signature=signature, form=payload)
    return telephony_service.process_inbound_voice(db, payload)


def _status_work(
    db: Session, payload: dict[str, str], *, url: str, signature: str | None
) -> dict[str, Any]:
    validate_twilio_signature(db, url=url, signature=signature, form=payload)
    return telephony_service.process_status_callback(db, payload)


def _recording_work(
    db: Session, payload: dict[str, str], *, url: str, signature: str | None
) -> dict[str, Any]:
    validate_twilio_signature(db, url=url, signature=signature, form=payload)
    return telephony_service.process_recording_webhook(db, payload)


def _transfer_work(
    db: Session, payload: dict[str, str], *, url: str, signature: str | None
) -> Response:
    from app.telephony.transfer import record_transfer_dial_status

    validate_twilio_signature(db, url=url, signature=signature, form=payload)
    record_transfer_dial_status(
        db,
        call_sid=str(payload.get("CallSid") or ""),
        dial_call_status=payload.get("DialCallStatus"),
    )
    status = (payload.get("DialCallStatus") or "").lower()
    if status in {"busy", "no-answer", "failed", "canceled"}:
        xml = (
            "<Response><Say>Sorry, no one is available right now. "
            "Please try again later.</Say><Hangup/></Response>"
        )
    else:
        xml = "<Response><Hangup/></Response>"
    return Response(content=xml, media_type="application/xml")


@router.post("/twilio/voice")
async def twilio_inbound_voice(
    request: Request,
    CallSid: str | None = Form(None),
    AccountSid: str | None = Form(None),
    To: str | None = Form(None),
    From: str | None = Form(None),
) -> Response:
    payload = await _form_payload(
        request,
        CallSid=CallSid,
        AccountSid=AccountSid,
        To=To,
        From=From,
    )
    url, signature = _twilio_auth_parts(request)
    return await to_thread_db(_voice_work, payload, url=url, signature=signature)


@router.post("/twilio/status")
async def twilio_status(
    request: Request,
    CallSid: str | None = Form(None),
    CallStatus: str | None = Form(None),
    CallDuration: str | None = Form(None),
    AccountSid: str | None = Form(None),
) -> dict:
    payload = await _form_payload(
        request,
        CallSid=CallSid,
        CallStatus=CallStatus,
        CallDuration=CallDuration,
        AccountSid=AccountSid,
    )
    url, signature = _twilio_auth_parts(request)
    return await to_thread_db(_status_work, payload, url=url, signature=signature)


@router.post("/twilio/recording")
async def twilio_recording(
    request: Request,
    AccountSid: str | None = Form(None),
    CallSid: str | None = Form(None),
    RecordingSid: str | None = Form(None),
    RecordingUrl: str | None = Form(None),
) -> dict:
    payload = await _form_payload(
        request,
        AccountSid=AccountSid,
        CallSid=CallSid,
        RecordingSid=RecordingSid,
        RecordingUrl=RecordingUrl,
    )
    url, signature = _twilio_auth_parts(request)
    return await to_thread_db(_recording_work, payload, url=url, signature=signature)


@router.post("/transfer-status")
async def transfer_dial_status(
    request: Request,
    CallSid: str | None = Form(None),
    DialCallStatus: str | None = Form(None),
    AccountSid: str | None = Form(None),
) -> Response:
    """Twilio Dial action callback — records answered/busy/no-answer/failed."""
    payload = await _form_payload(
        request,
        CallSid=CallSid,
        DialCallStatus=DialCallStatus,
        AccountSid=AccountSid,
    )
    url, signature = _twilio_auth_parts(request)
    return await to_thread_db(_transfer_work, payload, url=url, signature=signature)
