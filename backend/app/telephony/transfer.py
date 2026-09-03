"""Human handoff / Twilio call transfer (P6-03)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from xml.sax.saxutils import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CallSession, User
from app.telephony.phones import canonical_e164
from app.users.product_prefs import load_product_prefs

logger = logging.getLogger(__name__)


def build_redacted_handoff_summary(
    *,
    reason: str | None,
    call_sid: str,
    from_number: str | None,
) -> dict[str, Any]:
    """Structured summary for operators — never includes transcript or secrets."""
    category = (reason or "caller_request").strip().lower()[:64] or "caller_request"
    masked_from = None
    if from_number:
        digits = "".join(ch for ch in from_number if ch.isdigit())
        masked_from = f"***{digits[-4:]}" if len(digits) >= 4 else "***"
    return {
        "reason_category": category,
        "call_sid_suffix": call_sid[-6:] if call_sid else None,
        "from_masked": masked_from,
        "note": "Full transcript is not forwarded.",
    }


def transfer_allowed_now(
    user: User,
    *,
    db: Session | None = None,
    now: datetime | None = None,
) -> tuple[bool, str]:
    prefs = load_product_prefs(user.config_json).transfer
    if not prefs.enabled:
        return False, "transfer_disabled"
    if not prefs.destination_e164:
        return False, "no_destination"
    if canonical_e164(prefs.destination_e164) is None:
        return False, "invalid_destination"
    if prefs.business_hours_only:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        from app.appointments.policy import load_booking_policy
        from app.calendars.service import get_auth_record
        from app.core.config import settings

        policy = load_booking_policy(user.config_json)
        if policy.business_hours and db is not None:
            auth = get_auth_record(db, user.id)
            tz_name = (
                (auth.time_zone if auth and auth.time_zone else None)
                or settings.default_timezone
                or "UTC"
            )
            try:
                zone = ZoneInfo(tz_name)
            except ZoneInfoNotFoundError:
                zone = ZoneInfo("UTC")
            local = (now or datetime.now(timezone.utc)).astimezone(zone)
            day = local.strftime("%A").lower()
            windows = policy.business_hours.get(day) or []
            if not windows:
                return False, "outside_business_hours"
            t = local.time().isoformat(timespec="minutes")
            ok = any(w.start <= t < w.end for w in windows)
            if not ok:
                return False, "outside_business_hours"
    return True, "ok"


def execute_twilio_transfer(
    db: Session,
    *,
    user: User,
    call_sid: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Redirect live call to configured destination once."""
    allowed, code = transfer_allowed_now(user, db=db)
    if not allowed:
        return {"success": False, "error": code}

    cs = db.scalar(
        select(CallSession).where(
            CallSession.call_sid == call_sid,
            CallSession.user_id == user.id,
        )
    )
    if cs is None:
        return {"success": False, "error": "call_not_found"}
    if cs.transfer_attempted_at is not None:
        return {"success": False, "error": "transfer_already_attempted"}

    prefs = load_product_prefs(user.config_json).transfer
    dest = prefs.destination_e164
    assert dest is not None

    account_sid = user.twilio_account_sid
    auth_token = user.twilio_auth_token
    if not account_sid or not auth_token:
        return {"success": False, "error": "twilio_not_configured"}

    summary = build_redacted_handoff_summary(
        reason=reason, call_sid=call_sid, from_number=cs.from_number
    )
    say = f"Connecting you to a team member. Reason: {summary['reason_category']}."
    twiml = (
        f"<Response><Say>{escape(say)}</Say>"
        f"<Dial>{escape(dest)}</Dial></Response>"
    )

    cs.transfer_attempted_at = datetime.now(timezone.utc)
    db.add(cs)
    db.commit()

    try:
        from app.telephony.providers.twilio import TwilioProvider

        provider = TwilioProvider(account_sid=account_sid, auth_token=auth_token)
        provider._client.calls(call_sid).update(twiml=twiml)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "transfer_failed call_sid_suffix=%s err=%s",
            call_sid[-6:],
            type(exc).__name__,
        )
        cs.outcome = "transfer_failed"
        cs.terminal_reason = f"transfer:{type(exc).__name__}"[:64]
        db.add(cs)
        db.commit()
        return {
            "success": False,
            "error": "provider_failure",
            "fallback": "continue_with_assistant",
            "summary": summary,
        }

    cs.outcome = "transferred"
    cs.terminal_reason = "transfer:dial"
    db.add(cs)
    db.commit()
    return {
        "success": True,
        "destination_masked": f"***{dest[-4:]}",
        "summary": summary,
    }
