"""Telephony HTTP routes (Twilio webhooks)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.deps import require_db
from app.telephony import service as telephony_service
from app.telephony.security import validate_twilio_request

router = APIRouter(prefix="/telephony", tags=["telephony"])


async def _form_payload(request: Request, **fields: str | None) -> dict[str, str]:
    form = await request.form()
    payload = {k: str(v) for k, v in form.items()}
    for key, value in fields.items():
        if value:
            payload.setdefault(key, value)
    return payload


@router.post("/twilio/voice")
async def twilio_inbound_voice(
    request: Request,
    db: Session = Depends(require_db),
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
    validate_twilio_request(db, request, payload)
    return telephony_service.process_inbound_voice(db, payload)


@router.post("/twilio/status")
async def twilio_status(
    request: Request,
    db: Session = Depends(require_db),
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
    validate_twilio_request(db, request, payload)
    return telephony_service.process_status_callback(db, payload)


@router.post("/twilio/recording")
async def twilio_recording(
    request: Request,
    db: Session = Depends(require_db),
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
    validate_twilio_request(db, request, payload)
    return telephony_service.process_recording_webhook(db, payload)


@router.post("/transfer-status")
async def transfer_dial_status(
    request: Request,
    db: Session = Depends(require_db),
    CallSid: str | None = Form(None),
    DialCallStatus: str | None = Form(None),
    AccountSid: str | None = Form(None),
) -> Response:
    """Twilio Dial action callback — records answered/busy/no-answer/failed."""
    from app.telephony.transfer import record_transfer_dial_status

    payload = await _form_payload(
        request,
        CallSid=CallSid,
        DialCallStatus=DialCallStatus,
        AccountSid=AccountSid,
    )
    validate_twilio_request(db, request, payload)
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
