"""Page-transactional, resumable Twilio call synchronization."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select
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
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise RuntimeError(f"Twilio upsert does not support database dialect {dialect}")

    stmt = insert(TwilioCall).values(rows)
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
    conflict = (
        {"constraint": "uq_twilio_call_user_sid"}
        if dialect == "postgresql"
        else {"index_elements": ["user_id", "sid"]}
    )
    stmt = stmt.on_conflict_do_update(**conflict, set_=update_cols, where=newer)
    return len(db.scalars(stmt.returning(TwilioCall.id)).all())


def _locked_user(db: Session, user_id: int) -> User:
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise ValueError("user not found")
    return user


def _advance_high_water(user: User, records: list[dict[str, Any]]) -> None:
    high_water = _aware(user.twilio_sync_window_high_water)
    for item in records:
        started = _parse_time(item.get("start_time"))
        if started is not None and (high_water is None or started > high_water):
            high_water = started
    user.twilio_sync_window_high_water = high_water


def _sync_pages(
    db: Session,
    provider: TwilioProvider,
    user_id: int,
    *,
    page_size: int,
    page_budget: int,
    lookback_seconds: int,
) -> tuple[int, int, bool]:
    from app.core.cache_generation import advance_cache_generations

    synced = 0
    pages = 0
    exhausted = False
    for _ in range(page_budget):
        user = _locked_user(db, user_id)
        if user.twilio_sync_window_started_at is None:
            stable = _aware(user.twilio_last_synced_at)
            user.twilio_sync_window_started_at = (
                stable - timedelta(seconds=lookback_seconds) if stable else None
            )
            user.twilio_sync_window_high_water = stable
        if hasattr(provider, "fetch_call_page"):
            page = provider.fetch_call_page(
                start_time_after=_aware(user.twilio_sync_window_started_at),
                page_size=page_size,
                page_token=user.twilio_sync_page_token,
            )
        else:
            # Retain the service injection seam used by older integrations.
            # Production providers always use the explicit one-page API above.
            records = provider.fetch_calls(
                limit=page_size,
                start_time_after=_aware(user.twilio_sync_window_started_at),
                page_size=page_size,
                max_pages=1,
            )
            page = CallPage(records=records, next_page_token=None, exhausted=True)
        changed = upsert_twilio_calls(db, user_id, page.records)
        _advance_high_water(user, page.records)
        user.twilio_sync_page_token = page.next_page_token
        exhausted = page.exhausted
        if exhausted:
            user.twilio_last_synced_at = user.twilio_sync_window_high_water
            user.twilio_sync_page_token = None
            user.twilio_sync_window_started_at = None
            user.twilio_sync_window_high_water = None
        advance_cache_generations(db, user_id, "analytics", "dashboard")
        db.commit()
        synced += changed
        pages += 1
        if exhausted:
            break
    return synced, pages, exhausted


def _refresh_active_calls(
    db: Session, provider: TwilioProvider, user_id: int, *, batch_size: int, interval: int
) -> int:
    from app.core.cache_generation import advance_cache_generations

    now = datetime.now(timezone.utc)
    user = _locked_user(db, user_id)
    due = _aware(user.twilio_active_refresh_due_at)
    if due is not None and due > now:
        db.rollback()
        return 0
    query = select(TwilioCall.sid).where(
        TwilioCall.user_id == user_id,
        or_(TwilioCall.status.is_(None), TwilioCall.status.notin_(tuple(TERMINAL_CALL_STATUSES))),
    )
    if user.twilio_active_refresh_cursor:
        query = query.where(TwilioCall.sid > user.twilio_active_refresh_cursor)
    sids = list(db.scalars(query.order_by(TwilioCall.sid).limit(batch_size + 1)).all())
    batch = sids[:batch_size]
    records = provider.fetch_calls_by_sids(batch) if batch else []
    changed = upsert_twilio_calls(db, user_id, records)
    if len(sids) > batch_size:
        user.twilio_active_refresh_cursor = batch[-1]
        user.twilio_active_refresh_due_at = now
    else:
        user.twilio_active_refresh_cursor = None
        user.twilio_active_refresh_due_at = now + timedelta(seconds=interval)
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

    provider = provider_factory(account_sid=account_sid, auth_token=auth_token)
    page_size = settings.twilio_sync_page_size
    page_budget = settings.twilio_sync_max_pages
    if limit is not None:
        page_budget = max(1, min(page_budget, (limit + page_size - 1) // page_size))
    synced, pages, exhausted = _sync_pages(
        db,
        provider,
        user_id,
        page_size=page_size,
        page_budget=page_budget,
        lookback_seconds=settings.twilio_sync_lookback_seconds,
    )
    refreshed = _refresh_active_calls(
        db,
        provider,
        user_id,
        batch_size=settings.twilio_active_refresh_batch_size,
        interval=settings.twilio_active_refresh_interval_seconds,
    )
    return {
        "message": "Twilio data synced",
        "synced": synced,
        "pages": pages,
        "has_more": not exhausted,
        "active_refreshed": refreshed,
    }
