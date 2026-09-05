"""Telephony application service."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

from app.calendars.service import get_auth_record
from app.core.config import settings
from app.db.models import CallSession, User
from app.telephony.providers.twilio import TwilioProvider
from app.telephony.security import assert_valid_twilio_sid, twilio_recording_api_url
from app.telephony.stream_tokens import get_or_issue_stream_token
from app.voice.context import CallContext
from app.workers.tasks import download_and_archive_recording

logger = logging.getLogger(__name__)


def _normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"[\s\-()]", "", value.strip())
    return cleaned or None


def find_user_by_twilio_account(db: Session, account_sid: str) -> User | None:
    if not account_sid:
        return None
    return db.scalar(select(User).where(User.twilio_account_sid == account_sid))


def find_user_by_twilio_phone(db: Session, phone: str | None) -> User | None:
    from app.telephony.phones import canonical_e164

    e164 = canonical_e164(phone)
    if not e164:
        return None
    return db.scalar(select(User).where(User.twilio_phone_e164 == e164))


def resolve_inbound_user(
    db: Session,
    *,
    to_number: str | None,
    account_sid: str | None,
) -> User | None:
    """Resolve tenant for an inbound Twilio call. Never falls back to 'first user'."""
    user = find_user_by_twilio_phone(db, to_number)
    if user is not None:
        return user
    return find_user_by_twilio_account(db, account_sid or "")


def build_call_context(db: Session, *, call_sid: str, user_id: int) -> CallContext:
    auth = get_auth_record(db, user_id)
    timezone = (
        (auth.time_zone if auth and auth.time_zone else None)
        or settings.default_timezone
        or "UTC"
    )
    calendar_id = (
        (auth.calendar_id if auth and auth.calendar_id else None) or "primary"
    )
    return CallContext(
        call_sid=call_sid,
        user_id=user_id,
        timezone=timezone,
        calendar_id=calendar_id,
    )


def resolve_call_context_from_start(
    db: Session,
    *,
    call_sid: str | None,
    custom_parameters: dict[str, str] | None = None,
    stream_token: str | None = None,
) -> CallContext:
    """Resolve CallContext from a verified media-stream start.

    Caller-supplied ``user_id`` is ignored. Ownership comes only from CallSession
    after a valid single-use ``stream_token``.
    """
    from app.telephony.stream_tokens import consume_stream_token

    params = custom_parameters or {}
    call_sid = (call_sid or params.get("call_sid") or "").strip()
    token = (stream_token or params.get("stream_token") or "").strip()
    if not call_sid:
        raise ValueError("call_sid is required to resolve CallContext")
    if not token:
        raise ValueError("stream_token is required")

    cs = consume_stream_token(db, call_sid=call_sid, raw_token=token)
    return build_call_context(db, call_sid=cs.call_sid, user_id=cs.user_id)


def _media_stream_wss_url(*, call_sid: str, stream_token: str) -> str:
    base = (settings.public_base_url or "").rstrip("/")
    if not base:
        raise RuntimeError("PUBLIC_BASE_URL is required for Twilio media streams")
    parsed = urlparse(base)
    if settings.is_production and parsed.scheme != "https":
        raise RuntimeError("PUBLIC_BASE_URL must be https for Twilio media streams")
    scheme = "wss" if parsed.scheme == "https" else "ws"
    host = parsed.netloc or parsed.path
    from urllib.parse import quote

    return (
        f"{scheme}://{host}/ws/voice/"
        f"{quote(call_sid, safe='')}/{quote(stream_token, safe='')}"
    )


def process_inbound_voice(
    db: Session,
    payload: dict[str, str],
) -> Response:
    """Create a tenant-scoped CallSession and return TwiML that connects the media stream."""
    call_sid = (payload.get("CallSid") or "").strip()
    account_sid = (payload.get("AccountSid") or "").strip()
    to_number = payload.get("To")
    from_number = payload.get("From")

    if not call_sid:
        return Response(
            content="<?xml version='1.0' encoding='UTF-8'?><Response><Say>Missing call identifier.</Say><Hangup/></Response>",
            media_type="application/xml",
            status_code=400,
        )

    user = resolve_inbound_user(db, to_number=to_number, account_sid=account_sid)
    if user is None:
        logger.warning(
            "Inbound voice: no user for To=%s AccountSid=%s",
            to_number,
            account_sid or "(empty)",
        )
        return Response(
            content=(
                "<?xml version='1.0' encoding='UTF-8'?>"
                "<Response><Say>This number is not configured.</Say><Hangup/></Response>"
            ),
            media_type="application/xml",
            status_code=200,
        )

    existing = db.scalar(select(CallSession).where(CallSession.call_sid == call_sid))
    if existing is None:
        existing = CallSession.create(
            call_sid=call_sid,
            from_number=from_number,
            to_number=to_number,
            user_id=user.id,
            data={"AccountSid": account_sid},
            session=db,
        )
    elif existing.user_id != user.id:
        logger.warning(
            "Inbound voice: CallSession %s user_id=%s != resolved user=%s",
            call_sid,
            existing.user_id,
            user.id,
        )
        return Response(
            content=(
                "<?xml version='1.0' encoding='UTF-8'?>"
                "<Response><Say>Call ownership mismatch.</Say><Hangup/></Response>"
            ),
            media_type="application/xml",
            status_code=200,
        )

    try:
        stream_token = get_or_issue_stream_token(db, existing)
    except ValueError:
        response = VoiceResponse()
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    try:
        stream_url = _media_stream_wss_url(call_sid=call_sid, stream_token=stream_token)
    except RuntimeError as exc:
        logger.error("%s", exc)
        return Response(
            content=(
                "<?xml version='1.0' encoding='UTF-8'?>"
                "<Response><Say>Service misconfigured.</Say><Hangup/></Response>"
            ),
            media_type="application/xml",
            status_code=500,
        )

    # Do not put user_id/token in custom parameters — ownership is path-token-bound.
    # statusCallback on <Connect> is not supported; configure the Twilio number's
    # Status Callback URL to PUBLIC_BASE_URL/api/v1/telephony/twilio/status.
    voice_response = VoiceResponse()
    connect = Connect()
    stream = Stream(url=stream_url)
    stream.parameter(name="call_sid", value=call_sid)
    connect.append(stream)
    voice_response.append(connect)
    return Response(content=str(voice_response), media_type="application/xml")


def process_status_callback(
    db: Session,
    payload: dict[str, str],
) -> dict[str, Any]:
    """Apply signed Twilio call-status updates to CallSession (P2-01)."""
    from app.telephony.lifecycle import apply_twilio_status_callback

    account_sid = (payload.get("AccountSid") or "").strip()
    user = find_user_by_twilio_account(db, account_sid)
    if user is None:
        # Keep the response deliberately neutral: callers cannot use this
        # endpoint to discover account or call ownership.
        logger.warning("Twilio status webhook: unknown AccountSid")
        return {"ok": False, "error": "unknown call"}
    return apply_twilio_status_callback(db, payload, user_id=user.id)


def process_recording_webhook(
    db: Session,
    payload: dict[str, str],
    *,
    enqueue: bool = True,
) -> dict[str, Any]:
    """Handle Twilio recording callback after signature validation.

    Reconstructs the Twilio API URL from verified SIDs; rejects ownership mismatch.
    """
    account_sid = (payload.get("AccountSid") or "").strip()
    user = find_user_by_twilio_account(db, account_sid)

    if user is None:
        logger.warning(
            "Twilio recording webhook: no user for AccountSid=%s",
            account_sid or "(empty)",
        )
        return {"status": "forbidden", "ok": False, "enqueued": False}

    if not user.twilio_account_sid or not user.twilio_auth_token:
        logger.warning(
            "Twilio recording webhook: user id=%s missing twilio credentials",
            user.id,
        )
        return {"status": "forbidden", "ok": False, "enqueued": False}

    result = TwilioProvider.parse_recording_webhook(payload)
    if not result.get("ok"):
        return result

    try:
        call_sid = assert_valid_twilio_sid(result["call_sid"], prefix="CA")
        recording_sid = assert_valid_twilio_sid(result["recording_sid"], prefix="RE")
        account_sid = assert_valid_twilio_sid(account_sid, prefix="AC")
    except ValueError:
        return {"status": "invalid sid", "ok": False, "enqueued": False}

    # Never fetch the webhook-supplied host; rebuild from SIDs.
    recording_url = twilio_recording_api_url(
        account_sid=account_sid, recording_sid=recording_sid
    )

    cs = db.scalar(select(CallSession).where(CallSession.call_sid == call_sid))
    if cs is None:
        return {"status": "unknown call", "ok": False, "enqueued": False}
    if cs.user_id != user.id:
        logger.warning(
            "Recording webhook ownership mismatch call_sid=%s cs.user=%s account.user=%s",
            call_sid,
            cs.user_id,
            user.id,
        )
        return {"status": "forbidden", "ok": False, "enqueued": False}

    # Idempotent: same recording_sid already stored → no re-enqueue side effect.
    already = cs.recording_sid == recording_sid and cs.recording_url == recording_url
    cs.recording_sid = recording_sid
    cs.recording_url = recording_url
    db.commit()

    if enqueue and not already:
        try:
            download_and_archive_recording.delay(
                recording_sid=recording_sid,
                recording_url=recording_url,
                call_sid=call_sid,
                account_sid=account_sid,
                user_id=user.id,
            )
        except Exception:
            logger.exception("Failed to enqueue recording download for %s", call_sid)
            return {"status": "ok", "ok": True, "enqueued": False}

    return {"status": "ok", "ok": True, "enqueued": bool(enqueue and not already)}
