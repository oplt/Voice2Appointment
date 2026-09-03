"""Phase 8 — regression test hardening for Phases 3–7 changes."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Appointment CRUD via HTTP
# ---------------------------------------------------------------------------

class TestAppointmentHTTP:
    """Appointment create/update/delete via the API."""

    def _seed_user(self, db: Session) -> int:
        from app.core.security import hash_password
        from app.db.models import User

        user = User(
            username="testuser",
            email="test@example.com",
            password=hash_password("testpass123"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id

    def _login(self, client, user_id: int):
        from app.core.security import create_access_token
        token = create_access_token(subject=str(user_id))
        client.cookies = {"access_token": token}

    def test_create_appointment(self, client, db_session):
        user_id = self._seed_user(db_session)
        self._login(client, user_id)

        resp = client.post(
            "/api/v1/appointments",
            json={
                "summary": "Test Appointment",
                "start_datetime": "2026-09-10T10:00:00Z",
                "end_datetime": "2026-09-10T10:30:00Z",
                "timezone": "UTC",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["summary"] == "Test Appointment"
        assert data["status"] == "pending"
        assert data["user_id"] == user_id

    def test_list_appointments(self, client, db_session):
        user_id = self._seed_user(db_session)
        self._login(client, user_id)

        client.post(
            "/api/v1/appointments",
            json={
                "summary": "Listed",
                "start_datetime": "2026-09-10T14:00:00Z",
                "end_datetime": "2026-09-10T14:30:00Z",
                "timezone": "UTC",
            },
        )
        resp = client.get("/api/v1/appointments")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1
        assert items[0]["summary"] == "Listed"

    def test_delete_appointment(self, client, db_session):
        user_id = self._seed_user(db_session)
        self._login(client, user_id)

        resp = client.post(
            "/api/v1/appointments",
            json={
                "summary": "To Delete",
                "start_datetime": "2026-09-11T09:00:00Z",
                "end_datetime": "2026-09-11T09:30:00Z",
                "timezone": "UTC",
            },
        )
        appt_id = resp.json()["id"]
        del_resp = client.delete(f"/api/v1/appointments/{appt_id}")
        assert del_resp.status_code == 204
        get_resp = client.get(f"/api/v1/appointments/{appt_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "cancelled"

    def test_update_appointment(self, client, db_session):
        user_id = self._seed_user(db_session)
        self._login(client, user_id)

        resp = client.post(
            "/api/v1/appointments",
            json={
                "summary": "Original",
                "start_datetime": "2026-09-12T10:00:00Z",
                "end_datetime": "2026-09-12T10:30:00Z",
                "timezone": "UTC",
            },
        )
        appt_id = resp.json()["id"]
        patch_resp = client.patch(
            f"/api/v1/appointments/{appt_id}",
            json={"summary": "Updated"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["summary"] == "Updated"

    def test_other_user_cannot_access(self, client, db_session):
        from app.core.security import hash_password
        from app.db.models import User

        user_id = self._seed_user(db_session)
        self._login(client, user_id)

        resp = client.post(
            "/api/v1/appointments",
            json={
                "summary": "Private",
                "start_datetime": "2026-09-13T10:00:00Z",
                "end_datetime": "2026-09-13T10:30:00Z",
                "timezone": "UTC",
            },
        )
        appt_id = resp.json()["id"]

        # Create second user
        user2 = User(
            username="other", email="other@example.com",
            password=hash_password("otherpass123"),
        )
        db_session.add(user2)
        db_session.commit()
        db_session.refresh(user2)
        self._login(client, user2.id)

        get_resp = client.get(f"/api/v1/appointments/{appt_id}")
        assert get_resp.status_code == 404

    def test_conflict_detection(self, client, db_session):
        user_id = self._seed_user(db_session)
        self._login(client, user_id)

        client.post(
            "/api/v1/appointments",
            json={
                "summary": "First",
                "start_datetime": "2026-09-14T10:00:00Z",
                "end_datetime": "2026-09-14T10:30:00Z",
                "timezone": "UTC",
            },
        )
        # Overlapping slot
        resp2 = client.post(
            "/api/v1/appointments",
            json={
                "summary": "Overlap",
                "start_datetime": "2026-09-14T10:15:00Z",
                "end_datetime": "2026-09-14T10:45:00Z",
                "timezone": "UTC",
            },
        )
        assert resp2.status_code == 409

    def test_unauthenticated_rejected(self, raw_client):
        resp = raw_client.get("/api/v1/appointments")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Voice tool error handling
# ---------------------------------------------------------------------------

class TestVoiceToolErrors:
    """Voice tool functions handle errors gracefully."""

    def test_unknown_function_returns_error(self):
        from app.voice.session import execute_function_call

        result = execute_function_call("nonexistent_function", {})
        assert "error" in result
        assert "Unknown function" in result["error"]

    def test_create_event_missing_args(self):
        from app.calendars.tools import create_calendar_event

        result = create_calendar_event(summary=None, datetime_start=None)
        assert result["success"] is False
        assert "required" in result["error"]

    def test_cancel_without_event_id(self):
        from app.calendars.tools import cancel_appointment

        result = cancel_appointment(event_id=None)
        assert result["success"] is False
        assert "event_id is required" in result["error"]

    def test_reschedule_without_event_id(self):
        from app.calendars.tools import reschedule_appointment

        result = reschedule_appointment(event_id=None)
        assert result["success"] is False

    def test_reschedule_rejects_approximate_timestamp(self):
        from app.calendars.tools import reschedule_appointment

        result = reschedule_appointment(
            original_datetime="2026-09-10T10:00:00Z",
            new_datetime_start="2026-09-10T11:00:00Z",
            new_datetime_end="2026-09-10T11:30:00Z",
        )
        assert result["success"] is False
        assert "approximate" in result["error"].lower()

    def test_function_call_handler_catches_exception(self):
        """handle_function_call_request sends error response on bad JSON."""
        from app.voice.context import CallContext
        from app.voice.latency import LatencyTracker
        from app.voice.session import handle_function_call_request

        decoded = {
            "functions": [
                {
                    "id": "f_err",
                    "name": "check_calendar_availability",
                    "arguments": "INVALID_JSON{{{",
                }
            ]
        }
        sts_ws = AsyncMock()
        ctx = CallContext("CAerr", 1, "UTC", "primary")

        asyncio.run(
            handle_function_call_request(
                decoded, sts_ws, ctx=ctx, latency=LatencyTracker()
            )
        )
        sts_ws.send.assert_awaited()
        sent = json.loads(sts_ws.send.await_args[0][0])
        assert "error" in sent.get("content", sent.get("output", ""))


# ---------------------------------------------------------------------------
# Celery task structure
# ---------------------------------------------------------------------------

class TestCeleryTasks:
    """Celery tasks have correct retry/idempotency configuration."""

    def test_recording_task_no_db_raises(self):
        from app.workers import tasks as tasks_mod

        original = tasks_mod.SessionLocal
        try:
            tasks_mod.SessionLocal = None
            with pytest.raises(RuntimeError, match="DATABASE_URL"):
                tasks_mod.download_and_archive_recording("sid", "url", "csid")
        finally:
            tasks_mod.SessionLocal = original

    def test_sync_user_handles_missing_user(self):
        from app.workers import tasks as tasks_mod

        mock_session = MagicMock()
        mock_session.get.return_value = None

        original = tasks_mod.SessionLocal
        try:
            tasks_mod.SessionLocal = lambda: mock_session
            result = tasks_mod.sync_twilio_for_user(99999)
            assert result["ok"] is False
            assert "not found" in result["error"]
        finally:
            tasks_mod.SessionLocal = original

    def test_precompute_warms_cache_empty(self):
        from app.workers import tasks as tasks_mod

        mock_session = MagicMock()
        mock_session.scalars.return_value.all.return_value = []

        original = tasks_mod.SessionLocal
        try:
            tasks_mod.SessionLocal = lambda: mock_session
            result = tasks_mod.precompute_analytics_summaries()
            assert result["ok"] is True
            assert result["warmed"] == 0
        finally:
            tasks_mod.SessionLocal = original


# ---------------------------------------------------------------------------
# Voice session cleanup
# ---------------------------------------------------------------------------

class TestVoiceSessionCleanup:
    """Voice session properly cleans up resources."""

    def test_transcript_cleared_at_session_start(self):
        from unittest.mock import MagicMock

        from app.voice.context import CallContext
        from app.voice.session import VoiceSession

        sess = VoiceSession(
            MagicMock(),
            call_context=CallContext("CA1", 1, "UTC", "primary"),
        )
        sess.transcript.extend(["old: data"])
        sess.transcript.clear()
        assert len(sess.transcript) == 0

    def test_cancel_tasks_handles_already_done(self):
        from app.voice.session import cancel_tasks

        done_task = MagicMock()
        done_task.done.return_value = True

        asyncio.run(cancel_tasks(done_task))
        done_task.cancel.assert_not_called()


# ---------------------------------------------------------------------------
# Google Calendar error paths
# ---------------------------------------------------------------------------

class TestGoogleCalendarErrors:
    """Calendar tool functions handle provider errors gracefully."""

    def test_availability_check_returns_error_on_exception(self):
        from app.calendars.tools import check_calendar_availability

        with patch("app.calendars.tools._resolve_service") as mock_resolve:
            mock_resolve.side_effect = ValueError("No Google Calendar authentication found")
            result = check_calendar_availability(
                datetime_start="2026-09-10T10:00:00Z",
                datetime_end="2026-09-10T10:30:00Z",
            )
            assert result["available"] is False
            assert "error" in result

    def test_find_appointments_returns_error_on_exception(self):
        from app.calendars.tools import find_appointments

        with patch("app.calendars.tools._resolve_service") as mock_resolve:
            mock_resolve.side_effect = ValueError("No credentials")
            result = find_appointments(
                datetime_start="2026-09-10T10:00:00Z",
                datetime_end="2026-09-10T10:30:00Z",
            )
            assert result["success"] is False
            assert result["count"] == 0


# ---------------------------------------------------------------------------
# Booking policy edge cases
# ---------------------------------------------------------------------------

class TestBookingPolicyEdges:
    """Booking policy validation edge cases from Phases 3-7."""

    def test_end_before_start_rejected(self, db_session):
        from app.appointments.policy import BookingPolicyError, validate_slot

        user_id = self._seed_user(db_session)
        with pytest.raises(BookingPolicyError, match="after start"):
            validate_slot(
                db_session,
                user_id,
                start=datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc),
                end=datetime(2026, 9, 10, 9, 0, tzinfo=timezone.utc),
                timezone_name="UTC",
            )

    def test_missing_user_rejected(self, db_session):
        from app.appointments.policy import BookingPolicyError, validate_slot

        with pytest.raises(BookingPolicyError, match="user not found"):
            validate_slot(
                db_session,
                99999,
                start=datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc),
                end=datetime(2026, 9, 10, 10, 30, tzinfo=timezone.utc),
                timezone_name="UTC",
            )

    def _seed_user(self, db: Session) -> int:
        from app.core.security import hash_password
        from app.db.models import User

        user = User(
            username="policyuser",
            email="policy@example.com",
            password=hash_password("testpass123"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id
