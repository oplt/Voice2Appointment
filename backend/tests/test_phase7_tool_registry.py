"""PHASE 7 — capability-aware voice ToolRegistry."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import User
from app.industries.service import assign_industry_profile
from app.tenancy.service import create_organization_for_user
from app.voice.config_loader import load_voice_config_for_context
from app.voice.context import CallContext
from app.voice.registry.core import get_tool_registry, reset_tool_registry_for_tests
from app.voice.registry.types import ToolKind


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def setup_function() -> None:
    reset_tool_registry_for_tests()


def test_registry_keeps_legacy_deepgram_names() -> None:
    registry = get_tool_registry()
    for name in (
        "check_calendar_availability",
        "find_appointments",
        "create_calendar_event",
        "reschedule_appointment",
        "cancel_appointment",
        "request_human_handoff",
    ):
        definition = registry.get(name)
        assert definition is not None
        assert definition.name == name
    assert registry.get("create_calendar_event").kind is ToolKind.MUTATION
    assert "confirmed_gate" in registry.get("create_calendar_event").idempotency.mode


def test_legacy_default_deepgram_config_without_profile() -> None:
    db = _session()
    user = User(username="voice7", email="voice7@example.test", password="unused")
    db.add(user)
    db.flush()
    create_organization_for_user(db, user)
    db.commit()

    def factory() -> Session:
        return sessionmaker(bind=db.get_bind())()

    ctx = CallContext(
        user_id=user.id,
        call_sid="CA_test",
        timezone="UTC",
        calendar_id="primary",
    )
    config = load_voice_config_for_context(ctx, factory)
    names = [item["name"] for item in config["agent"]["think"]["functions"]]
    assert set(names) == {
        "check_calendar_availability",
        "find_appointments",
        "create_calendar_event",
        "reschedule_appointment",
        "cancel_appointment",
        "request_human_handoff",
    }
    assert len(names) == 6
    assert "CURRENT DATE CONTEXT" in config["agent"]["think"]["prompt"]


def test_restaurant_profile_filters_deepgram_tools() -> None:
    db = _session()
    user = User(username="resto7", email="resto7@example.test", password="unused")
    db.add(user)
    db.flush()
    organization = create_organization_for_user(db, user)
    assign_industry_profile(db, organization_id=organization.id, industry_type="restaurant")
    db.commit()

    def factory() -> Session:
        return sessionmaker(bind=db.get_bind())()

    ctx = CallContext(
        user_id=user.id,
        call_sid="CA_resto",
        timezone="UTC",
        calendar_id="primary",
    )
    config = load_voice_config_for_context(ctx, factory)
    names = {item["name"] for item in config["agent"]["think"]["functions"]}
    assert "restaurant_availability" in names
    assert "create_reservation" in names
    assert "join_waitlist" in names
    assert "request_human_handoff" in names
    assert "create_calendar_event" not in names
    assert "create_reservation" in config["agent"]["think"]["prompt"]


def test_clinic_and_general_tool_sets() -> None:
    registry = get_tool_registry()
    db = _session()
    clinic_user = User(username="clinic7", email="clinic7@example.test", password="unused")
    general_user = User(username="gen7", email="gen7@example.test", password="unused")
    db.add_all((clinic_user, general_user))
    db.flush()
    clinic_org = create_organization_for_user(db, clinic_user)
    general_org = create_organization_for_user(db, general_user)
    assign_industry_profile(db, organization_id=clinic_org.id, industry_type="clinic")
    assign_industry_profile(db, organization_id=general_org.id, industry_type="general")
    db.commit()

    clinic_names = {d.name for d in registry.enabled_definitions(db, user_id=clinic_user.id)}
    assert "find_visit_types" in clinic_names
    assert "find_practitioners" in clinic_names
    assert "create_appointment" in clinic_names
    assert "create_reservation" not in clinic_names

    general_names = {d.name for d in registry.enabled_definitions(db, user_id=general_user.id)}
    assert "search_catalog" in general_names
    assert "get_price" in general_names
    assert "take_message" in general_names
    assert "book_appointment" in general_names


def test_execute_denies_unentitled_tool() -> None:
    from app.calendars.tools import voice_db, voice_user_id
    from app.voice.session import execute_function_call

    db = _session()
    user = User(username="deny7", email="deny7@example.test", password="unused")
    db.add(user)
    db.flush()
    organization = create_organization_for_user(db, user)
    assign_industry_profile(db, organization_id=organization.id, industry_type="restaurant")
    db.commit()

    token_db = voice_db.set(db)
    token_user = voice_user_id.set(user.id)
    try:
        result = execute_function_call("create_calendar_event", {"summary": "x"})
        assert result["error"] == "tool_not_entitled"
        allowed = get_tool_registry().is_allowed(
            db, user_id=user.id, tool_name="create_reservation"
        )
        assert allowed is True
    finally:
        voice_user_id.reset(token_user)
        voice_db.reset(token_db)
