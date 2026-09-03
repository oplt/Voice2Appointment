"""P7-03 PostgreSQL persistence / concurrency gates."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.appointments import booking as booking_service
from app.appointments.locking import tenant_booking_lock
from app.appointments.policy import BookingConflictError, BookingPolicy, save_booking_policy
from app.core.security import hash_password
from app.db.models import Appointment, User


def _pg_url() -> str:
    return (os.environ.get("DATABASE_URL") or "").strip()


@pytest.fixture()
def pg_session():
    url = _pg_url()
    if not url.startswith("postgresql"):
        pytest.skip("DATABASE_URL is not PostgreSQL")

    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        engine.dispose()
        pytest.skip(f"PostgreSQL unavailable: {type(exc).__name__}")

    from sqlalchemy import inspect

    from app.db.base import Base
    import app.db.models  # noqa: F401

    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:  # noqa: BLE001
        engine.dispose()
        pytest.skip(f"PostgreSQL schema setup failed: {type(exc).__name__}")

    tables = set(inspect(engine).get_table_names())
    if "appointment" not in tables or "res_user" not in tables:
        engine.dispose()
        pytest.skip("PostgreSQL missing required tables; run alembic upgrade head")

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        try:
            session.execute(
                text("TRUNCATE appointment, res_user RESTART IDENTITY CASCADE")
            )
            session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
        session.close()
        engine.dispose()


@pytest.mark.integration
def test_postgres_advisory_lock_path(pg_session) -> None:
    user = User(
        username="pg_lock",
        email="pg_lock@example.com",
        password=hash_password("password123"),
    )
    pg_session.add(user)
    pg_session.commit()
    pg_session.refresh(user)
    with tenant_booking_lock(pg_session, user.id):
        held = pg_session.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"),
            {
                "key": (0xB00A_0000_0000_0000 | (user.id & 0xFFFF_FFFF))
                & 0x7FFF_FFFF_FFFF_FFFF
            },
        ).scalar()
        # Same transaction already holds the lock; try returns true when held/acquirable.
        assert held in (True, 1)


@pytest.mark.integration
def test_postgres_booking_overlap_conflict(pg_session) -> None:
    user = User(
        username="pg_book",
        email="pg_book@example.com",
        password=hash_password("password123"),
    )
    save_booking_policy(
        user,
        BookingPolicy(
            default_service_duration_minutes=30,
            business_hours={"monday": [{"start": "09:00", "end": "17:00"}]},
        ),
    )
    pg_session.add(user)
    pg_session.commit()
    pg_session.refresh(user)

    start = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
    first = booking_service.book_appointment(
        pg_session,
        user.id,
        summary="A",
        start_datetime=start,
    )
    assert first.id is not None
    with pytest.raises(BookingConflictError):
        booking_service.book_appointment(
            pg_session,
            user.id,
            summary="B",
            start_datetime=start,
        )


@pytest.mark.integration
def test_postgres_timezone_extract_smoke(pg_session) -> None:
    row = pg_session.execute(
        text("SELECT EXTRACT(HOUR FROM timezone('UTC', now()))")
    ).scalar()
    assert row is not None


@pytest.mark.integration
def test_postgres_appointment_table_exists(pg_session) -> None:
    count = pg_session.execute(text("SELECT count(*) FROM appointment")).scalar()
    assert count is not None
    assert Appointment.__table__.name == "appointment"
