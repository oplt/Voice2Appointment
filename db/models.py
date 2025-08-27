from datetime import datetime
from itsdangerous import URLSafeTimedSerializer as Serializer
from flask import current_app
from flaskapp import db, login_manager
from flask_login import UserMixin


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(db.Model, UserMixin):
    __tablename__ = 'res_user'


    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    image_file = db.Column(db.String(20), nullable=False, default='default.jpg')
    password = db.Column(db.String(60), nullable=False)
    credentials_file = db.Column(db.LargeBinary, nullable=True)
    token_file = db.Column(db.LargeBinary, nullable=True)
    
    # Twilio Configuration
    twilio_account_sid = db.Column(db.String(255), nullable=True)
    twilio_auth_token = db.Column(db.String(255), nullable=True)
    twilio_phone_number = db.Column(db.String(20), nullable=True)
    
    # Plivo Configuration
    plivo_auth_id = db.Column(db.String(255), nullable=True)
    plivo_auth_token = db.Column(db.String(255), nullable=True)
    plivo_phone_number = db.Column(db.String(20), nullable=True)

    # Telnyx Configuration
    telnyx_api_key = db.Column(db.String(255), nullable=True)
    telnyx_connection_id = db.Column(db.String(255), nullable=True)
    telnyx_webhook_secret = db.Column(db.String(255), nullable=True)
    telnyx_phone_number = db.Column(db.String(20), nullable=True)

    def __repr__(self):
        return f'<User {self.username}>'


    def get_reset_token(self, expires_sec=1800):
        s = Serializer(current_app.config['SECRET_KEY'], expires_sec)
        return s.dumps({'user_id': self.id}).decode('utf-8')

    @staticmethod
    def verify_reset_token(token):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            user_id = s.loads(token, max_age=3600)['user_id']
        except:
            return None
        return User.query.get(user_id)

    def __repr__(self):
        return f"User('{self.username}', '{self.email}', '{self.image_file}')"


class GoogleCalendarAuth(db.Model):
    __tablename__ = 'google_calendar_auth'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('res_user.id'), nullable=False, index=True)

    # Identity
    account_email = db.Column(db.String(255), nullable=True)
    provider = db.Column(db.String(50), nullable=False, default='google')

    # OAuth/credentials
    credentials_json = db.Column(db.Text, nullable=True)  # service account or client secrets
    token_json = db.Column(db.Text, nullable=True)        # access/refresh token blob
    scopes = db.Column(db.Text, nullable=True)

    # Operational
    calendar_id = db.Column(db.String(255), nullable=True)
    time_zone = db.Column(db.String(64), nullable=True)
    access_token_expires_at = db.Column(db.DateTime, nullable=True)
    revoked = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(32), nullable=True)      # e.g., 'valid', 'expired', 'error'
    last_tested_at = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.Text, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('calendar_auths', lazy=True))


# Stores uploaded voice recordings and analysis
class Appointment(db.Model):
    __tablename__ = 'appointment'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('res_user.id'), nullable=True, index=True)
    stored_filename = db.Column(db.String(255), nullable=True)
    mime_type = db.Column(db.String(100), nullable=True)
    audio_data = db.Column(db.LargeBinary, nullable=True)
    transcript = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(32), nullable=False, default='uploaded')  # uploaded, processed, error
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('appointments', lazy=True))

# class AppSetting(db.Model):
#     __tablename__ = 'app_setting'
#
#     id = db.Column(db.Integer, primary_key=True)
#     user_id = db.Column(db.Integer, db.ForeignKey('res_user.id'), nullable=False, index=True)
#     key = db.Column(db.String(100), unique=True, nullable=False, index=True)
#     value = db.Column(db.Text, nullable=False)
#     type = db.Column(db.String(20), nullable=False)  # int, float, bool, str, json
#     updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
#
#     user = db.relationship('User', backref=db.backref('appsettings_rel', lazy=True))




