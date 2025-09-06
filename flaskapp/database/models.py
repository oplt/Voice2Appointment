from datetime import datetime, timedelta, timezone
from flask_login import UserMixin
from config import settings
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import text
from .. import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class User(db.Model, UserMixin):
    __tablename__ = 'res_user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    image_file = db.Column(db.String(255), nullable=False, default='default.jpg')
    password = db.Column(db.String(128), nullable=False)

    twilio_account_sid = db.Column(db.String(255), nullable=True)
    twilio_auth_token = db.Column(db.String(255), nullable=True)
    twilio_phone_number = db.Column(db.String(20), nullable=True)
    deepgram_api_key = db.Column(db.String(255), nullable=True)
    config_json = db.Column(db.Text, nullable=True)

    call_sessions = db.relationship('CallSession', backref='user', lazy=True)
    appointments = db.relationship('Appointment', backref='user', lazy=True)
    google_calendar_auth = db.relationship('GoogleCalendarAuth', backref='user', lazy=True, uselist=False)


class GoogleCalendarAuth(db.Model, TimestampMixin):
    __tablename__ = 'google_calendar_auth'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('res_user.id'), nullable=False, index=True)

    # Identity
    account_email = db.Column(db.String(255), nullable=True)
    provider = db.Column(db.String(50), nullable=False, default='google')
    credentials_json = db.Column(db.Text, nullable=True)
    token_json = db.Column(db.Text, nullable=True)
    scopes = db.Column(db.Text, nullable=True)
    calendar_id = db.Column(db.String(255), nullable=True)
    time_zone = db.Column(db.String(100), nullable=True)
    access_token_expires_at = db.Column(db.DateTime, nullable=True)
    revoked = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(32), nullable=True)
    embedded_link = db.Column(db.String(500), nullable=True)


class CallSession(db.Model):
    __tablename__ = 'callsession'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('res_user.id'), nullable=False, index=True)
    call_sid = db.Column(db.String(64), unique=True, index=True, nullable=False)
    stream_sid = db.Column(db.String(64), index=True, nullable=True)       # from "start" event
    recording_sid = db.Column(db.String(64), index=True, nullable=True)
    recording_url = db.Column(db.String(500), nullable=True)
    recording_path = db.Column(db.Text, nullable=True)
    recording_downloaded_at = db.Column(db.DateTime, nullable=True)
    from_number = db.Column(db.String(32), index=True)
    to_number = db.Column(db.String(32), index=True)
    status = db.Column(db.String(16), default='active', index=True)        # active | ended | expired | error
    data = db.Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    ended_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, index=True)
    duration_seconds = db.Column(db.Integer, nullable=True)

    appointment = db.relationship(
        "Appointment",
        back_populates="callsession",
        uselist=False
    )

    def __repr__(self):
        return f"<CallSession call_sid={self.call_sid} from={self.from_number} to={self.to_number}>"

    @classmethod
    def create(cls, call_sid, from_number, to_number, user_id, data=None):
        session = cls(
            user_id=user_id,
            call_sid=call_sid,
            from_number=from_number,
            to_number=to_number,
            data=data or {},
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.CALL_EXPIRES_IN),
        )
        db.session.add(session)
        db.session.commit()
        return session

    def update(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        db.session.commit()
        return self


class Appointment(TimestampMixin, db.Model):
    __tablename__ = 'appointment'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('res_user.id'), nullable=False, index=True)
    callsession_id = db.Column(db.Integer,db.ForeignKey("callsession.id", ondelete="SET NULL"), unique=True, nullable=True, index=True)

    # Appointment details
    summary = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    start_datetime = db.Column(db.DateTime, nullable=False)
    end_datetime = db.Column(db.DateTime, nullable=False)
    timezone = db.Column(db.String(100), nullable=False, default='UTC')

    # Status and tracking
    status = db.Column(db.String(32), nullable=False, default='pending')  # pending, confirmed, cancelled, completed
    google_calendar_event_id = db.Column(db.String(255), nullable=True)
    google_calendar_link = db.Column(db.String(500), nullable=True)

    # Audio recording and transcript
    stored_filename = db.Column(db.String(255), nullable=True)
    mime_type = db.Column(db.String(100), nullable=True)
    audio_data = db.Column(db.LargeBinary, nullable=True)
    transcript = db.Column(db.Text, nullable=True)

    # Client information
    client_name = db.Column(db.String(255), nullable=True)
    client_phone = db.Column(db.String(32), nullable=True)
    client_email = db.Column(db.String(255), nullable=True)

    # Notes and additional info
    notes = db.Column(db.Text, nullable=True)
    reminder_sent = db.Column(db.Boolean, default=False)

    callsession = db.relationship("CallSession", back_populates="appointment", passive_deletes=True)

    def __repr__(self):
        return f'<Appointment {self.summary} on {self.start_datetime}>'

    @classmethod
    def create_from_call(cls, call_session, summary, start_datetime, end_datetime,
                         description="", client_name="", client_phone="", client_email=""):
        appointment = cls(
                            user_id=call_session.user_id,
                            callsession_id=call_session.id,
                            summary=summary,
                            description=description,
                            start_datetime=start_datetime,
                            end_datetime=end_datetime,
                            client_name=client_name,
                            client_phone=client_phone,
                            client_email=client_email,
                            status='pending'
        )

        db.session.add(appointment)
        db.session.commit()
        return appointment

    def confirm(self, google_event_id=None, google_link=None):
        self.status = 'confirmed'
        if google_event_id:
            self.google_calendar_event_id = google_event_id
        if google_link:
            self.google_calendar_link = google_link
        db.session.commit()

    def cancel(self, reason=""):
        self.status = 'cancelled'
        if reason:
            self.notes = f"Cancelled: {reason}"
        db.session.commit()


