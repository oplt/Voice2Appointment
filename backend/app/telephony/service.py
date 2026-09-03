"""Telephony application service."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calendars.service import get_auth_record
from app.core.config import settings
from app.db.models import CallSession, User
from app.telephony.providers.twilio import TwilioProvider
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
    normalized = _normalize_phone(phone)
    if not normalized:
        return None
    users = db.scalars(
        select(User).where(User.twilio_phone_number.is_not(None))
    ).all()
    for user in users:
        if _normalize_phone(user.twilio_phone_number) == normalized:
            return user
    return None


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
) -> CallContext:
    """Resolve CallContext from a Twilio media-stream start event."""
    params = custom_parameters or {}
    user_id_raw = params.get("user_id")
    call_sid = (call_sid or params.get("call_sid") or "").strip()
    if not call_sid:
        raise ValueError("call_sid is required to resolve CallContext")

    user_id: int | None = None
    if user_id_raw:
        try:
            user_id = int(user_id_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid user_id custom parameter") from exc

    if user_id is None:
        cs = db.scalar(select(CallSession).where(CallSession.call_sid == call_sid))
        if cs is None:
            raise ValueError(f"No CallSession for call_sid={call_sid}")
        user_id = cs.user_id

    return build_call_context(db, call_sid=call_sid, user_id=user_id)


def _media_stream_wss_url() -> str:
    base = (settings.public_base_url or "").rstrip("/")
    if not base:
        raise RuntimeError("PUBLIC_BASE_URL is required for Twilio media streams")
    parsed = urlparse(base)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    host = parsed.netloc or parsed.path
    return f"{scheme}://{host}/ws/voice"


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
        CallSession.create(
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

    try:
        stream_url = _media_stream_wss_url()
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

    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response><Connect><Stream url=\"{url}\">"
        '<Parameter name="user_id" value="{user_id}"/>'
        '<Parameter name="call_sid" value="{call_sid}"/>'
        "</Stream></Connect></Response>"
    ).format(url=stream_url, user_id=user.id, call_sid=call_sid)
    return Response(content=twiml, media_type="application/xml")


def process_recording_webhook(
    db: Session,
    payload: dict[str, str],
    *,
    enqueue: bool = True,
) -> dict[str, Any]:
    """Handle Twilio recording callback.

    Looks up the user by ``User.twilio_account_sid`` (not ``account_sid``).
    Safe when the user row is missing.
    """
    account_sid = (payload.get("AccountSid") or "").strip()
    user = find_user_by_twilio_account(db, account_sid)

    if user is None:
        logger.warning(
            "Twilio recording webhook: no user for AccountSid=%s",
            account_sid or "(empty)",
        )
    elif not user.twilio_account_sid or not user.twilio_auth_token:
        logger.warning(
            "Twilio recording webhook: user id=%s missing twilio credentials",
            user.id,
        )

    # Parsing the webhook body does not need live Twilio API credentials.
    result = TwilioProvider.parse_recording_webhook(payload)
    if not result.get("ok"):
        return result

    call_sid = result["call_sid"]
    recording_sid = result["recording_sid"]
    recording_url = result["recording_url"]

    cs = db.scalar(select(CallSession).where(CallSession.call_sid == call_sid))
    if cs is not None:
        cs.recording_sid = recording_sid
        cs.recording_url = recording_url
        if user is not None and cs.user_id != user.id:
            logger.warning(
                "CallSession user_id=%s does not match AccountSid user id=%s",
                cs.user_id,
                user.id,
            )
        db.commit()

    # Only enqueue download when we have a user with credentials.
    if (
        enqueue
        and user is not None
        and user.twilio_account_sid
        and user.twilio_auth_token
    ):
        try:
            download_and_archive_recording.delay(
                recording_sid=recording_sid,
                recording_url=recording_url,
                call_sid=call_sid,
            )
        except Exception:
            logger.exception("Failed to enqueue recording download for %s", call_sid)

    return {"status": "ok", "ok": True, "enqueued": bool(user and enqueue)}
