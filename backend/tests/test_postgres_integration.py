"""Checks that require the migrated PostgreSQL schema."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier, BrokenBarrierError
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.catalog.service import create_catalog_item
from app.db.models import (
    Organization,
    OrganizationMember,
    Resource,
    ServiceResourceRequirement,
    User,
)
from app.reservations import service as reservation_service
from app.reservations.service import ReservationConflictError, hold_reservation
from app.tenancy.service import create_organization_for_user

_PERSIST_ALLOCATIONS = reservation_service._persist_allocations


@pytest.mark.integration
def test_postgres_organization_backfill_schema_is_usable() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_engine(database_url)
    assert engine.dialect.name == "postgresql"

    suffix = uuid4().hex
    with Session(engine) as db:
        user = User(
            username=f"integration-{suffix}",
            email=f"integration-{suffix}@example.invalid",
            password="unused",
        )
        db.add(user)
        db.flush()
        organization = create_organization_for_user(db, user)
        db.flush()

        assert db.get(Organization, organization.id) is not None
        assert db.scalar(
            select(OrganizationMember).where(OrganizationMember.user_id == user.id)
        ) is not None
        db.rollback()

    engine.dispose()


def _seed_reservation_resource(
    db: Session, *, resource_type: str, capacity: int, count: int = 1
) -> tuple[int, int, tuple[int, ...]]:
    suffix = uuid4().hex
    user = User(
        username=f"reservation-{suffix}",
        email=f"reservation-{suffix}@example.invalid",
        password="unused",
    )
    db.add(user)
    db.flush()
    organization = create_organization_for_user(db, user)
    item = create_catalog_item(
        db,
        organization_id=organization.id,
        name=f"{resource_type}-{suffix}",
        duration_minutes=30,
        bookable=True,
    )
    db.add(item)
    db.flush()
    resources = [
        Resource(
            organization_id=organization.id,
            resource_type=resource_type,
            name=f"{resource_type}-{index}-{suffix}",
            capacity=capacity,
        )
        for index in range(count)
    ]
    db.add_all(resources)
    db.flush()
    db.add(
        ServiceResourceRequirement(
            catalog_item_id=item.id,
            resource_type=resource_type,
            quantity=1,
            required=True,
        )
    )
    db.commit()
    return organization.id, item.id, tuple(resource.id for resource in resources)


def _concurrent_holds(
    engine: object,
    monkeypatch: pytest.MonkeyPatch,
    first: dict[str, object],
    second: dict[str, object],
) -> tuple[str, str]:
    barrier = Barrier(2)
    def pause_before_persist(*args: object, **kwargs: object) -> None:
        try:
            barrier.wait(timeout=0.2)
        except BrokenBarrierError:
            pass
        _PERSIST_ALLOCATIONS(*args, **kwargs)

    monkeypatch.setattr(reservation_service, "_persist_allocations", pause_before_persist)

    def hold(payload: dict[str, object]) -> str:
        with Session(engine) as db:  # type: ignore[arg-type]
            try:
                hold_reservation(db, **payload)  # type: ignore[arg-type]
            except ReservationConflictError:
                return "conflict"
            return "held"

    with ThreadPoolExecutor(max_workers=2) as executor:
        return tuple(executor.map(hold, (first, second)))  # type: ignore[return-value]


def _hold_request(
    *,
    organization_id: int,
    catalog_item_id: int,
    start_datetime: datetime,
    party_size: int,
    duration_minutes: int,
    idempotency_key: str,
    preferred_resource_ids: tuple[int, ...] = (),
) -> dict[str, object]:
    return {
        "organization_id": organization_id,
        "catalog_item_id": catalog_item_id,
        "start_datetime": start_datetime,
        "party_size": party_size,
        "duration_minutes": duration_minutes,
        "idempotency_key": idempotency_key,
        "preferred_resource_ids": preferred_resource_ids,
    }


@pytest.mark.integration
def test_postgres_capacity_locks_serialize_cross_hour_holds(monkeypatch) -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    with Session(engine) as db:
        organization_id, item_id, _ = _seed_reservation_resource(
            db, resource_type="capacity_pool", capacity=10
        )

    first = _hold_request(
        organization_id=organization_id,
        catalog_item_id=item_id,
        start_datetime=datetime(2030, 1, 1, 10, 50, tzinfo=timezone.utc),
        party_size=6,
        duration_minutes=60,
        idempotency_key="capacity-cross-hour-six-a",
    )
    second = _hold_request(
        organization_id=organization_id,
        catalog_item_id=item_id,
        start_datetime=datetime(2030, 1, 1, 11, 0, tzinfo=timezone.utc),
        party_size=6,
        duration_minutes=30,
        idempotency_key="capacity-cross-hour-six-b",
    )
    assert sorted(_concurrent_holds(engine, monkeypatch, first, second)) == ["conflict", "held"]

    first = _hold_request(
        organization_id=organization_id,
        catalog_item_id=item_id,
        start_datetime=datetime(2030, 1, 1, 14, 50, tzinfo=timezone.utc),
        party_size=5,
        duration_minutes=60,
        idempotency_key="capacity-cross-hour-five-a",
    )
    second = _hold_request(
        organization_id=organization_id,
        catalog_item_id=item_id,
        start_datetime=datetime(2030, 1, 1, 15, 0, tzinfo=timezone.utc),
        party_size=5,
        duration_minutes=30,
        idempotency_key="capacity-cross-hour-five-b",
    )
    assert _concurrent_holds(engine, monkeypatch, first, second) == ("held", "held")
    engine.dispose()


@pytest.mark.integration
@pytest.mark.parametrize("resource_type", ("practitioner", "room"))
def test_postgres_resource_locks_allow_distinct_resources_and_reject_same_resource(
    monkeypatch, resource_type: str
) -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    with Session(engine) as db:
        organization_id, item_id, resource_ids = _seed_reservation_resource(
            db, resource_type=resource_type, capacity=1
        )

    same_first = _hold_request(
        organization_id=organization_id,
        catalog_item_id=item_id,
        start_datetime=datetime(2030, 1, 2, 10, 50, tzinfo=timezone.utc),
        party_size=1,
        duration_minutes=60,
        idempotency_key=f"{resource_type}-same-a",
        preferred_resource_ids=(resource_ids[0],),
    )
    same_second = _hold_request(
        organization_id=organization_id,
        catalog_item_id=item_id,
        start_datetime=datetime(2030, 1, 2, 11, 0, tzinfo=timezone.utc),
        party_size=1,
        duration_minutes=30,
        idempotency_key=f"{resource_type}-same-b",
        preferred_resource_ids=(resource_ids[0],),
    )
    assert sorted(_concurrent_holds(engine, monkeypatch, same_first, same_second)) == [
        "conflict",
        "held",
    ]

    with Session(engine) as db:
        organization_id, item_id, resource_ids = _seed_reservation_resource(
            db, resource_type=resource_type, capacity=1, count=2
        )
    different_first = _hold_request(
        organization_id=organization_id,
        catalog_item_id=item_id,
        start_datetime=datetime(2030, 1, 2, 14, 50, tzinfo=timezone.utc),
        party_size=1,
        duration_minutes=60,
        idempotency_key=f"{resource_type}-different-a",
        preferred_resource_ids=(resource_ids[0],),
    )
    different_second = _hold_request(
        organization_id=organization_id,
        catalog_item_id=item_id,
        start_datetime=datetime(2030, 1, 2, 15, 0, tzinfo=timezone.utc),
        party_size=1,
        duration_minutes=30,
        idempotency_key=f"{resource_type}-different-b",
        preferred_resource_ids=(resource_ids[1],),
    )
    assert _concurrent_holds(engine, monkeypatch, different_first, different_second) == (
        "held",
        "held",
    )
    engine.dispose()
