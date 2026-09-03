"""Phase 6: notifications, retention, handoff, readiness."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.appointments.booking import book_appointment, cancel_appointment
from app.core.security import create_access_token, hash_password
from app.db.models import Appointment, CallSession, NotificationDelivery, User
from app.notifications.service import (
    KIND_CONFIRMATION,
    KIND_REMINDER,
    deliver_notification,
    process_due_reminders,
)
from app.privacy import service as privacy_service
from app.telephony.transfer import build_redacted_handoff_summary, execute_twilio_transfer
from app.users.product_prefs import (
    NotificationPrefs,
    ProductPrefs,
    RetentionPrefs,
    TransferPrefs,
    grant_notification_consent,
    load_product_prefs,
    save_product_prefs,
)
from app.users.readiness import compute_readiness


def _user(db, email: str = "p6@example.com") -> User:
    user = User(
        username=email.split("@")[0][:40],
        email=email,
        password=hash_password("password123"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_alembic_head_phase6() -> None:
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = Path(__file__).resolve().parents[1] / "migrations"
    cfg = Config()
    cfg.set_main_option("script_location", str(root))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert heads == ["c9d0e1f2a3b4"]


def test_notification_idempotent_and_consent(db_session, monkeypatch) -> None:
    user = _user(db_session)
    prefs = ProductPrefs(
        notifications=grant_notification_consent(
            NotificationPrefs(confirmations_enabled=True, reminders_enabled=True)
        )
    )
    save_product_prefs(user, prefs)
    db_session.commit()

    start = datetime.now(timezone.utc) + timedelta(hours=2)
    appt = book_appointment(
        db_session,
        user.id,
        summary="Checkup",
        start_datetime=start,
        end_datetime=start + timedelta(minutes=30),
        timezone_name="UTC",
        client_email="client@example.com",
    )

    sent: list[str] = []

    def fake_send(*, to_addr: str, subject: str, body: str) -> None:
        sent.append(to_addr)

    monkeypatch.setattr("app.notifications.service._send_email", fake_send)
    r1 = deliver_notification(db_session, appt, kind=KIND_CONFIRMATION)
    r2 = deliver_notification(db_session, appt, kind=KIND_CONFIRMATION)
    assert r1["status"] == "sent"
    assert r2.get("idempotent") is True
    assert len(sent) == 1


def test_quiet_hours_skip(db_session) -> None:
    user = _user(db_session, email="quiet@example.com")
    prefs = ProductPrefs(
        notifications=grant_notification_consent(
            NotificationPrefs(
                confirmations_enabled=True,
                quiet_hours_start="00:00",
                quiet_hours_end="23:59",
            )
        )
    )
    save_product_prefs(user, prefs)
    db_session.commit()
    start = datetime.now(timezone.utc) + timedelta(hours=5)
    appt = Appointment(
        user_id=user.id,
        summary="Q",
        start_datetime=start,
        end_datetime=start + timedelta(minutes=30),
        timezone="UTC",
        status="confirmed",
        client_email="c@example.com",
    )
    db_session.add(appt)
    db_session.commit()
    result = deliver_notification(db_session, appt, kind=KIND_CONFIRMATION)
    assert result["status"] == "skipped"
    assert result["error_code"] == "quiet_hours"


def test_reminder_job_respects_lead_time(db_session, monkeypatch) -> None:
    user = _user(db_session, email="rem@example.com")
    prefs = ProductPrefs(
        notifications=grant_notification_consent(
            NotificationPrefs(reminders_enabled=True, reminder_hours_before=24)
        )
    )
    save_product_prefs(user, prefs)
    db_session.commit()
    soon = datetime.now(timezone.utc) + timedelta(hours=2)
    later = datetime.now(timezone.utc) + timedelta(days=3)
    for start, summary in ((soon, "Soon"), (later, "Later")):
        db_session.add(
            Appointment(
                user_id=user.id,
                summary=summary,
                start_datetime=start,
                end_datetime=start + timedelta(minutes=30),
                timezone="UTC",
                status="confirmed",
                client_email="c@example.com",
                reminder_sent=False,
            )
        )
    db_session.commit()
    monkeypatch.setattr("app.notifications.service._send_email", lambda **_k: None)
    out = process_due_reminders(db_session)
    assert out["sent"] >= 1
    soon_row = db_session.query(Appointment).filter_by(summary="Soon").one()
    later_row = db_session.query(Appointment).filter_by(summary="Later").one()
    assert soon_row.reminder_sent is True
    assert later_row.reminder_sent is False


def test_cancel_skips_pending_notifications(db_session) -> None:
    user = _user(db_session, email="can@example.com")
    start = datetime.now(timezone.utc) + timedelta(days=1)
    appt = book_appointment(
        db_session,
        user.id,
        summary="Cancel me",
        start_datetime=start,
        end_datetime=start + timedelta(minutes=30),
    )
    db_session.add(
        NotificationDelivery(
            user_id=user.id,
            appointment_id=appt.id,
            kind=KIND_REMINDER,
            channel="email",
            status="pending",
            idempotency_key=f"reminder:{appt.id}:x",
        )
    )
    db_session.commit()
    cancel_appointment(db_session, user.id, appointment_id=appt.id)
    row = db_session.query(NotificationDelivery).filter_by(appointment_id=appt.id).one()
    assert row.status == "skipped"


def test_retention_purge_and_legal_hold(db_session) -> None:
    user = _user(db_session, email="ret@example.com")
    save_product_prefs(
        user,
        ProductPrefs(retention=RetentionPrefs(transcript_days=1, recording_days=1)),
    )
    db_session.commit()
    old = datetime.now(timezone.utc) - timedelta(days=10)
    cs = CallSession.create(
        call_sid="CApurge",
        from_number="+1",
        to_number="+2",
        user_id=user.id,
        session=db_session,
    )
    cs.transcript = "secret words"
    cs.started_at = old
    db_session.commit()

    out = privacy_service.run_retention_purge(db_session)
    assert out["purged_calls"] >= 1
    db_session.refresh(cs)
    assert cs.transcript is None
    assert cs.content_purged_at is not None

    again = privacy_service.purge_call_content(db_session, cs)
    assert again["idempotent"] is True

    save_product_prefs(
        user,
        ProductPrefs(retention=RetentionPrefs(legal_hold=True)),
    )
    db_session.commit()
    try:
        privacy_service.delete_call_content_for_user(db_session, user.id, cs.id)
        raise AssertionError("expected PermissionError")
    except PermissionError:
        pass


def test_handoff_summary_has_no_transcript() -> None:
    summary = build_redacted_handoff_summary(
        reason="billing",
        call_sid="CAabcdefghijklmnop",
        from_number="+15551234567",
    )
    assert "transcript" not in summary
    assert summary["from_masked"] == "***4567"


def test_transfer_loop_prevention(db_session) -> None:
    user = _user(db_session, email="xfer@example.com")
    user.twilio_account_sid = "AC"
    user.twilio_auth_token = "tok"
    save_product_prefs(
        user,
        ProductPrefs(
            transfer=TransferPrefs(enabled=True, destination_e164="+15557654321")
        ),
    )
    db_session.commit()
    cs = CallSession.create(
        call_sid="CAxfer1",
        from_number="+15551112222",
        to_number="+15553334444",
        user_id=user.id,
        session=db_session,
    )
    cs.transfer_attempted_at = datetime.now(timezone.utc)
    db_session.commit()
    result = execute_twilio_transfer(
        db_session, user=user, call_sid="CAxfer1", reason="caller_request"
    )
    assert result["success"] is False
    assert result["error"] == "transfer_already_attempted"


def test_transfer_success_mocks_twilio(db_session) -> None:
    user = _user(db_session, email="xfer2@example.com")
    user.twilio_account_sid = "AC"
    user.twilio_auth_token = "tok"
    save_product_prefs(
        user,
        ProductPrefs(
            transfer=TransferPrefs(enabled=True, destination_e164="+15557654321")
        ),
    )
    db_session.commit()
    CallSession.create(
        call_sid="CAxfer2",
        from_number="+15551112222",
        to_number="+15553334444",
        user_id=user.id,
        session=db_session,
    )
    fake_client = MagicMock()
    with patch("app.telephony.providers.twilio.TwilioProvider") as FakeProv:
        FakeProv.return_value._client = fake_client
        result = execute_twilio_transfer(
            db_session, user=user, call_sid="CAxfer2", reason="caller_request"
        )
    assert result["success"] is True
    fake_client.calls.assert_called()


def test_readiness_shape(db_session, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "deepgram_api_key", "dg")
    user = _user(db_session, email="ready@example.com")
    user.twilio_account_sid = "AC"
    user.twilio_auth_token = "tok"
    user.twilio_phone_number = "+15551234567"
    db_session.commit()
    payload = compute_readiness(db_session, user)
    keys = {i["key"] for i in payload["items"]}
    assert "telephony" in keys
    assert "calendar" in keys


def test_product_prefs_api_forces_english(client, db_session) -> None:
    user = _user(db_session, email="api@example.com")
    token = create_access_token(subject=str(user.id), auth_version=0)
    client.cookies.set("access_token", token)
    body = ProductPrefs().model_dump(mode="json")
    body["languages"] = {"primary": "fr", "enabled": ["fr", "en"]}
    body["notifications"]["confirmations_enabled"] = True
    resp = client.put("/api/v1/users/me/product-prefs", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["languages"]["primary"] == "en"
    assert data["languages"]["enabled"] == ["en"]
    assert data["notifications"]["consent_at"]


def test_load_product_prefs_defaults() -> None:
    prefs = load_product_prefs(None)
    assert prefs.retention.transcript_days == 30
    assert prefs.transfer.enabled is False
