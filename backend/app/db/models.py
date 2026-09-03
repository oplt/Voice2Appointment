"""ORM models shared by FastAPI modules (SQLAlchemy 2.0 mapped style)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.core.types import EncryptedText
from app.db.base import Base
from app.db.session import SessionLocal

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


class User(Base):
    __tablename__ = "res_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    image_file: Mapped[str] = mapped_column(
        String(255), nullable=False, default="default.jpg"
    )
    password: Mapped[str] = mapped_column(String(128), nullable=False)

    twilio_account_sid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    twilio_auth_token: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    twilio_phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    deepgram_api_key: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    twilio_last_synced_at: Mapped[datetime | None] = mapped_column(
        TZDateTime, nullable=True
    )

    call_sessions: Mapped[list[CallSession]] = relationship(
        "CallSession", back_populates="user", lazy="select"
    )
    appointments: Mapped[list[Appointment]] = relationship(
        "Appointment", back_populates="user", lazy="select"
    )
    google_calendar_auth: Mapped[GoogleCalendarAuth | None] = relationship(
        "GoogleCalendarAuth",
        back_populates="user",
        lazy="select",
        uselist=False,
    )


class GoogleCalendarAuth(TimestampMixin, Base):
    __tablename__ = "google_calendar_auth"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("res_user.id"), nullable=False, index=True
    )

    account_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="google")
    credentials_json: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    token_json: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    scopes: Mapped[str | None] = mapped_column(Text, nullable=True)
    calendar_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    time_zone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(
        TZDateTime, nullable=True
    )
    revoked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    embedded_link: Mapped[str | None] = mapped_column(String(500), nullable=True)

    user: Mapped[User] = relationship("User", back_populates="google_calendar_auth")


class CallSession(Base):
    __tablename__ = "callsession"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("res_user.id"), nullable=False, index=True
    )
    call_sid: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    stream_sid: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    recording_sid: Mapped[str | None] = mapped_column(
        String(64), index=True, nullable=True
    )
    recording_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recording_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    recording_downloaded_at: Mapped[datetime | None] = mapped_column(
        TZDateTime, nullable=True
    )
    from_number: Mapped[str | None] = mapped_column(String(32), index=True)
    to_number: Mapped[str | None] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active", index=True
    )
    data: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE, nullable=False, server_default=text("'{}'")
    )
    started_at: Mapped[datetime] = mapped_column(
        TZDateTime, default=_utcnow, index=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(TZDateTime, index=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped[User] = relationship("User", back_populates="call_sessions")
    appointment: Mapped[Appointment | None] = relationship(
        "Appointment", back_populates="callsession", uselist=False
    )

    def __repr__(self) -> str:
        return (
            f"<CallSession call_sid={self.call_sid} "
            f"from={self.from_number} to={self.to_number}>"
        )

    @classmethod
    def create(
        cls,
        call_sid: str,
        from_number: str | None,
        to_number: str | None,
        user_id: int,
        data: dict[str, Any] | None = None,
        *,
        session: Any | None = None,
    ) -> CallSession:
        db = session
        owns_session = False
        if db is None:
            if SessionLocal is None:
                raise RuntimeError("DATABASE_URL is not configured")
            db = SessionLocal()
            owns_session = True
        try:
            row = cls(
                user_id=user_id,
                call_sid=call_sid,
                from_number=from_number,
                to_number=to_number,
                data=data or {},
                expires_at=_utcnow()
                + timedelta(minutes=settings.call_expires_in),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row
        finally:
            if owns_session:
                db.close()

    def update(self, session: Any | None = None, **kwargs: Any) -> CallSession:
        db = session
        owns_session = False
        if db is None:
            if SessionLocal is None:
                raise RuntimeError("DATABASE_URL is not configured")
            db = SessionLocal()
            owns_session = True
        try:
            for key, value in kwargs.items():
                if hasattr(self, key):
                    setattr(self, key, value)
            db.add(self)
            db.commit()
            db.refresh(self)
            return self
        finally:
            if owns_session:
                db.close()


class Appointment(TimestampMixin, Base):
    __tablename__ = "appointment"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_appointment_idempotency_key"),
        Index("ix_appointment_user_start", "user_id", "start_datetime"),
        Index("ix_appointment_user_status_start", "user_id", "status", "start_datetime"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("res_user.id"), nullable=False, index=True
    )
    callsession_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("callsession.id", ondelete="SET NULL"),
        unique=True,
        nullable=True,
        index=True,
    )

    summary: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # UTC instant + IANA name in `timezone`
    start_datetime: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    end_datetime: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False, default="UTC")

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    google_calendar_event_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    google_calendar_link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)

    stored_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    audio_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)

    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    client_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship("User", back_populates="appointments")
    callsession: Mapped[CallSession | None] = relationship(
        "CallSession", back_populates="appointment", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Appointment {self.summary} on {self.start_datetime}>"


class TwilioCallAnalytics(TimestampMixin, Base):
    __tablename__ = "twilio_call_analytics"
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_twilio_analytics_user_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("res_user.id"), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    call_data: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE, nullable=False, server_default=text("'{}'")
    )
    processed_metrics: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE, nullable=False, server_default=text("'{}'")
    )

    def __repr__(self) -> str:
        return f"<TwilioCallAnalytics user={self.user_id} date={self.date}>"


class TwilioCall(TimestampMixin, Base):
    """Normalized Twilio call row (tenant-scoped, upsert by sid)."""

    __tablename__ = "twilio_call"
    __table_args__ = (
        UniqueConstraint("user_id", "sid", name="uq_twilio_call_user_sid"),
        Index("ix_twilio_call_user_start", "user_id", "start_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("res_user.id"), nullable=False, index=True
    )
    sid: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    from_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    price_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    direction: Mapped[str | None] = mapped_column(String(32), nullable=True)

    def __repr__(self) -> str:
        return f"<TwilioCall sid={self.sid} user={self.user_id}>"
