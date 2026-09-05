"""Setup readiness checklist derived from live config (P6-04)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.appointments.policy import load_booking_policy
from app.calendars.service import calendar_status
from app.core.config import settings
from app.db.models import User
from app.users.product_prefs import load_product_prefs


def compute_readiness(db: Session, user: User) -> dict[str, Any]:
    cal = calendar_status(db, user.id)
    policy = load_booking_policy(user.config_json)
    product = load_product_prefs(user.config_json)

    items: list[dict[str, Any]] = []

    def add(
        key: str,
        label: str,
        ok: bool,
        *,
        fix_path: str,
        detail: str,
        required: bool = True,
    ) -> None:
        items.append(
            {
                "key": key,
                "label": label,
                "ok": ok,
                "required": required,
                "fix_path": fix_path,
                "detail": detail,
            }
        )

    add(
        "account",
        "Account email",
        bool(user.email),
        fix_path="/settings",
        detail="Sign-in email is set." if user.email else "Add an account email.",
    )
    add(
        "calendar",
        "Google Calendar connected",
        bool(cal.get("connected")),
        fix_path="/settings#calendar",
        detail=(
            f"Connected as {cal.get('account_email')}"
            if cal.get("connected")
            else "Connect Google Calendar via OAuth."
        ),
    )
    add(
        "timezone",
        "Timezone selected",
        bool(cal.get("time_zone")),
        fix_path="/settings#calendar",
        detail=cal.get("time_zone") or "Set a calendar timezone after connecting.",
    )
    named_services = {
        k: v
        for k, v in (policy.service_durations_minutes or {}).items()
        if k.strip() and k.strip().casefold() != "default"
    }
    add(
        "services",
        "Named service durations",
        bool(named_services),
        fix_path="/settings#booking",
        detail=(
            f"{len(named_services)} service(s) configured."
            if named_services
            else "Add at least one named service duration (not only the default)."
        ),
    )
    add(
        "business_hours",
        "Business hours",
        bool(policy.business_hours),
        fix_path="/settings#booking",
        detail=(
            "Business hours configured."
            if policy.business_hours
            else "Configure business hours for booking and transfer schedules."
        ),
        required=False,
    )
    twilio_sid = bool(user.twilio_account_sid and user.twilio_auth_token)
    add(
        "telephony",
        "Twilio credentials stored",
        twilio_sid,
        fix_path="/settings#telephony",
        detail=(
            "Twilio SID/token present — verify with a test call before production."
            if twilio_sid
            else "Add Twilio Account SID and Auth Token."
        ),
    )
    add(
        "phone_route",
        "Inbound phone number",
        bool(user.twilio_phone_number or user.twilio_phone_e164),
        fix_path="/settings#telephony",
        detail=(
            user.twilio_phone_e164
            or user.twilio_phone_number
            or "Set the Twilio phone number that routes here."
        ),
    )
    add(
        "test_call",
        "Safe test call",
        bool(user.twilio_last_synced_at),
        fix_path="/settings#telephony",
        detail=(
            "A recent telephony sync/activity was recorded."
            if user.twilio_last_synced_at
            else "Place a non-production test call after credentials are set."
        ),
        required=False,
    )
    add(
        "deepgram",
        "Speech platform credential",
        bool((settings.deepgram_api_key or "").strip()),
        fix_path="/settings#voice",
        detail=(
            "Platform Deepgram key is configured."
            if (settings.deepgram_api_key or "").strip()
            else "Ask an admin to set DEEPGRAM_API_KEY."
        ),
    )
    add(
        "notifications",
        "Notification consent (optional)",
        bool(product.notifications.consent_at),
        fix_path="/settings#notifications",
        detail=(
            "Confirmations/reminders consent recorded."
            if product.notifications.consent_at
            else "Enable email notifications when ready."
        ),
        required=False,
    )
    add(
        "retention",
        "Retention policy",
        product.retention.transcript_days >= 1,
        fix_path="/settings#privacy",
        detail=(
            f"Transcripts {product.retention.transcript_days}d, "
            f"recordings {product.retention.recording_days}d"
            + (" (legal hold)" if product.retention.legal_hold else "")
        ),
    )

    required = [i for i in items if i["required"]]
    ready = all(i["ok"] for i in required)
    return {
        "ready": ready,
        "items": items,
        "completed_required": sum(1 for i in required if i["ok"]),
        "total_required": len(required),
        "test_call_hint": (
            "Place a non-production test call to your Twilio number after readiness. "
            "Do not book real client appointments during verification."
        ),
    }
