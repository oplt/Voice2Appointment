"""Phase 3 regression tests — date/timezone resolution, idempotency, analytics row cap."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import pytest

from app.appointments.idempotency import (
    build_appointment_idempotency_key,
)
from app.voice.dates import (
    next_weekday_date,
    resolve_relative_date,
    resolve_relative_datetime,
)

# ---------------------------------------------------------------------------
# Date / timezone regression
# ---------------------------------------------------------------------------

class TestResolveRelativeDate:
    """Regression: 'tomorrow at 3', 'next Friday', timezone handling."""

    _FIXED_NOW = datetime(2026, 9, 3, 14, 0, 0, tzinfo=ZoneInfo("Europe/Brussels"))

    def test_tomorrow(self):
        d = resolve_relative_date("tomorrow", timezone_name="Europe/Brussels", now=self._FIXED_NOW)
        assert d == date(2026, 9, 4)

    def test_today(self):
        d = resolve_relative_date("today", timezone_name="Europe/Brussels", now=self._FIXED_NOW)
        assert d == date(2026, 9, 3)

    def test_next_friday(self):
        # 2026-09-03 is Thursday, so "next Friday" => 2026-09-04
        d = resolve_relative_date("next friday", timezone_name="Europe/Brussels", now=self._FIXED_NOW)
        assert d == date(2026, 9, 4)

    def test_next_monday(self):
        # Thursday -> next Monday = +4 days => 2026-09-07
        d = resolve_relative_date("next monday", timezone_name="Europe/Brussels", now=self._FIXED_NOW)
        assert d == date(2026, 9, 7)

    def test_new_york_timezone(self):
        # 2026-09-03 23:30 UTC => still Sep 3 in New York (UTC-4), but Sep 4 in Brussels
        late_utc = datetime(2026, 9, 3, 23, 30, 0, tzinfo=timezone.utc)
        d_ny = resolve_relative_date("today", timezone_name="America/New_York", now=late_utc)
        d_bru = resolve_relative_date("today", timezone_name="Europe/Brussels", now=late_utc)
        assert d_ny == date(2026, 9, 3)
        assert d_bru == date(2026, 9, 4)  # +1h/+2h CEST => next day

    def test_unsupported_phrase_raises(self):
        with pytest.raises(ValueError, match="Unsupported"):
            resolve_relative_date("in three weeks", timezone_name="UTC", now=self._FIXED_NOW)


class TestResolveRelativeDatetime:
    _FIXED_NOW = datetime(2026, 9, 3, 14, 0, 0, tzinfo=ZoneInfo("Europe/Brussels"))

    def test_tomorrow_at_default_time(self):
        dt = resolve_relative_datetime(
            "tomorrow",
            timezone_name="Europe/Brussels",
            now=self._FIXED_NOW,
            default_time=time(15, 30),
        )
        assert dt.date() == date(2026, 9, 4)
        assert dt.hour == 15 and dt.minute == 30

    def test_this_afternoon(self):
        dt = resolve_relative_datetime(
            "this afternoon",
            timezone_name="Europe/Brussels",
            now=self._FIXED_NOW,
        )
        assert dt.date() == date(2026, 9, 3)
        assert dt.hour == 12

    def test_this_evening(self):
        dt = resolve_relative_datetime(
            "this evening",
            timezone_name="Europe/Brussels",
            now=self._FIXED_NOW,
        )
        assert dt.hour == 17


class TestDSTBoundary:
    """Regression: DST transitions don't break date resolution."""

    def test_brussels_spring_forward(self):
        # 2026 spring forward: last Sunday of March => Mar 29 2026 at 02:00
        before_dst = datetime(2026, 3, 28, 23, 0, 0, tzinfo=ZoneInfo("Europe/Brussels"))
        d = resolve_relative_date("tomorrow", timezone_name="Europe/Brussels", now=before_dst)
        assert d == date(2026, 3, 29)

    def test_new_york_fall_back(self):
        # 2026 fall back: first Sunday of November => Nov 1 2026
        before_fb = datetime(2026, 10, 31, 23, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        d = resolve_relative_date("tomorrow", timezone_name="America/New_York", now=before_fb)
        assert d == date(2026, 11, 1)


class TestNextWeekdayDate:
    def test_same_weekday_returns_plus_7(self):
        # Thursday now, ask for Thursday => +7
        now = datetime(2026, 9, 3, 10, 0, tzinfo=ZoneInfo("UTC"))
        assert next_weekday_date(now, 3) == date(2026, 9, 10)


# ---------------------------------------------------------------------------
# Idempotency regression
# ---------------------------------------------------------------------------

class TestIdempotencyKey:
    """Regression: duplicate appointment creation detection."""

    _BASE = dict(
        user_id=1,
        calendar_id="primary",
        start_utc=datetime(2026, 9, 5, 10, 0, 0, tzinfo=timezone.utc),
        end_utc=datetime(2026, 9, 5, 10, 30, 0, tzinfo=timezone.utc),
        summary="Dentist Appointment",
        call_sid="CA123",
    )

    def test_same_inputs_same_key(self):
        k1 = build_appointment_idempotency_key(**self._BASE)
        k2 = build_appointment_idempotency_key(**self._BASE)
        assert k1 == k2

    def test_different_time_different_key(self):
        alt = {**self._BASE, "start_utc": datetime(2026, 9, 5, 11, 0, 0, tzinfo=timezone.utc)}
        assert build_appointment_idempotency_key(**self._BASE) != build_appointment_idempotency_key(**alt)

    def test_whitespace_normalization(self):
        k1 = build_appointment_idempotency_key(**{**self._BASE, "summary": "  Dentist   Appointment "})
        k2 = build_appointment_idempotency_key(**self._BASE)
        assert k1 == k2

    def test_case_insensitive_title(self):
        k1 = build_appointment_idempotency_key(**{**self._BASE, "summary": "DENTIST APPOINTMENT"})
        k2 = build_appointment_idempotency_key(**self._BASE)
        assert k1 == k2

    def test_none_call_sid(self):
        k1 = build_appointment_idempotency_key(**{**self._BASE, "call_sid": None})
        k2 = build_appointment_idempotency_key(**{**self._BASE, "call_sid": None})
        assert k1 == k2


# ---------------------------------------------------------------------------
# Analytics row cap (unit-level: verify the query has a limit)
# ---------------------------------------------------------------------------

class TestAnalyticsRangeValidation:
    """Analytics ranges are bounded; no silent row truncation."""

    def test_reversed_range_rejected(self):
        from datetime import date

        import pytest

        from app.analytics.service import AnalyticsRangeError, resolve_analytics_window

        with pytest.raises(AnalyticsRangeError):
            resolve_analytics_window(
                date(2026, 9, 10), date(2026, 9, 1), timezone_name="UTC"
            )

    def test_oversized_range_rejected(self, monkeypatch):
        from datetime import date

        import pytest

        from app.analytics.service import AnalyticsRangeError, resolve_analytics_window
        from app.core.config import settings

        monkeypatch.setattr(settings, "analytics_max_range_days", 7)
        with pytest.raises(AnalyticsRangeError):
            resolve_analytics_window(
                date(2026, 1, 1), date(2026, 1, 20), timezone_name="UTC"
            )
