from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, Optional
from flask_login import current_user
from flaskapp.database.models import User
from flask_wtf import FlaskForm
from wtforms import FileField, StringField, SelectField, TextAreaField
from flask_wtf.file import FileAllowed
import pytz


class RegistrationForm(FlaskForm):
    username = StringField('Username',
                           validators=[DataRequired(), Length(min=2, max=20)])
    email = StringField('Email',
                        validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password',
                                     validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Sign Up')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('That username is taken. Please choose a different one.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('That email is taken. Please choose a different one.')


class LoginForm(FlaskForm):
    email = StringField('Email',
                        validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')


class UpdateAccountForm(FlaskForm):
    username = StringField('Username',
                           validators=[DataRequired(), Length(min=2, max=20)])
    email = StringField('Email',
                        validators=[DataRequired(), Email()])
    picture = FileField('Update Profile Picture', validators=[FileAllowed(['jpg', 'png'])])
    submit = SubmitField('Update')

    def validate_username(self, username):
        if username.data != current_user.username:
            user = User.query.filter_by(username=username.data).first()
            if user:
                raise ValidationError('That username is taken. Please choose a different one.')

    def validate_email(self, email):
        if email.data != current_user.email:
            user = User.query.filter_by(email=email.data).first()
            if user:
                raise ValidationError('That email is taken. Please choose a different one.')


class RequestResetForm(FlaskForm):
    email = StringField('Email',
                        validators=[DataRequired(), Email()])
    submit = SubmitField('Request Password Reset')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is None:
            raise ValidationError('There is no account with that email. You must register first.')


class ResetPasswordForm(FlaskForm):
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password',
                                     validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Reset Password')


class GoogleCalendarForm(FlaskForm):
    credentials_json = FileField('Credentials File', validators=[FileAllowed(['json']), Optional()])
    token_json = FileField('Token File', validators=[FileAllowed(['json']), Optional()])
    account_email = StringField('Account Email', validators=[Email(), DataRequired()])
    calendar_id = StringField('Calendar ID', validators=[DataRequired()])
    scopes = StringField('Scopes', validators=[DataRequired()])
    time_zone = SelectField(
        'Preferred Timezone',
        choices=[(tz, tz) for tz in pytz.all_timezones], validators=[DataRequired()]
    )
    embedded_link = StringField('Embeded Link', validators=[Optional(), Length(max=500)])

    submit = SubmitField('Save Google Calendar Settings')

    def validate(self, extra_validators=None):
        ok = super().validate(extra_validators)
        if not ok:
            return False
        if not self.credentials_json.data and not self.token_json.data:
            self.credentials_json.errors.append('Upload credentials.json or token.json')
            self.token_json.errors.append('Upload credentials.json or token.json')
            return False
        return True

class TwilioForm(FlaskForm):
    twilio_account_sid = StringField('Twilio Account SID', validators=[DataRequired()])
    twilio_auth_token = PasswordField('Twilio Auth Token', validators=[DataRequired()])
    twilio_phone_number = StringField('Twilio Phone Number', validators=[DataRequired()])
    submit = SubmitField('Save Twilio Settings')

class DeepgramForm(FlaskForm):
    deepgram_api_key = PasswordField('Deepgram API Key', validators=[DataRequired()])
    submit = SubmitField('Save Deepgram Settings')

class ConfigForm(FlaskForm):
    config_json = TextAreaField("Configuration (JSON)", validators=[Optional()])
    submit_config = SubmitField("Save Configuration")
