"""Phase J/K — clinic create_appointment passes Google Calendar provider hooks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.calendars.service import BookingProviderHooks
from app.calendars.tools import voice_db, voice_user_id
from app.catalog.service import create_catalog_item
from app.db.base import Base
from app.db.models import Location, User
from app.industries.service import assign_industry_profile
from app.tenancy.service import create_organization_for_user
from app.voice.registry import handlers_industry


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_create_appointment_passes_provider_create(monkeypatch) -> None:
    db = _session()
    user = User(username="clinicjk", email="clinicjk@example.test", password="unused")
    db.add(user)
    db.flush()
    organization = create_organization_for_user(db, user)
    assign_industry_profile(db, organization_id=organization.id, industry_type="clinic")
    location = Location(organization_id=organization.id, name="Main", timezone="UTC")
    db.add(location)
    db.flush()
    visit = create_catalog_item(
        db,
        organization_id=organization.id,
        name="Follow-up",
        duration_minutes=30,
        bookable=True,
    )
    db.add(visit)
    db.commit()
    db.refresh(visit)

    captured: dict = {}

    def fake_hooks(_db: Session, user_id: int) -> BookingProviderHooks:
        assert user_id == user.id

        def create(**kwargs):
            return {"id": "gcal-1", "htmlLink": "https://calendar.test/1"}

        return BookingProviderHooks(calendar_id="clinic-cal", create_event=create)

    def fake_book(db_arg, **kwargs):
        captured.update(kwargs)
        start = kwargs["start_datetime"]
        return SimpleNamespace(
            id=99,
            status="pending_provider",
            start_datetime=start,
            end_datetime=start + timedelta(minutes=30),
            appointment_id=7,
        )

    monkeypatch.setattr(handlers_industry, "booking_provider_hooks", fake_hooks)
    monkeypatch.setattr(handlers_industry, "book_reservation", fake_book)

    start = datetime.now(timezone.utc) + timedelta(days=2)
    token_db = voice_db.set(db)
    token_user = voice_user_id.set(user.id)
    try:
        result = handlers_industry.create_appointment_tool(
            catalog_item_id=visit.id,
            datetime_start=start.isoformat(),
            confirmed=True,
            client_name="Ada",
            client_phone="+15551212",
        )
    finally:
        voice_user_id.reset(token_user)
        voice_db.reset(token_db)

    assert result["success"] is True
    assert result["path"] == "reservation"
    assert captured["provider_create"] is not None
    assert captured["calendar_id"] == "clinic-cal"
    assert captured["sync_calendar"] is True
    assert captured["organization_id"] == organization.id


def test_create_appointment_without_calendar_falls_back(monkeypatch) -> None:
    db = _session()
    user = User(username="clinicjk2", email="clinicjk2@example.test", password="unused")
    db.add(user)
    db.flush()
    organization = create_organization_for_user(db, user)
    assign_industry_profile(db, organization_id=organization.id, industry_type="clinic")
    visit = create_catalog_item(
        db,
        organization_id=organization.id,
        name="Checkup",
        duration_minutes=20,
        bookable=True,
    )
    db.add(visit)
    db.commit()
    db.refresh(visit)

    captured: dict = {}

    monkeypatch.setattr(
        handlers_industry,
        "booking_provider_hooks",
        lambda *_a, **_k: BookingProviderHooks(),
    )

    def fake_book(_db, **kwargs):
        captured.update(kwargs)
        start = kwargs["start_datetime"]
        return SimpleNamespace(
            id=1,
            status="confirmed",
            start_datetime=start,
            end_datetime=start + timedelta(minutes=20),
            appointment_id=None,
        )

    monkeypatch.setattr(handlers_industry, "book_reservation", fake_book)

    start = datetime.now(timezone.utc) + timedelta(days=1)
    token_db = voice_db.set(db)
    token_user = voice_user_id.set(user.id)
    try:
        result = handlers_industry.create_appointment_tool(
            catalog_item_id=visit.id,
            datetime_start=start.isoformat(),
            confirmed=True,
        )
    finally:
        voice_user_id.reset(token_user)
        voice_db.reset(token_db)

    assert result["success"] is True
    assert captured["provider_create"] is None
    assert captured["calendar_id"] == "primary"
