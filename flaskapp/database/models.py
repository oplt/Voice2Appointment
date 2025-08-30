# models.py
from datetime import datetime, timedelta
from flask_login import UserMixin
from itsdangerous import URLSafeTimedSerializer as Serializer
from flask import current_app
from flaskapp import db

class TimestampMixin:
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

class User(db.Model, UserMixin):
    __tablename__ = 'res_user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    image_file = db.Column(db.String(255), nullable=False, default='default.jpg')
    password = db.Column(db.String(128), nullable=False)
    credentials_file = db.Column(db.LargeBinary, nullable=True)
    token_file = db.Column(db.LargeBinary, nullable=True)

    # Twilio Configuration
    twilio_account_sid = db.Column(db.String(255), nullable=True)
    twilio_auth_token = db.Column(db.String(255), nullable=True)
    twilio_phone_number = db.Column(db.String(20), nullable=True)
    
    # Deepgram Configuration
    deepgram_api_key = db.Column(db.String(255), nullable=True)

    # Relationships
    call_sessions = db.relationship('CallSession', backref='user', lazy=True)
    appointments = db.relationship('Appointment', backref='user', lazy=True)
    google_calendar_auth = db.relationship('GoogleCalendarAuth', backref='user', lazy=True, uselist=False)

    def __repr__(self):
        return f'<User {self.username}>'

    # Flask-Login required properties
    @property
    def is_authenticated(self):
        """Return True if the user is authenticated"""
        return True  # Since this is a database model, if it exists it's authenticated
    
    @property
    def is_active(self):
        """Return True if the user is active"""
        return True  # You can add a status field later if needed
    
    @property
    def is_anonymous(self):
        """Return False if this is an authenticated user"""
        return False
    
    def get_id(self):
        """Return the user ID as a string"""
        return str(self.id)

    def get_reset_token(self, expires_sec=1800):
        s = Serializer(current_app.config['SECRET_KEY'], expires_sec)
        return s.dumps({'user_id': self.id}).decode('utf-8')

    @staticmethod
    def verify_reset_token(token):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            user_id = s.loads(token)['user_id']
        except:
            return None
        return User.query.get(user_id)

class GoogleCalendarAuth(db.Model, TimestampMixin):
    __tablename__ = 'google_calendar_auth'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('res_user.id'), nullable=False, index=True)

    # Identity
    account_email = db.Column(db.String(255), nullable=True)
    provider = db.Column(db.String(50), nullable=False, default='google')

    # OAuth/credentials
    credentials_json = db.Column(db.Text, nullable=True)
    token_json = db.Column(db.Text, nullable=True)
    scopes = db.Column(db.Text, nullable=True)

    # Operational
    calendar_id = db.Column(db.String(255), nullable=True)
    time_zone = db.Column(db.String(100), nullable=True)
    access_token_expires_at = db.Column(db.DateTime, nullable=True)
    revoked = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(32), nullable=True)
    last_tested_at = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.Text, nullable=True)

class CallSession(db.Model):
    __tablename__ = 'callsession'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('res_user.id'), nullable=False, index=True)
    call_sid = db.Column(db.String(64), unique=True, index=True, nullable=False)
    from_number = db.Column(db.String(32))
    to_number = db.Column(db.String(32))
    step = db.Column(db.String(32), default='greeting')
    data = db.Column(db.JSON)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, index=True)

    # Relationships
    appointments = db.relationship('Appointment', backref='call_session', lazy=True)

    @classmethod
    def create(cls, call_sid, from_number, to_number, data=None, ttl_minutes=60):
        from flaskapp import db  # Import here to avoid circular imports
        
        # Get user_id from phone number
        from flaskapp.database.models import User
        user = User.query.filter_by(twilio_phone_number=to_number).first()
        user_id = user.id if user else 1  # Default to user 1 if not found
        
        session = cls(
            user_id=user_id,
            call_sid=call_sid,
            from_number=from_number,
            to_number=to_number,
            data=data or {},
            expires_at=datetime.utcnow() + timedelta(minutes=ttl_minutes),
        )
        db.session.add(session)
        db.session.commit()
        return session

class Appointment(db.Model, TimestampMixin):
    __tablename__ = 'appointment'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('res_user.id'), nullable=False, index=True)
    callsession_id = db.Column(db.Integer, db.ForeignKey('callsession.id'), unique=True, nullable=True, index=True)
    
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
    
    def __repr__(self):
        return f'<Appointment {self.summary} on {self.start_datetime}>'
    
    @classmethod
    def create_from_call(cls, call_session, summary, start_datetime, end_datetime, 
                        description="", client_name="", client_phone="", client_email=""):
        """Create appointment from call session"""
        from flaskapp import db
        
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
        """Confirm the appointment"""
        self.status = 'confirmed'
        if google_event_id:
            self.google_calendar_event_id = google_event_id
        if google_link:
            self.google_calendar_link = google_link
        self.updated_at = datetime.utcnow()
        
        from flaskapp import db
        db.session.commit()
    
    def cancel(self, reason=""):
        """Cancel the appointment"""
        self.status = 'cancelled'
        if reason:
            self.notes = f"Cancelled: {reason}"
        self.updated_at = datetime.utcnow()
        
        from flaskapp import db
        db.session.commit()