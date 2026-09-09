"""Shared SQLAlchemy column types and timestamp mixin."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")

# Real-world instants are stored timezone-aware (UTC preferred).
TZDateTime = DateTime(timezone=True)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )
