# tests/test_google_calendar_integration.py
import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flaskapp import create_app
from flaskapp.utils.calendar import GoogleCalendarService

# If you implemented a custom exception like ReauthRequired, import it:
try:
    from flaskapp.utils.calendar import ReauthRequired  # optional
except Exception:  # pragma: no cover
    ReauthRequired = None


@pytest.mark.integration
def test_create_event_tomorrow_4pm_brussels():
    """
    Integration test: create a Google Calendar event tomorrow at 16:00
    Europe/Brussels for 1 hour. Skips if Google re-authorization is required.
    """

    app = create_app()

    # IMPORTANT: ensure we have a valid user_id that is linked to Google Calendar credentials
    user_id = 1

    # Compute tomorrow at 16:00 in Europe/Brussels
    tz = ZoneInfo("Europe/Brussels")
    now_local = datetime.now(tz)
    tomorrow_local = (now_local + timedelta(days=1)).replace(hour=16, minute=0, second=0, microsecond=0)
    end_local = tomorrow_local + timedelta(hours=1)

    # Use local ISO strings; pass timezone explicitly to service
    start_iso = tomorrow_local.isoformat()
    end_iso = end_local.isoformat()

    with app.app_context():
        # Initialize the service
        try:
            svc = GoogleCalendarService(user_id)
        except Exception as e:
            # If your service raises a custom "reauth required" error, skip:
            if ReauthRequired and isinstance(e, ReauthRequired):
                pytest.skip(f"Google re-authorization required: {e}")
            # Or, skip on common token errors without failing the suite
            msg = str(e).lower()
            if "invalid_grant" in msg or "reauthorization" in msg or "expired or revoked" in msg:
                pytest.skip(f"OAuth not authorized for user {user_id}: {e}")
            raise  # Unexpected error → fail the test

        event_id = None
        try:
            event = svc.create_event(
                summary="Pytest: Tomorrow 4pm (Europe/Brussels)",
                datetime_start=start_iso,
                datetime_end=end_iso,
                description="Created by automated integration test",
                timezone="Europe/Brussels",
            )

            # Basic assertions
            assert event is not None, "Service returned no event payload"
            assert "id" in event and event["id"], "Event ID missing in response"
            assert event.get("summary") == "Pytest: Tomorrow 4pm (Europe/Brussels)"
            event_id = event["id"]

        finally:
            # Cleanup: delete the event to keep calendars tidy (best-effort)
            if event_id:
                try:
                    if hasattr(svc, "delete_event"):
                        svc.delete_event(event_id)
                except Exception:
                    # Don't fail the test if cleanup fails
                    pass