# models.py - Add this class
class TwilioCallAnalytics(db.Model, TimestampMixin):
    __tablename__ = 'twilio_call_analytics'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    call_data = db.Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    processed_metrics = db.Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # __table_args__ = (db.UniqueConstraint('user_id', 'date', name='unique_user_date'),)

    def __repr__(self):
        return f"<TwilioCallAnalytics date={self.date}>"



''' RESTAURANT SECTION'''

from decimal import Decimal
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import validates

class Category(db.Model, TimestampMixin):
    __tablename__ = 'category'
    # __table_args__ = (
    #     UniqueConstraint('user_id', 'slug', name='uq_category_user_slug'),
    # )

    id = db.Column(db.Integer, primary_key=True)
    # user_id = db.Column(db.Integer, db.ForeignKey('res_user.id'), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    slug = db.Column(db.String(80), nullable=False)  # e.g., snack, spices, cold_drink
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    products = db.relationship('Product', backref='category', lazy=True, order_by='Product.sort_order')

    def __repr__(self):
        return f"<Category {self.slug} ({self.name})>"


class Product(db.Model, TimestampMixin):
    __tablename__ = 'product'
    # __table_args__ = (
    #     UniqueConstraint('user_id', 'category_id', 'name', name='uq_product_user_cat_name'),
    # )

    id = db.Column(db.Integer, primary_key=True)
    # user_id = db.Column(db.Integer, db.ForeignKey('res_user.id'), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)  # stored as Decimal
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    menu_items = db.relationship('MenuItem', backref='product', lazy=True, cascade='all, delete-orphan')

    @validates('price')
    def validate_price(self, key, value):
        if isinstance(value, str):
            value = Decimal(value)
        if value < 0:
            raise ValueError("Price cannot be negative")
        return value

    def __repr__(self):
        return f"<Product {self.name} ${self.price}>"


class Menu(db.Model, TimestampMixin):
    __tablename__ = 'menu'
    # __table_args__ = (
    #     UniqueConstraint('user_id', 'name', name='uq_menu_user_name'),
    # )

    id = db.Column(db.Integer, primary_key=True)
    # user_id = db.Column(db.Integer, db.ForeignKey('res_user.id'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)

    items = db.relationship('MenuItem', backref='menu', lazy=True, cascade='all, delete-orphan', order_by='MenuItem.id')

    @property
    def total_price(self):
        total = Decimal('0.00')
        for it in self.items:
            unit = it.price_override if it.price_override is not None else it.product.price
            total += (unit or Decimal('0.00')) * it.quantity
        return total

    def __repr__(self):
        return f"<Menu {self.name} items={len(self.items)}>"


class MenuItem(db.Model, TimestampMixin):
    __tablename__ = 'menu_item'
    __table_args__ = (
        UniqueConstraint('menu_id', 'product_id', name='uq_menu_item_unique_product'),
    )

    id = db.Column(db.Integer, primary_key=True)
    menu_id = db.Column(db.Integer, db.ForeignKey('menu.id', ondelete='CASCADE'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id', ondelete='CASCADE'), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    price_override = db.Column(db.Numeric(10, 2), nullable=True)  # optional override per menu

    def __repr__(self):
        return f"<MenuItem menu={self.menu_id} product={self.product_id} qty={self.quantity}>"


