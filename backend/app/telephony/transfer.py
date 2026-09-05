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

_FALLBACK_TWIML = (
    "<Response><Say>We are sorry, the appointment assistant is unavailable. "
    "Please call back shortly.</Say><Hangup/></Response>"
)


_ALLOWED_HANDOFF_REASONS = frozenset(
    {
        "caller_request",
        "complex_request",
        "billing",
        "complaint",
        "provider_unavailable",
        "emergency",
        "other",
    }
)


def build_redacted_handoff_summary(
    *,
    reason: str | None,
    call_sid: str,
    from_number: str | None,
) -> dict[str, Any]:
    """Structured summary for operators — never includes transcript or secrets."""
    raw = (reason or "caller_request").strip().lower().replace(" ", "_")[:64]
    category = raw if raw in _ALLOWED_HANDOFF_REASONS else "other"
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
    dest = canonical_e164(prefs.destination_e164)
    if dest is None:
        return False, "invalid_destination"
    inbound = canonical_e164(user.twilio_phone_e164 or user.twilio_phone_number)
    if inbound and dest == inbound:
        return False, "loop_to_inbound"
    if prefs.business_hours_only:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        from app.appointments.policy import load_booking_policy
        from app.calendars.service import get_auth_record
        from app.core.config import settings

        if db is None:
            return False, "schedule_unavailable"
        policy = load_booking_policy(user.config_json)
        if not policy.business_hours:
            # Fail closed: business_hours_only with no schedule is unavailable.
            return False, "no_business_hours"
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
    """Redirect live call to configured destination once (atomic claim)."""
    allowed, code = transfer_allowed_now(user, db=db)
    if not allowed:
        return {"success": False, "error": code}

    cs = db.scalar(
        select(CallSession)
        .where(
            CallSession.call_sid == call_sid,
            CallSession.user_id == user.id,
        )
        .with_for_update()
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
    # Whisper/context channel: short allowlisted Say before Dial (no transcript/PII).
    say = (
        f"Connecting you to a team member. "
        f"Reason category: {summary['reason_category']}."
    )
    action_url = f"{settings_public_base()}/api/v1/telephony/transfer-status"
    twiml = (
        f"<Response><Say>{escape(say)}</Say>"
        f'<Dial action="{escape(action_url)}" method="POST">'
        f"{escape(dest)}</Dial></Response>"
    )

    # Atomic claim before provider call.
    now = datetime.now(timezone.utc)
    cs.transfer_attempted_at = now
    cs.outcome = "transfer_attempted"
    cs.terminal_reason = "transfer:claimed"
    data = dict(cs.data or {})
    data["transfer"] = {
        "status": "attempted",
        "reason_category": summary["reason_category"],
        "claimed_at": now.isoformat(),
    }
    cs.data = data
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
        data = dict(cs.data or {})
        data["transfer"] = {**(data.get("transfer") or {}), "status": "failed"}
        cs.data = data
        db.add(cs)
        db.commit()
        return {
            "success": False,
            "error": "provider_failure",
            "fallback": "continue_with_assistant",
            "summary": summary,
        }

    # Outcome stays transfer_attempted until Dial status callback confirms.
    return {
        "success": True,
        "destination_masked": f"***{dest[-4:]}",
        "summary": summary,
        "status": "attempted",
    }


def settings_public_base() -> str:
    from app.core.config import settings

    return (settings.public_base_url or "http://localhost:8000").rstrip("/")


def record_transfer_dial_status(
    db: Session,
    *,
    call_sid: str,
    dial_call_status: str | None,
) -> dict[str, Any]:
    """Map Twilio Dial action callback status to durable call outcome."""
    cs = db.scalar(
        select(CallSession)
        .where(CallSession.call_sid == call_sid)
        .with_for_update()
    )
    if cs is None:
        return {"ok": False, "error": "call_not_found"}
    status = (dial_call_status or "").strip().lower()
    mapping = {
        "completed": ("transferred", "answered"),
        "answered": ("transferred", "answered"),
        "busy": ("transfer_failed", "busy"),
        "no-answer": ("transfer_failed", "no_answer"),
        "failed": ("transfer_failed", "failed"),
        "canceled": ("transfer_failed", "canceled"),
    }
    outcome, detail = mapping.get(status, ("transfer_failed", status or "unknown"))
    cs.outcome = outcome
    cs.terminal_reason = f"transfer:{detail}"[:64]
    data = dict(cs.data or {})
    data["transfer"] = {
        **(data.get("transfer") or {}),
        "status": detail,
        "dial_call_status": status,
    }
    cs.data = data
    db.add(cs)
    db.commit()
    return {"ok": True, "outcome": outcome, "status": detail}


def execute_controlled_fallback(
    db: Session,
    *,
    user: User,
    call_sid: str,
) -> dict[str, Any]:
    """Perform exactly one transfer or audible Twilio fallback for a live call."""
    cs = db.scalar(
        select(CallSession)
        .where(CallSession.call_sid == call_sid, CallSession.user_id == user.id)
        .with_for_update()
    )
    if cs is None:
        return {"success": False, "action": "unavailable", "error": "call_not_found"}
    prior = (cs.data or {}).get("provider_fallback")
    if prior in {"transfer", "announcement", "announcement_pending"}:
        return {"success": True, "action": str(prior), "idempotent": True}
    if prior == "announcement_failed":
        return {
            "success": False,
            "action": "announcement",
            "error": "provider_failure",
            "idempotent": True,
        }

    allowed, _ = transfer_allowed_now(user, db=db)
    if allowed:
        result = execute_twilio_transfer(
            db, user=user, call_sid=call_sid, reason="provider_unavailable"
        )
        if result.get("success"):
            data = dict(cs.data or {})
            data["provider_fallback"] = "transfer"
            cs.data = data
            db.add(cs)
            db.commit()
            return {"success": True, "action": "transfer"}
        return {"success": False, "action": "transfer", "error": "transfer_failed"}

    if not user.twilio_account_sid or not user.twilio_auth_token:
        return {"success": False, "action": "unavailable", "error": "twilio_not_configured"}

    # Commit the idempotency marker before the external call. A timeout may
    # leave its delivery unknown, so repeating it could speak twice.
    data = dict(cs.data or {})
    data["provider_fallback"] = "announcement_pending"
    cs.data = data
    db.add(cs)
    db.commit()
    try:
        from app.telephony.providers.twilio import TwilioProvider

        provider = TwilioProvider(
            account_sid=user.twilio_account_sid, auth_token=user.twilio_auth_token
        )
        provider._client.calls(call_sid).update(twiml=_FALLBACK_TWIML)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "provider_fallback_failed call_sid_suffix=%s err=%s",
            call_sid[-6:],
            type(exc).__name__,
        )
        data["provider_fallback"] = "announcement_failed"
        cs.data = data
        db.add(cs)
        db.commit()
        return {"success": False, "action": "announcement", "error": "provider_failure"}

    data["provider_fallback"] = "announcement"
    cs.data = data
    db.add(cs)
    db.commit()
    return {"success": True, "action": "announcement"}
