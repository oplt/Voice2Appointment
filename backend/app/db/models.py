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
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

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
    auth_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    password_reset_token_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    password_reset_expires_at: Mapped[datetime | None] = mapped_column(
        TZDateTime, nullable=True
    )
    password_reset_consumed_at: Mapped[datetime | None] = mapped_column(
        TZDateTime, nullable=True
    )

    twilio_account_sid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    twilio_auth_token: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    twilio_phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    twilio_phone_e164: Mapped[str | None] = mapped_column(
        String(20), nullable=True, unique=True, index=True
    )
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    twilio_last_synced_at: Mapped[datetime | None] = mapped_column(
        TZDateTime, nullable=True
    )
    twilio_sync_page_token: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    twilio_sync_window_started_at: Mapped[datetime | None] = mapped_column(
        TZDateTime, nullable=True
    )
    twilio_sync_window_high_water: Mapped[datetime | None] = mapped_column(
        TZDateTime, nullable=True
    )
    twilio_active_refresh_cursor: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    twilio_active_refresh_due_at: Mapped[datetime | None] = mapped_column(
        TZDateTime, nullable=True
    )
    cache_calendar_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    cache_dashboard_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    cache_analytics_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    cache_settings_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
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

    @validates("twilio_phone_number")
    def _sync_twilio_phone_e164(self, _key: str, value: str | None) -> str | None:
        from app.telephony.phones import canonical_e164

        cleaned = (value or "").strip() or None
        canonical = canonical_e164(cleaned)
        if cleaned is not None and canonical is None:
            raise ValueError("twilio_phone_number must be a valid E.164 number")
        self.twilio_phone_e164 = canonical
        return cleaned


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
    __table_args__ = (
        Index("ix_callsession_user_started", "user_id", "started_at"),
    )

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
    stream_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stream_token_ciphertext: Mapped[str | None] = mapped_column(
        EncryptedText, nullable=True
    )
    stream_token_expires_at: Mapped[datetime | None] = mapped_column(
        TZDateTime, nullable=True
    )
    stream_token_consumed_at: Mapped[datetime | None] = mapped_column(
        TZDateTime, nullable=True
    )
    from_number: Mapped[str | None] = mapped_column(String(32), index=True)
    to_number: Mapped[str | None] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(
        String(32), default="active", server_default="active", index=True
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
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    terminal_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_purged_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    transfer_attempted_at: Mapped[datetime | None] = mapped_column(
        TZDateTime, nullable=True
    )

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
        UniqueConstraint(
            "user_id",
            "google_calendar_event_id",
            name="uq_appointment_user_google_event",
        ),
        Index("ix_appointment_user_start", "user_id", "start_datetime"),
        Index("ix_appointment_user_start_id", "user_id", "start_datetime", "id"),
        Index("ix_appointment_user_created", "user_id", "created_at"),
        Index("ix_appointment_user_status_start", "user_id", "status", "start_datetime"),
        # Overlap-friendly: covers validate_slot conflict query shape.
        Index(
            "ix_appointment_overlap",
            "user_id", "status", "start_datetime", "end_datetime",
        ),
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
    # pending_provider → provider write not finalized; confirmed/cancelled/failed otherwise
    provider_sync_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="confirmed",
        server_default="confirmed",
    )
    provider_operation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_operation_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON_TYPE, nullable=True
    )
    provider_attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    provider_last_error_code: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    provider_next_retry_at: Mapped[datetime | None] = mapped_column(
        TZDateTime, nullable=True
    )
    provider_calendar_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default="primary", server_default="primary"
    )

    stored_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    audio_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)

    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    client_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmation_sent_at: Mapped[datetime | None] = mapped_column(
        TZDateTime, nullable=True
    )
    transcript_purged_at: Mapped[datetime | None] = mapped_column(
        TZDateTime, nullable=True
    )

    user: Mapped[User] = relationship("User", back_populates="appointments")
    callsession: Mapped[CallSession | None] = relationship(
        "CallSession", back_populates="appointment", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Appointment {self.summary} on {self.start_datetime}>"


class NotificationDelivery(TimestampMixin, Base):
    """Idempotent notification audit without message body (P6-01)."""

    __tablename__ = "notification_delivery"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_notification_delivery_idem"),
        Index(
            "ix_notification_delivery_user_appt",
            "user_id",
            "appointment_id",
            "kind",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("res_user.id"), nullable=False, index=True
    )
    appointment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("appointment.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    channel: Mapped[str] = mapped_column(
        String(16), nullable=False, default="email", server_default="email"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    leased_until: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<NotificationDelivery {self.kind} appt={self.appointment_id} {self.status}>"


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
        Index("ix_twilio_call_user_status", "user_id", "status"),
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
    status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    provider_updated_at: Mapped[datetime | None] = mapped_column(
        TZDateTime, nullable=True
    )

    def __repr__(self) -> str:
        return f"<TwilioCall sid={self.sid} user={self.user_id}>"


class BookingFunnelEvent(Base):
    """Append-only, idempotent booking funnel history."""

    __tablename__ = "booking_funnel_event"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_booking_funnel_event_key"),
        Index("ix_booking_funnel_event_user_time", "user_id", "occurred_at"),
        Index("ix_booking_funnel_event_call_stage", "call_session_id", "stage"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("res_user.id"), nullable=False)
    call_session_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("callsession.id"), nullable=True)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    occurred_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False, default=_utcnow)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)


from app.core.cache_generation import register_cache_generation_events  # noqa: E402

register_cache_generation_events()
