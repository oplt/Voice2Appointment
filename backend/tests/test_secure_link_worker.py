"""Secure-link worker: expiry starvation, claim lease, channel isolation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.db.models import SecureLinkDelivery, User
from app.notifications.secure_link_worker import (
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_SCHEDULED,
    STATUS_SENT,
    claim_due_deliveries,
    deliver_one,
    deliver_scheduled_secure_links,
)
from app.notifications.secure_links import stage_secure_link
from app.tenancy.service import create_organization_for_user


def _session() -> Session:
    if not (settings.fernet_key or "").strip():
        settings.fernet_key = Fernet.generate_key().decode()
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _org(db: Session) -> tuple[User, int]:
    user = User(username="slw", email="slw@example.test", password="unused")
    db.add(user)
    db.flush()
    org = create_organization_for_user(db, user)
    db.commit()
    return user, org.id


def test_expired_rows_do_not_starve_newer_scheduled() -> None:
    db = _session()
    _user, org_id = _org(db)
    now = datetime.now(timezone.utc)
    for i in range(55):
        db.add(
            SecureLinkDelivery(
                organization_id=org_id,
                purpose="payment",
                channel="email",
                recipient=f"old{i}@example.test",
                token_hash=f"{i:064d}"[:64],
                token_ciphertext=f"old-token-{i}",
                status=STATUS_SCHEDULED,
                expires_at=now - timedelta(hours=1),
                idempotency_key=f"expired-{i}",
                metadata_json={},
            )
        )
    db.flush()
    valid = stage_secure_link(
        db,
        organization_id=org_id,
        purpose="deposit",
        client_email="fresh@example.test",
        client_name="Fresh",
    )
    db.commit()
    valid_id = valid.id

    with (
        patch("app.notifications.secure_link_worker._mail_configured", return_value=True),
        patch("app.notifications.secure_link_worker._send_email") as send_email,
    ):
        # Multiple worker ticks may be needed if claim batch is smaller than expired count.
        for _ in range(3):
            deliver_scheduled_secure_links(db, limit=50)
            db.expire_all()
            row = db.get(SecureLinkDelivery, valid_id)
            assert row is not None
            if row.status == STATUS_SENT:
                break

    db.expire_all()
    expired = list(
        db.scalars(
            select(SecureLinkDelivery).where(SecureLinkDelivery.status == STATUS_EXPIRED)
        ).all()
    )
    assert len(expired) >= 50
    fresh = db.get(SecureLinkDelivery, valid_id)
    assert fresh is not None
    assert fresh.status == STATUS_SENT
    assert send_email.called
    assert "secure_url" not in dict(fresh.metadata_json or {})
    assert fresh.token_ciphertext is None


def test_claim_is_exclusive_after_first_worker() -> None:
    db = _session()
    _user, org_id = _org(db)
    delivery = stage_secure_link(
        db,
        organization_id=org_id,
        purpose="payment",
        client_email="race@example.test",
    )
    db.commit()

    first = claim_due_deliveries(db, limit=10)
    assert len(first) == 1
    assert first[0].id == delivery.id
    assert first[0].status == "processing"

    second = claim_due_deliveries(db, limit=10)
    assert second == []


def test_sms_does_not_fall_through_to_email_when_twilio_missing() -> None:
    db = _session()
    _user, org_id = _org(db)
    delivery = stage_secure_link(
        db,
        organization_id=org_id,
        purpose="payment",
        client_phone="+15550001111",
    )
    db.commit()

    with (
        patch(
            "app.notifications.secure_link_worker._resolve_twilio_credentials",
            return_value=None,
        ),
        patch("app.notifications.secure_link_worker._mail_configured", return_value=True),
        patch("app.notifications.secure_link_worker._send_email") as send_email,
        patch("app.notifications.secure_link_worker._send_sms") as send_sms,
    ):
        claimed = claim_due_deliveries(db, limit=1)
        assert len(claimed) == 1
        result = deliver_one(db, claimed[0])

    assert result["error_code"] == "transport_unavailable"
    assert send_email.call_count == 0
    assert send_sms.call_count == 0
    db.expire_all()
    row = db.get(SecureLinkDelivery, delivery.id)
    assert row is not None
    assert row.status in {STATUS_SCHEDULED, STATUS_FAILED}
