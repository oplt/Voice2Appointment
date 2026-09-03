"""PHASE 5 database correctness tests (tasks.txt)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, inspect

from app.appointments import service as appointments_service
from app.appointments.idempotency import build_appointment_idempotency_key
from app.core.security import hash_password
from app.db.models import Appointment, CallSession, GoogleCalendarAuth, User


def test_models_use_timezone_aware_datetimes() -> None:
    for column_name in ("start_datetime", "end_datetime", "created_at", "updated_at"):
        col = Appointment.__table__.c[column_name]
        assert isinstance(col.type, DateTime)
        assert col.type.timezone is True

    assert CallSession.__table__.c.recording_downloaded_at.type.timezone is True
    assert GoogleCalendarAuth.__table__.c.embedded_link.name == "embedded_link"


def test_appointment_indexes_declared() -> None:
    names = {idx.name for idx in Appointment.__table__.indexes}
    assert "ix_appointment_user_start" in names
    assert "ix_appointment_user_status_start" in names
    assert any("google_calendar_event_id" in (idx.name or "") for idx in Appointment.__table__.indexes)


def test_idempotency_key_stable() -> None:
    start = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)
    a = build_appointment_idempotency_key(
        user_id=1,
        calendar_id="primary",
        start_utc=start,
        end_utc=end,
        summary="  Dental  Check ",
        call_sid="CAabc",
    )
    b = build_appointment_idempotency_key(
        user_id=1,
        calendar_id="primary",
        start_utc=start,
        end_utc=end,
        summary="dental check",
        call_sid="CAabc",
    )
    assert a == b
    assert len(a) == 64


def test_create_appointment_idempotent(db_session) -> None:
    user = User(
        username="idemuser",
        email="idem@example.com",
        password=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    start = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)
    first = appointments_service.create_appointment(
        db_session,
        user.id,
        summary="Consult",
        start_datetime=start,
        end_datetime=end,
        timezone="Europe/Brussels",
        call_sid="CAidem",
    )
    second = appointments_service.create_appointment(
        db_session,
        user.id,
        summary="consult",
        start_datetime=start,
        end_datetime=end,
        timezone="Europe/Brussels",
        call_sid="CAidem",
    )
    assert first.id == second.id
    assert first.idempotency_key == second.idempotency_key
    count = db_session.query(Appointment).filter_by(user_id=user.id).count()
    assert count == 1


def test_schema_has_recording_and_analytics(db_engine) -> None:
    inspector = inspect(db_engine)
    call_cols = {c["name"] for c in inspector.get_columns("callsession")}
    assert "recording_path" in call_cols
    assert "recording_downloaded_at" in call_cols
    assert "twilio_call_analytics" in inspector.get_table_names()
    gcal_cols = {c["name"] for c in inspector.get_columns("google_calendar_auth")}
    assert "embedded_link" in gcal_cols
    assert "embeded_link" not in gcal_cols
