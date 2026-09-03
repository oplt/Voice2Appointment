"""Phase 7 feature tests — timezone clarity, transcript storage, transcript API."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock


class TestTimezoneInConfirmation:
    """Confirmation prompts include timezone name."""

    def test_format_local_includes_timezone(self):
        from app.calendars.tools import _format_local

        dt = datetime(2026, 9, 5, 15, 30, tzinfo=timezone.utc)
        result = _format_local(dt, "Europe/Brussels")
        assert "Europe/Brussels" in result
        assert "3:30 PM" in result

    def test_format_local_no_timezone(self):
        from app.calendars.tools import _format_local

        dt = datetime(2026, 9, 5, 9, 0, tzinfo=timezone.utc)
        result = _format_local(dt)
        assert "9:00 AM" in result
        # No timezone appended when None
        assert "Europe" not in result

    def test_create_confirmation_includes_timezone(self):
        from app.calendars.tools import create_calendar_event
        from app.voice.context import CallContext, bind_call_context, unbind_call_context

        ctx = CallContext(
            call_sid="CA_test",
            user_id=1,
            timezone="Europe/Brussels",
            calendar_id="primary",
        )
        token = bind_call_context(ctx)
        try:
            result = create_calendar_event(
                summary="Test",
                datetime_start="2026-09-05T15:00:00+00:00",
                datetime_end="2026-09-05T15:30:00+00:00",
                confirmed=False,
            )
            assert result["needs_confirmation"] is True
            assert "Europe/Brussels" in result["confirmation_prompt"]
        finally:
            unbind_call_context(token)


class TestTranscriptAccumulation:
    """Voice session accumulates transcript from ConversationText events."""

    def test_conversation_text_appended(self):
        import asyncio
        from unittest.mock import AsyncMock

        import app.voice.session as mod
        from app.voice.context import CallContext
        from app.voice.latency import LatencyTracker

        transcript: list[str] = []
        ctx = CallContext("CA1", 1, "UTC", "primary")
        decoded = {
            "type": "ConversationText",
            "role": "user",
            "content": "Book a meeting tomorrow at 3",
        }
        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock()
        mock_sts_ws = MagicMock()
        latency = LatencyTracker()

        asyncio.run(
            mod.handle_text_message(
                decoded,
                mock_ws,
                mock_sts_ws,
                "stream1",
                latency,
                ctx=ctx,
                transcript=transcript,
            )
        )
        assert "user: Book a meeting tomorrow at 3" in transcript

    def test_get_call_transcript_joins(self):
        from unittest.mock import MagicMock

        import app.voice.session as mod
        from app.voice.context import CallContext

        sess = mod.VoiceSession(
            MagicMock(),
            call_context=CallContext("CA1", 1, "UTC", "primary"),
        )
        sess.transcript.extend(["user: hello", "assistant: hi there"])
        token = mod._active_session.set(sess)
        try:
            result = mod.get_call_transcript()
            assert result == "user: hello\nassistant: hi there"
        finally:
            mod._active_session.reset(token)


class TestAppointmentOutSchema:
    """AppointmentOut schema includes transcript field."""

    def test_transcript_field_present(self):
        from app.appointments.schemas import AppointmentOut

        fields = AppointmentOut.model_fields
        assert "transcript" in fields
