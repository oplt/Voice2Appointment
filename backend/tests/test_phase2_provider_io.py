from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.analytics import sync
from app.appointments import booking, provider_operations
from app.db.base import Base
from app.db.models import Appointment, TwilioCall, User
from app.telephony.providers.twilio import CallPage


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _user(db: Session, user_id: int = 1) -> User:
    user = User(
        id=user_id,
        username=f"user-{user_id}",
        email=f"user-{user_id}@example.test",
        password="not-used-in-test",
    )
    db.add(user)
    db.commit()
    return user


def test_booking_provider_precheck_and_create_run_after_lock(monkeypatch) -> None:
    db = _session()
    _user(db)
    lock_held = False
    calls: list[str] = []

    @contextmanager
    def lock(*_args, **_kwargs):
        nonlocal lock_held
        lock_held = True
        try:
            yield
        finally:
            lock_held = False

    monkeypatch.setattr(booking, "scheduling_lock", lock)
    monkeypatch.setattr(
        "app.notifications.service.enqueue_confirmation", lambda *_args: None
    )

    def available(*_args) -> None:
        assert not lock_held
        assert not db.in_transaction()
        calls.append("available")

    def create(**_kwargs) -> dict[str, str]:
        assert not lock_held
        assert not db.in_transaction()
        calls.append("create")
        return {"id": "event-1", "htmlLink": "https://calendar.test/event-1"}

    start = datetime.now(timezone.utc) + timedelta(days=2)
    first = booking.book_appointment(
        db,
        1,
        summary="Consultation",
        start_datetime=start,
        end_datetime=start + timedelta(minutes=30),
        idempotency_key="phase2-booking",
        check_provider_availability=available,
        provider_create=create,
    )
    second = booking.book_appointment(
        db,
        1,
        summary="Consultation",
        start_datetime=start,
        end_datetime=start + timedelta(minutes=30),
        idempotency_key="phase2-booking",
        check_provider_availability=available,
        provider_create=create,
    )

    assert first.id == second.id
    assert calls == ["available", "create"]
    assert db.scalars(select(Appointment)).all()[0].provider_sync_status == "confirmed"


def test_twilio_provider_fetches_run_without_an_open_db_transaction() -> None:
    db = _session()
    _user(db, user_id=2)
    db.add(TwilioCall(user_id=2, sid="CA-active", status="in-progress"))
    db.commit()
    provider_calls: list[str] = []

    class Provider:
        def __init__(self, **_kwargs) -> None:
            pass

        def fetch_call_page(self, **_kwargs) -> CallPage:
            assert not db.in_transaction()
            provider_calls.append("page")
            return CallPage(records=[], next_page_token=None, exhausted=True)

        def fetch_calls_by_sids(self, _sids) -> list[dict]:
            assert not db.in_transaction()
            provider_calls.append("active")
            return []

    result = sync.fetch_and_store_twilio(
        db,
        user_id=2,
        account_sid="ACtest",
        auth_token="token",
        provider_factory=Provider,
    )

    assert result["pages"] == 1
    assert provider_calls == ["page", "active"]
    user = db.get(User, 2)
    assert user is not None
    assert user.twilio_sync_lease_token is None


def test_crash_after_pending_hold_keeps_booking_reconcilable(monkeypatch) -> None:
    db = _session()
    _user(db, user_id=4)
    monkeypatch.setattr(
        "app.notifications.service.enqueue_confirmation", lambda *_args: None
    )

    class SimulatedCrash(BaseException):
        pass

    def crash(**_kwargs) -> dict[str, str]:
        assert not db.in_transaction()
        raise SimulatedCrash()

    start = datetime.now(timezone.utc) + timedelta(days=2)
    try:
        booking.book_appointment(
            db,
            4,
            summary="Consultation",
            start_datetime=start,
            end_datetime=start + timedelta(minutes=30),
            idempotency_key="phase2-crash",
            provider_create=crash,
        )
    except SimulatedCrash:
        pass
    else:
        raise AssertionError("simulated crash must escape the booking request")

    pending = db.scalar(select(Appointment).where(Appointment.idempotency_key == "phase2-crash"))
    assert pending is not None
    assert pending.provider_sync_status == "pending_provider"
    assert pending.provider_operation == "create"


def test_provider_success_retries_after_finalize_failure(monkeypatch) -> None:
    db = _session()
    _user(db, user_id=5)
    monkeypatch.setattr(
        "app.notifications.service.enqueue_confirmation", lambda *_args: None
    )
    start = datetime.now(timezone.utc) + timedelta(days=2)
    provider_calls = 0

    def create(**_kwargs) -> dict[str, str]:
        nonlocal provider_calls
        provider_calls += 1
        return {"id": "provider-idempotent-event"}

    original_finalize = provider_operations._claimed_current
    monkeypatch.setattr(provider_operations, "_claimed_current", lambda *_args: None)
    pending = booking.book_appointment(
        db,
        5,
        summary="Consultation",
        start_datetime=start,
        end_datetime=start + timedelta(minutes=30),
        idempotency_key="phase2-finalize-retry",
        provider_create=create,
    )
    assert pending.provider_sync_status == "pending_provider"
    monkeypatch.setattr(provider_operations, "_claimed_current", original_finalize)

    pending.provider_next_retry_at = None
    db.commit()
    finalized = provider_operations.complete_create(db, pending.id, create)

    assert provider_calls == 2
    assert finalized.google_calendar_event_id == "provider-idempotent-event"
    assert finalized.provider_sync_status == "confirmed"


def test_twilio_sync_lease_skips_a_second_worker() -> None:
    db = _session()
    _user(db, user_id=3)
    token = sync._acquire_sync_lease(db, 3, lease_seconds=60)
    assert token is not None

    class Provider:
        def __init__(self, **_kwargs) -> None:
            raise AssertionError("provider must not be constructed for a held lease")

    result = sync.fetch_and_store_twilio(
        db,
        user_id=3,
        account_sid="ACtest",
        auth_token="token",
        provider_factory=Provider,
    )

    assert result["message"] == "Twilio sync already in progress"
    sync._release_sync_lease(db, 3, token)
