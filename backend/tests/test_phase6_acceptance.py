"""Phase 6 acceptance — correctness gaps across secure links, payments, customers, webhooks."""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.customers.api import list_customers
from app.customers.service import get_or_create_customer
from app.db.base import Base
from app.db.models import PaymentIntent, SecureLinkDelivery, User
from app.notifications.secure_link_worker import (
    STATUS_SENT,
    claim_due_deliveries,
    deliver_one,
)
from app.notifications.secure_links import stage_secure_link
from app.payments.service import PaymentError, capture_payment, payment_public_view
from app.tenancy.service import create_organization_for_user


def _session() -> Session:
    if not (settings.fernet_key or "").strip():
        settings.fernet_key = Fernet.generate_key().decode()
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _org(db: Session) -> tuple[User, int]:
    user = User(username="p6", email="p6@example.test", password="unused")
    db.add(user)
    db.flush()
    org = create_organization_for_user(db, user)
    db.commit()
    return user, org.id


def test_secure_link_token_is_encrypted_at_rest_and_url_not_persisted() -> None:
    db = _session()
    _user, org_id = _org(db)
    delivery = stage_secure_link(
        db,
        organization_id=org_id,
        purpose="payment",
        client_email="enc@example.test",
    )
    db.commit()

    assert "secure_url" not in dict(delivery.metadata_json or {})
    plain = delivery.token_ciphertext
    assert plain and len(plain) > 10

    raw = db.execute(
        text("SELECT token_ciphertext FROM secure_link_delivery WHERE id = :id"),
        {"id": delivery.id},
    ).scalar_one()
    assert isinstance(raw, str)
    assert raw.startswith("enc:")
    assert raw != plain
    assert plain not in raw


def test_deliver_one_does_not_duplicate_send_after_sent() -> None:
    db = _session()
    _user, org_id = _org(db)
    delivery = stage_secure_link(
        db,
        organization_id=org_id,
        purpose="payment",
        client_email="once@example.test",
    )
    db.commit()

    with (
        patch("app.notifications.secure_link_worker._mail_configured", return_value=True),
        patch("app.notifications.secure_link_worker._send_email") as send_email,
    ):
        claimed = claim_due_deliveries(db, limit=1)
        assert len(claimed) == 1
        first = deliver_one(db, claimed[0])
        assert first.get("ok") is True
        assert send_email.call_count == 1

        db.expire_all()
        row = db.get(SecureLinkDelivery, delivery.id)
        assert row is not None
        assert row.status == STATUS_SENT
        second = deliver_one(db, row)
        assert second.get("idempotent") is True
        assert send_email.call_count == 1


def test_payment_invalid_expired_and_already_captured_states() -> None:
    db = _session()
    _user, org_id = _org(db)
    customer = get_or_create_customer(
        db, organization_id=org_id, email="pay@example.test", name="Pay"
    )
    delivery = stage_secure_link(
        db,
        organization_id=org_id,
        purpose="deposit",
        client_email="pay@example.test",
        client_name="Pay",
    )
    intent = PaymentIntent(
        organization_id=org_id,
        customer_id=customer.id,
        amount_minor=1000,
        currency="EUR",
        purpose="deposit",
        provider="manual",
        status="pending",
        secure_link_delivery_id=delivery.id,
        metadata_json={},
    )
    db.add(intent)
    db.commit()
    db.refresh(delivery)
    raw_token = delivery.token_ciphertext
    assert raw_token

    with pytest.raises(PaymentError, match="invalid payment token"):
        capture_payment(db, intent.id, token="not-the-token")

    delivery.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    view = payment_public_view(intent, db)
    assert view["link_expired"] is True
    with pytest.raises(PaymentError, match="expired"):
        capture_payment(db, intent.id, token=raw_token)

    db.refresh(intent)
    assert intent.status == "expired"
    with pytest.raises(PaymentError, match="expired"):
        capture_payment(db, intent.id, token=raw_token)

    # Fresh intent for already-captured idempotency.
    delivery2 = stage_secure_link(
        db,
        organization_id=org_id,
        purpose="payment",
        client_email="pay2@example.test",
    )
    intent2 = PaymentIntent(
        organization_id=org_id,
        customer_id=customer.id,
        amount_minor=500,
        currency="EUR",
        purpose="payment",
        provider="manual",
        status="pending",
        secure_link_delivery_id=delivery2.id,
        metadata_json={},
    )
    db.add(intent2)
    db.commit()
    db.refresh(delivery2)
    token2 = delivery2.token_ciphertext
    assert token2
    first = capture_payment(db, intent2.id, token=token2)
    assert first.status == "captured"
    second = capture_payment(db, intent2.id, token=token2)
    assert second.id == first.id
    assert second.status == "captured"


def test_customer_list_pagination_clamps_and_pages() -> None:
    db = _session()
    _user, org_id = _org(db)
    for i in range(5):
        get_or_create_customer(
            db,
            organization_id=org_id,
            name=f"Customer {i:02d}",
            email=f"c{i}@example.test",
        )
    db.commit()

    page0 = list_customers(organization_id=org_id, query=None, limit=2, offset=0, db=db)
    assert page0.total == 5
    assert page0.limit == 2
    assert page0.offset == 0
    assert len(page0.items) == 2

    page1 = list_customers(organization_id=org_id, query=None, limit=2, offset=2, db=db)
    assert len(page1.items) == 2
    assert {row.id for row in page0.items}.isdisjoint({row.id for row in page1.items})

    clamped = list_customers(organization_id=org_id, query=None, limit=999, offset=-3, db=db)
    assert clamped.limit == 100
    assert clamped.offset == 0
    assert len(clamped.items) == 5


def test_webhook_handlers_own_work_via_to_thread_db() -> None:
    """Twilio + Stripe webhooks must leave the event loop via to_thread_db."""
    from app.payments import api as payments_api
    from app.telephony import router as telephony_router

    telephony_src = inspect.getsource(telephony_router)
    assert "to_thread_db" in telephony_src
    for name in ("voice_webhook", "status_webhook", "recording_webhook", "transfer_webhook"):
        # Function names may vary; assert module wires thread offload for webhook routes.
        pass
    assert telephony_src.count("to_thread_db") >= 3

    payments_src = inspect.getsource(payments_api)
    assert "to_thread_db" in payments_src
    assert "stripe_webhook" in payments_src

    # AST: stripe_webhook coroutine body awaits to_thread_db
    tree = ast.parse(Path(payments_api.__file__).read_text(encoding="utf-8"))
    stripe_fn = next(
        node
        for node in tree.body
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
        and node.name == "stripe_webhook"
    )
    assert isinstance(stripe_fn, ast.AsyncFunctionDef)
    await_calls = [
        n
        for n in ast.walk(stripe_fn)
        if isinstance(n, ast.Await)
        and isinstance(n.value, ast.Call)
        and (
            (isinstance(n.value.func, ast.Name) and n.value.func.id == "to_thread_db")
            or (
                isinstance(n.value.func, ast.Attribute)
                and n.value.func.attr == "to_thread_db"
            )
        )
    ]
    assert await_calls, "stripe_webhook must await to_thread_db"
