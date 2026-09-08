"""PHASE 13 — production acceptance gates."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core import feature_flags
from app.core.feature_flags import (
    FeatureDisabledError,
    capability_allowed,
    clear_flag_cache,
    require_catalog_domain,
    require_reservation_domain,
)
from app.db.base import Base
from app.db.models import Appointment, Organization, OrganizationMember, User
from app.tenancy.service import create_organization_for_user
from app.voice.registry.core import get_tool_registry, reset_tool_registry_for_tests


BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


@pytest.fixture(autouse=True)
def _reset_flags(monkeypatch):
    clear_flag_cache()
    reset_tool_registry_for_tests()
    yield
    clear_flag_cache()
    reset_tool_registry_for_tests()


def test_kill_switches_block_new_domain_capabilities(monkeypatch) -> None:
    monkeypatch.setattr(feature_flags, "catalog_domain_enabled", lambda: False)
    monkeypatch.setattr(feature_flags, "reservation_domain_enabled", lambda: False)
    monkeypatch.setattr(feature_flags, "industry_voice_tools_enabled", lambda: False)
    clear_flag_cache()
    assert capability_allowed("catalog") is False
    assert capability_allowed("reservation") is False
    assert capability_allowed("clinic") is False
    assert capability_allowed("calendar") is True
    with pytest.raises(FeatureDisabledError):
        require_catalog_domain()
    with pytest.raises(FeatureDisabledError):
        require_reservation_domain()


def test_legacy_calendar_tools_remain_when_domain_flags_off(monkeypatch) -> None:
    monkeypatch.setattr(feature_flags, "catalog_domain_enabled", lambda: False)
    monkeypatch.setattr(feature_flags, "reservation_domain_enabled", lambda: False)
    monkeypatch.setattr(feature_flags, "industry_voice_tools_enabled", lambda: False)
    clear_flag_cache()
    registry = get_tool_registry()
    assert registry.is_allowed(None, user_id=None, tool_name="create_calendar_event")
    assert registry.is_allowed(None, user_id=None, tool_name="check_calendar_availability")
    assert not registry.is_allowed(None, user_id=None, tool_name="book_table")
    names = {d.name for d in registry.enabled_definitions(None, user_id=None)}
    assert "create_calendar_event" in names
    assert "book_table" not in names


def test_legacy_tenant_gets_organization_on_create() -> None:
    db = _session()
    user = User(id=42, username="legacy", email="legacy@example.test", password="x")
    db.add(user)
    db.commit()
    org = create_organization_for_user(db, user)
    db.commit()
    assert org.slug == "legacy-42"
    assert user.organization_id == org.id
    member = db.scalar(
        select(OrganizationMember).where(OrganizationMember.user_id == user.id)
    )
    assert member is not None
    assert member.role == "owner"
    assert db.get(Organization, org.id) is not None


def test_appointment_booking_still_works_without_catalog_domain(monkeypatch) -> None:
    from datetime import datetime, timedelta, timezone

    from app.appointments import booking

    monkeypatch.setattr(feature_flags, "catalog_domain_enabled", lambda: False)
    clear_flag_cache()
    db = _session()
    user = User(id=7, username="u7", email="u7@example.test", password="x")
    db.add(user)
    db.commit()
    monkeypatch.setattr(
        "app.notifications.service.enqueue_confirmation", lambda *_a, **_k: None
    )
    start = datetime.now(timezone.utc) + timedelta(days=1)
    row = booking.book_appointment(
        db,
        7,
        summary="Consultation",
        start_datetime=start,
        end_datetime=start + timedelta(minutes=30),
        idempotency_key="p13-legacy-book",
    )
    assert row.id is not None
    assert db.get(Appointment, row.id) is not None


def test_provider_io_outside_lock_documented_in_booking_module() -> None:
    """Acceptance #10: booking docstring + complete_create after lock."""
    booking_path = BACKEND / "app" / "appointments" / "booking.py"
    text = booking_path.read_text(encoding="utf-8")
    assert "outside the lock" in text
    assert "complete_create" in text
    # Call site (not import/docstring) must follow the scheduling_lock block.
    lock_idx = text.find("with scheduling_lock")
    assert lock_idx != -1
    complete_idx = text.find("complete_create(", lock_idx)
    assert complete_idx != -1


def test_reservation_commit_calls_provider_after_lock() -> None:
    path = BACKEND / "app" / "reservations" / "service.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    commit_fn = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "commit_reservation"
    )
    # Find With(scheduling_lock) and ensure complete_create Call is not nested under it.
    lock_with: ast.With | None = None
    for node in ast.walk(commit_fn):
        if isinstance(node, ast.With):
            for item in node.items:
                call = item.context_expr
                if isinstance(call, ast.Call):
                    func = call.func
                    name = getattr(func, "id", None) or getattr(func, "attr", None)
                    if name == "scheduling_lock":
                        lock_with = node
                        break
    assert lock_with is not None

    def _contains_complete_create(node: ast.AST) -> bool:
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id == "complete_create":
                return True
            if isinstance(child, ast.Attribute) and child.attr == "complete_create":
                return True
        return False

    assert not _contains_complete_create(lock_with)
    assert _contains_complete_create(commit_fn)


def test_organization_backfill_migration_exists() -> None:
    migrations = list((BACKEND / "migrations" / "versions").glob("*backfill_organizations*"))
    assert migrations, "legacy tenant org backfill migration missing"
    body = migrations[0].read_text(encoding="utf-8")
    assert "legacy-" in body
    assert "organization_member" in body
    assert "downgrade" in body


def test_rollback_runbook_exists() -> None:
    doc = REPO / "docs" / "production-acceptance.md"
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    for needle in (
        "Rollback",
        "ENABLE_CATALOG_DOMAIN",
        "ENABLE_RESERVATION_DOMAIN",
        "legacy",
        "voice latency",
    ):
        assert needle.lower() in text.lower()
