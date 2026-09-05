"""Advance tenant cache generations in the same transaction as domain writes."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

_PENDING = "cache_generation_pending"
_APPLIED = "cache_generation_applied"
_registered = False


def _invalidations(instance: Any) -> tuple[int | None, frozenset[str]]:
    from app.db.models import Appointment, CallSession, GoogleCalendarAuth, TwilioCall, User

    if isinstance(instance, Appointment):
        return instance.user_id, frozenset({"calendar", "dashboard", "analytics"})
    if isinstance(instance, CallSession):
        return instance.user_id, frozenset({"dashboard", "analytics"})
    if isinstance(instance, TwilioCall):
        return instance.user_id, frozenset({"analytics", "dashboard"})
    if isinstance(instance, GoogleCalendarAuth):
        return instance.user_id, frozenset({"calendar", "dashboard"})
    if isinstance(instance, User):
        if instance in inspect(instance).session.new:
            return instance.id, frozenset({"settings", "dashboard"})
        tracked = (
            "username",
            "email",
            "image_file",
            "twilio_account_sid",
            "twilio_auth_token",
            "twilio_phone_number",
            "twilio_phone_e164",
            "config_json",
        )
        changed = any(inspect(instance).attrs[name].history.has_changes() for name in tracked)
        return (
            (instance.id, frozenset({"settings", "dashboard"}))
            if changed
            else (None, frozenset())
        )
    return None, frozenset()


def _before_flush(session: Session, _context: Any, _instances: Any) -> None:
    pending: set[tuple[int, str]] = session.info.setdefault(_PENDING, set())
    applied: set[tuple[int, str]] = session.info.setdefault(_APPLIED, set())
    for instance in session.new | session.dirty | session.deleted:
        user_id, namespaces = _invalidations(instance)
        if user_id is None:
            continue
        for namespace in namespaces:
            pair = (int(user_id), namespace)
            if pair not in applied:
                pending.add(pair)


def _after_flush(session: Session, _context: Any) -> None:
    from app.db.models import User

    pending: set[tuple[int, str]] = session.info.get(_PENDING, set())
    if not pending:
        return
    by_user: dict[int, set[str]] = defaultdict(set)
    for user_id, namespace in pending:
        by_user[user_id].add(namespace)
    columns = {
        "calendar": User.__table__.c.cache_calendar_version,
        "dashboard": User.__table__.c.cache_dashboard_version,
        "analytics": User.__table__.c.cache_analytics_version,
        "settings": User.__table__.c.cache_settings_version,
    }
    for user_id, namespaces in by_user.items():
        values = {columns[name]: columns[name] + 1 for name in namespaces}
        session.execute(
            User.__table__.update().where(User.__table__.c.id == user_id).values(values)
        )
    session.info.setdefault(_APPLIED, set()).update(pending)
    pending.clear()


def advance_cache_generations(
    session: Session, user_id: int, *namespaces: str
) -> None:
    """Stage O(1) durable invalidation inside the caller-owned transaction."""
    from app.db.models import User

    columns = {
        "calendar": User.__table__.c.cache_calendar_version,
        "dashboard": User.__table__.c.cache_dashboard_version,
        "analytics": User.__table__.c.cache_analytics_version,
        "settings": User.__table__.c.cache_settings_version,
    }
    values = {
        columns[name]: columns[name] + 1
        for name in set(namespaces)
        if name in columns
    }
    if not values:
        return
    session.execute(
        User.__table__.update().where(User.__table__.c.id == user_id).values(values)
    )


def _clear(session: Session) -> None:
    session.info.pop(_PENDING, None)
    session.info.pop(_APPLIED, None)


def register_cache_generation_events() -> None:
    global _registered
    if _registered:
        return
    event.listen(Session, "before_flush", _before_flush)
    event.listen(Session, "after_flush_postexec", _after_flush)
    event.listen(Session, "after_commit", _clear)
    event.listen(Session, "after_rollback", _clear)
    _registered = True
