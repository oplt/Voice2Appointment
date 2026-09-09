"""Page-transactional, resumable Twilio call synchronization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from app.db.models import TwilioCall, User
from app.telephony.providers.twilio import (
    TERMINAL_CALL_STATUSES,
    CallPage,
    TwilioProvider,
)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _aware(value)
    if not isinstance(value, str) or not value:
        return None
    try:
        return _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _normalize_row(user_id: int, item: dict[str, Any]) -> dict[str, Any] | None:
    sid = str(item.get("sid") or "").strip()
    if not sid:
        return None
    now = datetime.now(timezone.utc)
    return {
        "user_id": user_id,
        "sid": sid,
        "from_number": item.get("from"),
        "to_number": item.get("to"),
        "start_time": _parse_time(item.get("start_time")),
        "duration_sec": item.get("duration_sec"),
        "price": item.get("price"),
        "price_unit": item.get("price_unit"),
        "direction": item.get("direction"),
        "status": item.get("status"),
        "provider_updated_at": _parse_time(item.get("provider_updated_at")),
        "created_at": now,
        "updated_at": now,
    }


def upsert_twilio_calls(
    db: Session, user_id: int, call_data: list[dict[str, Any]]
) -> int:
    """Execute one freshness-aware batch statement; the caller owns commit."""
    rows_by_sid: dict[str, dict[str, Any]] = {}
    for item in call_data:
        row = _normalize_row(user_id, item)
        if row is None:
            continue
        existing = rows_by_sid.get(row["sid"])
        if existing is None or (
            _aware(row["provider_updated_at"]) or datetime.min.replace(tzinfo=timezone.utc)
        ) > (
            _aware(existing["provider_updated_at"])
            or datetime.min.replace(tzinfo=timezone.utc)
        ):
            rows_by_sid[row["sid"]] = row
    rows = list(rows_by_sid.values())
    if not rows:
        return 0

    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as postgres_insert

        stmt: Any = postgres_insert(TwilioCall).values(rows)
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        stmt = sqlite_insert(TwilioCall).values(rows)
    else:
        raise RuntimeError(f"Twilio upsert does not support database dialect {dialect}")

    excluded = stmt.excluded
    terminals = tuple(TERMINAL_CALL_STATUSES)
    incoming_terminal = excluded.status.in_(terminals)
    existing_nonterminal = or_(
        TwilioCall.status.is_(None), TwilioCall.status.notin_(terminals)
    )
    # A terminal state is sticky: a later incomplete provider response must not
    # turn a completed call back into an active one.  Within that boundary,
    # Twilio's date_updated is the sole ordering value.  Without that value we
    # can only safely make the monotonic nonterminal -> terminal transition.
    status_can_advance = or_(existing_nonterminal, incoming_terminal)
    newer = and_(
        status_can_advance,
        or_(
            and_(
                excluded.provider_updated_at.is_not(None),
                or_(
                    TwilioCall.provider_updated_at.is_(None),
                    excluded.provider_updated_at > TwilioCall.provider_updated_at,
                ),
            ),
            and_(
                excluded.provider_updated_at == TwilioCall.provider_updated_at,
                incoming_terminal,
                existing_nonterminal,
            ),
            and_(
                excluded.provider_updated_at.is_(None),
                TwilioCall.provider_updated_at.is_(None),
                existing_nonterminal,
            ),
        ),
    )
    update_cols = {
        "from_number": func.coalesce(excluded.from_number, TwilioCall.from_number),
        "to_number": func.coalesce(excluded.to_number, TwilioCall.to_number),
        "start_time": func.coalesce(excluded.start_time, TwilioCall.start_time),
        "duration_sec": func.coalesce(excluded.duration_sec, TwilioCall.duration_sec),
        "price": func.coalesce(excluded.price, TwilioCall.price),
        "price_unit": func.coalesce(excluded.price_unit, TwilioCall.price_unit),
        "direction": func.coalesce(excluded.direction, TwilioCall.direction),
        "status": func.coalesce(excluded.status, TwilioCall.status),
        "provider_updated_at": func.coalesce(
            excluded.provider_updated_at, TwilioCall.provider_updated_at
        ),
        "updated_at": excluded.updated_at,
    }
    if dialect == "postgresql":
        stmt = stmt.on_conflict_do_update(
            constraint="uq_twilio_call_user_sid", set_=update_cols, where=newer
        )
    else:
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "sid"], set_=update_cols, where=newer
        )
    return len(db.scalars(stmt.returning(TwilioCall.id)).all())


@dataclass(frozen=True)
class _PageSnapshot:
    window_started_at: datetime | None
    page_token: str | None
    high_water: datetime | None


@dataclass(frozen=True)
class _ActiveSnapshot:
    cursor: str | None
    sids: list[str]


def _acquire_sync_lease(
    db: Session, user_id: int, *, lease_seconds: int
) -> str | None:
    """Acquire a durable lease without retaining a row lock during I/O."""
    now = datetime.now(timezone.utc)
    token = uuid4().hex
    acquired = db.execute(
        update(User)
        .where(
            User.id == user_id,
            or_(
                User.twilio_sync_lease_expires_at.is_(None),
                User.twilio_sync_lease_expires_at <= now,
            ),
        )
        .values(
            twilio_sync_lease_token=token,
            twilio_sync_lease_expires_at=now + timedelta(seconds=lease_seconds),
        )
        .returning(User.id)
        .execution_options(synchronize_session=False)
    ).scalar_one_or_none()
    db.commit()
    if acquired is not None:
        return token
    user_exists = db.scalar(select(User.id).where(User.id == user_id))
    db.rollback()
    if user_exists is None:
        raise ValueError("user not found")
    return None


def _release_sync_lease(db: Session, user_id: int, token: str) -> None:
    db.execute(
        update(User)
        .where(User.id == user_id, User.twilio_sync_lease_token == token)
        .values(twilio_sync_lease_token=None, twilio_sync_lease_expires_at=None)
        .execution_options(synchronize_session=False)
    )
    db.commit()


def _lease_user(db: Session, user_id: int, token: str) -> User | None:
    now = datetime.now(timezone.utc)
    return db.scalar(
        select(User)
        .where(
            User.id == user_id,
            User.twilio_sync_lease_token == token,
            User.twilio_sync_lease_expires_at > now,
        )
        .with_for_update()
    )


def _advance_high_water(user: User, records: list[dict[str, Any]]) -> None:
    high_water = _aware(user.twilio_sync_window_high_water)
    for item in records:
        started = _parse_time(item.get("start_time"))
        if started is not None and (high_water is None or started > high_water):
            high_water = started
    user.twilio_sync_window_high_water = high_water


def _page_snapshot(
    db: Session,
    user_id: int,
    token: str,
    *,
    lookback_seconds: int,
) -> _PageSnapshot | None:
    user = _lease_user(db, user_id, token)
    if user is None:
        db.rollback()
        return None
    if user.twilio_sync_window_started_at is None:
        stable = _aware(user.twilio_last_synced_at)
        user.twilio_sync_window_started_at = (
            stable - timedelta(seconds=lookback_seconds) if stable else None
        )
        user.twilio_sync_window_high_water = stable
    snapshot = _PageSnapshot(
        window_started_at=_aware(user.twilio_sync_window_started_at),
        page_token=user.twilio_sync_page_token,
        high_water=_aware(user.twilio_sync_window_high_water),
    )
    db.commit()
    return snapshot


def _finalize_page(
    db: Session,
    user_id: int,
    token: str,
    snapshot: _PageSnapshot,
    page: CallPage,
    *,
    lease_seconds: int,
) -> int | None:
    from app.core.cache_generation import advance_cache_generations

    user = _lease_user(db, user_id, token)
    if user is None or (
        _aware(user.twilio_sync_window_started_at) != snapshot.window_started_at
        or user.twilio_sync_page_token != snapshot.page_token
        or _aware(user.twilio_sync_window_high_water) != snapshot.high_water
    ):
        db.rollback()
        return None
    changed = upsert_twilio_calls(db, user_id, page.records)
    _advance_high_water(user, page.records)
    user.twilio_sync_page_token = page.next_page_token
    if page.exhausted:
        user.twilio_last_synced_at = user.twilio_sync_window_high_water
        user.twilio_sync_page_token = None
        user.twilio_sync_window_started_at = None
        user.twilio_sync_window_high_water = None
    user.twilio_sync_lease_expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=lease_seconds
    )
    advance_cache_generations(db, user_id, "analytics", "dashboard")
    db.commit()
    return changed


def _sync_pages(
    db: Session,
    provider: TwilioProvider,
    user_id: int,
    *,
    page_size: int,
    page_budget: int,
    lookback_seconds: int,
    lease_token: str,
    lease_seconds: int,
) -> tuple[int, int, bool]:
    synced = 0
    pages = 0
    exhausted = False
    for _ in range(page_budget):
        snapshot = _page_snapshot(
            db,
            user_id,
            lease_token,
            lookback_seconds=lookback_seconds,
        )
        if snapshot is None:
            break
        # The snapshot transaction has committed before the provider request.
        if hasattr(provider, "fetch_call_page"):
            page = provider.fetch_call_page(
                start_time_after=snapshot.window_started_at,
                page_size=page_size,
                page_token=snapshot.page_token,
            )
        else:
            # Retain the service injection seam used by older integrations.
            # Production providers always use the explicit one-page API above.
            records = provider.fetch_calls(
                limit=page_size,
                start_time_after=snapshot.window_started_at,
                page_size=page_size,
                max_pages=1,
            )
            page = CallPage(records=records, next_page_token=None, exhausted=True)
        changed = _finalize_page(
            db,
            user_id,
            lease_token,
            snapshot,
            page,
            lease_seconds=lease_seconds,
        )
        if changed is None:
            break
        exhausted = page.exhausted
        synced += changed
        pages += 1
        if exhausted:
            break
    return synced, pages, exhausted


def _refresh_active_calls(
    db: Session,
    provider: TwilioProvider,
    user_id: int,
    *,
    batch_size: int,
    interval: int,
    lease_token: str,
    lease_seconds: int,
) -> int:
    from app.core.cache_generation import advance_cache_generations

    now = datetime.now(timezone.utc)
    user = _lease_user(db, user_id, lease_token)
    if user is None:
        db.rollback()
        return 0
    due = _aware(user.twilio_active_refresh_due_at)
    if due is not None and due > now:
        db.commit()
        return 0
    query = select(TwilioCall.sid).where(
        TwilioCall.user_id == user_id,
        or_(TwilioCall.status.is_(None), TwilioCall.status.notin_(tuple(TERMINAL_CALL_STATUSES))),
    )
    if user.twilio_active_refresh_cursor:
        query = query.where(TwilioCall.sid > user.twilio_active_refresh_cursor)
    sids = list(db.scalars(query.order_by(TwilioCall.sid).limit(batch_size + 1)).all())
    batch = sids[:batch_size]
    snapshot = _ActiveSnapshot(cursor=user.twilio_active_refresh_cursor, sids=batch)
    db.commit()
    # Fetching active calls is intentionally outside the checkpoint transaction.
    records = provider.fetch_calls_by_sids(batch) if batch else []
    user = _lease_user(db, user_id, lease_token)
    if user is None or user.twilio_active_refresh_cursor != snapshot.cursor:
        db.rollback()
        return 0
    changed = upsert_twilio_calls(db, user_id, records)
    if len(sids) > batch_size:
        user.twilio_active_refresh_cursor = batch[-1]
        user.twilio_active_refresh_due_at = now
    else:
        user.twilio_active_refresh_cursor = None
        user.twilio_active_refresh_due_at = datetime.now(timezone.utc) + timedelta(
            seconds=interval
        )
    user.twilio_sync_lease_expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=lease_seconds
    )
    if records:
        advance_cache_generations(db, user_id, "analytics", "dashboard")
    db.commit()
    return changed


def fetch_and_store_twilio(
    db: Session,
    *,
    user_id: int,
    account_sid: str,
    auth_token: str,
    limit: int | None = None,
    provider_factory: type[TwilioProvider] = TwilioProvider,
) -> dict[str, Any]:
    from app.core.config import settings

    lease_token = _acquire_sync_lease(
        db,
        user_id,
        lease_seconds=settings.twilio_sync_lease_seconds,
    )
    if lease_token is None:
        return {
            "message": "Twilio sync already in progress",
            "synced": 0,
            "pages": 0,
            "has_more": True,
            "active_refreshed": 0,
        }
    page_size = settings.twilio_sync_page_size
    page_budget = settings.twilio_sync_max_pages
    if limit is not None:
        page_budget = max(1, min(page_budget, (limit + page_size - 1) // page_size))
    try:
        provider = provider_factory(account_sid=account_sid, auth_token=auth_token)
        synced, pages, exhausted = _sync_pages(
            db,
            provider,
            user_id,
            page_size=page_size,
            page_budget=page_budget,
            lookback_seconds=settings.twilio_sync_lookback_seconds,
            lease_token=lease_token,
            lease_seconds=settings.twilio_sync_lease_seconds,
        )
        refreshed = _refresh_active_calls(
            db,
            provider,
            user_id,
            batch_size=settings.twilio_active_refresh_batch_size,
            interval=settings.twilio_active_refresh_interval_seconds,
            lease_token=lease_token,
            lease_seconds=settings.twilio_sync_lease_seconds,
        )
    finally:
        _release_sync_lease(db, user_id, lease_token)
    return {
        "message": "Twilio data synced",
        "synced": synced,
        "pages": pages,
        "has_more": not exhausted,
        "active_refreshed": refreshed,
    }
