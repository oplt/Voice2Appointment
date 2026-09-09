"""PHASE 9 — voice product tools: arg validation, orders, secure links."""

from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.calendars.tools import voice_db, voice_user_id
from app.db.base import Base
from app.db.models import SecureLinkDelivery, User
from app.industries.service import assign_industry_profile
from app.orders.service import upsert_order
from app.tenancy.service import create_organization_for_user
from app.voice.registry.core import get_tool_registry, reset_tool_registry_for_tests
from app.voice.registry.validation import validate_tool_arguments
from app.voice.session import execute_function_call


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def setup_function() -> None:
    reset_tool_registry_for_tests()


def _bind_voice(db: Session, user_id: int):
    return voice_db.set(db), voice_user_id.set(user_id)


def _unbind_voice(token_db, token_user) -> None:
    voice_user_id.reset(token_user)
    voice_db.reset(token_db)


def test_validate_tool_arguments_rejects_bad_send_secure_link() -> None:
    registry = get_tool_registry()
    definition = registry.get("send_secure_link")
    assert definition is not None
    assert definition.args_model is not None

    bad = validate_tool_arguments(definition, {"purpose": "payment"})
    assert bad["success"] is False
    assert bad["error"] == "invalid_arguments"
    assert "details" in bad

    good = validate_tool_arguments(
        definition,
        {"purpose": "payment", "client_email": "buyer@example.test", "extra": "drop-me"},
    )
    assert good.get("error") != "invalid_arguments"
    assert good["client_email"] == "buyer@example.test"
    assert "extra" not in good


def test_validate_tool_arguments_rejects_bad_order_id() -> None:
    registry = get_tool_registry()
    definition = registry.get("check_order_status")
    assert definition is not None
    result = validate_tool_arguments(definition, {"order_id": "   "})
    assert result["success"] is False
    assert result["error"] == "invalid_arguments"


def test_execute_function_call_rejects_invalid_args_before_handler() -> None:
    db = _session()
    user = User(username="p9val", email="p9val@example.test", password="unused")
    db.add(user)
    db.flush()
    organization = create_organization_for_user(db, user)
    assign_industry_profile(db, organization_id=organization.id, industry_type="general")
    db.commit()

    token_db, token_user = _bind_voice(db, user.id)
    try:
        result = execute_function_call("send_secure_link", {"purpose": "payment"})
        assert result["error"] == "invalid_arguments"
        assert db.scalar(select(SecureLinkDelivery.id)) is None
    finally:
        _unbind_voice(token_db, token_user)


def test_check_order_status_found_and_not_found() -> None:
    db = _session()
    user = User(username="p9ord", email="p9ord@example.test", password="unused")
    db.add(user)
    db.flush()
    organization = create_organization_for_user(db, user)
    assign_industry_profile(db, organization_id=organization.id, industry_type="general")
    upsert_order(
        db,
        organization_id=organization.id,
        external_id="ORD-100",
        status="shipped",
        metadata={"carrier": "ups"},
    )
    db.commit()

    token_db, token_user = _bind_voice(db, user.id)
    try:
        missing = execute_function_call("check_order_status", {"order_id": "MISSING"})
        assert missing["success"] is False
        assert missing["error"] == "not_found"

        found = execute_function_call("check_order_status", {"order_id": "ORD-100"})
        assert found["success"] is True
        assert found["order_id"] == "ORD-100"
        assert found["status"] == "shipped"
        assert found["metadata"]["carrier"] == "ups"
    finally:
        _unbind_voice(token_db, token_user)


def test_send_secure_link_creates_delivery_row() -> None:
    db = _session()
    user = User(username="p9link", email="p9link@example.test", password="unused")
    db.add(user)
    db.flush()
    organization = create_organization_for_user(db, user)
    assign_industry_profile(db, organization_id=organization.id, industry_type="general")
    db.commit()

    token_db, token_user = _bind_voice(db, user.id)
    try:
        result = execute_function_call(
            "send_secure_link",
            {
                "purpose": "payment",
                "client_phone": "+15551234567",
                "client_name": "Alex",
            },
        )
        assert result["success"] is True
        assert result["queued"] is True
        assert result["delivery_id"] == result["link_id"]
        assert result["channel"] == "sms"
        assert "token" not in result
        assert "token_ciphertext" not in result
        assert result.get("recipient_masked") == "***4567"

        row = db.get(SecureLinkDelivery, result["delivery_id"])
        assert row is not None
        assert row.organization_id == organization.id
        assert row.purpose == "payment"
        assert row.status == "scheduled"
        assert row.token_hash
        assert row.token_ciphertext
        assert row.token_ciphertext not in str(result)
    finally:
        _unbind_voice(token_db, token_user)
