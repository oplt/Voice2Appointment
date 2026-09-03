"""Phase 16: tenant booking policy and conflict enforcement."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.appointments.policy import (
    BookingConflictError,
    BookingPolicy,
    BookingPolicyError,
    BusinessHoursWindow,
    load_booking_policy,
    resolve_slot_end,
    save_booking_policy,
    validate_slot,
)
from app.appointments.service import create_appointment
from app.core.security import hash_password
from app.db.models import User


def _user(db_session) -> User:
    user = User(
        username="commercial",
        email="commercial@example.com",
        password=hash_password("password123"),
        config_json='{"agent":{"greeting":"hello"}}',
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_booking_policy_merge_preserves_voice_config(db_session) -> None:
    user = _user(db_session)
    policy = BookingPolicy(
        default_service_duration_minutes=30,
        service_durations_minutes={"Consultation": 45},
        buffer_before_minutes=10,
        buffer_after_minutes=15,
        business_hours={
            "monday": [BusinessHoursWindow(start="09:00", end="17:00")]
        },
    )
    save_booking_policy(user, policy)
    db_session.commit()

    assert '"agent"' in (user.config_json or "")
    assert load_booking_policy(user.config_json) == policy


def test_named_service_duration_supplies_missing_end() -> None:
    start = datetime(2026, 9, 7, 10, 0, tzinfo=ZoneInfo("Europe/Brussels"))
    policy = BookingPolicy(service_durations_minutes={"Consultation": 45})
    assert resolve_slot_end(
        policy, summary="consultation", start=start, end=None
    ) == start + timedelta(minutes=45)
    with pytest.raises(BookingPolicyError, match="must be 45 minutes"):
        resolve_slot_end(
            policy,
            summary="Consultation",
            start=start,
            end=start + timedelta(minutes=30),
        )


def test_business_hours_and_buffer_conflicts(db_session) -> None:
    user = _user(db_session)
    save_booking_policy(
        user,
        BookingPolicy(
            buffer_before_minutes=15,
            business_hours={
                "monday": [BusinessHoursWindow(start="09:00", end="17:00")]
            },
        ),
    )
    db_session.commit()
    zone = ZoneInfo("Europe/Brussels")
    existing_start = datetime(2026, 9, 7, 10, 0, tzinfo=zone)
    create_appointment(
        db_session,
        user.id,
        summary="Existing",
        start_datetime=existing_start,
        end_datetime=existing_start + timedelta(minutes=30),
        timezone="Europe/Brussels",
        status="confirmed",
    )

    with pytest.raises(BookingConflictError):
        validate_slot(
            db_session,
            user.id,
            start=existing_start + timedelta(minutes=40),
            end=existing_start + timedelta(minutes=70),
            timezone_name="Europe/Brussels",
        )
    with pytest.raises(BookingPolicyError, match="outside business hours"):
        validate_slot(
            db_session,
            user.id,
            start=existing_start.replace(hour=18),
            end=existing_start.replace(hour=18, minute=30),
            timezone_name="Europe/Brussels",
        )
