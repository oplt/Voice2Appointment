"""Small database-specific value adaptations kept out of domain queries."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session


def datetime_comparison_value(db: Session, value: datetime) -> datetime:
    """Bind a UTC instant for a timestamp comparison on the active database.

    PostgreSQL receives the aware instant required by ``TIMESTAMP WITH TIME
    ZONE``. SQLite has no timezone-aware timestamp storage, so its test adapter
    uses the equivalent naive UTC representation.
    """
    utc_value = value.astimezone(timezone.utc)
    if db.get_bind().dialect.name == "sqlite":
        return utc_value.replace(tzinfo=None)
    return utc_value
