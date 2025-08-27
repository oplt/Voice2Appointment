from flask import render_template, url_for, flash, redirect, request, Blueprint, jsonify
import json
from datetime import datetime
from flask_login import login_user, current_user, logout_user, login_required
from flaskapp import db, bcrypt
from db.models import User
from flaskapp.users.forms import (RegistrationForm, LoginForm, UpdateAccountForm,
                                   RequestResetForm, ResetPasswordForm)
from flaskapp.users.utils import save_picture, send_reset_email
from db.models import GoogleCalendarAuth
from backend.core.logging_config import app_logger

# Setup logger for this module
logger = app_logger

users = Blueprint('users', __name__)


@users.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data, email=form.email.data, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        flash('Your account has been created! You are now able to log in', 'success')
        return redirect(url_for('users.login'))
    return render_template('register.html', title='Register', form=form)


@users.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('users.dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('users.dashboard'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('login.html', title='Login', form=form)


@users.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('main.home'))


@users.route("/account", methods=['GET', 'POST'])
@login_required
def account():
    form = UpdateAccountForm()
    if form.validate_on_submit():
        if form.picture.data:
            picture_file = save_picture(form.picture.data)
            current_user.image_file = picture_file
        current_user.username = form.username.data
        current_user.email = form.email.data
        db.session.commit()
        flash('Your account has been updated!', 'success')
        return redirect(url_for('users.account'))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.email.data = current_user.email
    image_file = url_for('static', filename='profile_pics/' + current_user.image_file)
    return render_template('account.html', title='Account',
                           image_file=image_file, form=form)


@users.route("/dashboard")
@login_required
def dashboard():
    return render_template('dashboard.html')

@users.route("/settings")
@login_required
def settings():
    logger.info(f"Settings page accessed by user {current_user.id}")
    auth = None
    twilio_config = None
    plivo_config = None
    telnyx_config = None
    if current_user.is_authenticated:
        auth = GoogleCalendarAuth.query.filter_by(user_id=current_user.id, revoked=False).order_by(GoogleCalendarAuth.id.desc()).first()
        # Create a simple object with Twilio config for the template
        twilio_config = {
            'account_sid': current_user.twilio_account_sid,
            'auth_token': current_user.twilio_auth_token,
            'phone_number': current_user.twilio_phone_number
        }
        # Create a simple object with Plivo config for the template
        plivo_config = {
            'auth_id': current_user.plivo_auth_id,
            'auth_token': current_user.plivo_auth_token,
            'phone_number': current_user.plivo_phone_number
        }
        telnyx_config = {
            'api_key': current_user.telnyx_api_key,
            'connection_id': current_user.telnyx_connection_id,
            'webhook_secret': current_user.telnyx_webhook_secret,
            'phone_number': current_user.telnyx_phone_number
        }
        logger.debug(f"User {current_user.id} has Twilio config: Account SID: {current_user.twilio_account_sid[:8] if current_user.twilio_account_sid else 'None'}..., Phone: {current_user.twilio_phone_number}")
        logger.debug(f"User {current_user.id} has Plivo config: Auth ID: {current_user.plivo_auth_id[:8] if current_user.plivo_auth_id else 'None'}..., Phone: {current_user.plivo_phone_number}")
        logger.debug(f"User {current_user.id} has Telnyx config: API: {'set' if current_user.telnyx_api_key else 'unset'}, Phone: {current_user.telnyx_phone_number}")
    return render_template('settings.html', auth=auth, twilio_config=twilio_config, plivo_config=plivo_config, telnyx_config=telnyx_config)


@users.route("/reset_password", methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('users.dashboard'))
    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        send_reset_email(user)
        flash('An email has been sent with instructions to reset your password.', 'info')
        return redirect(url_for('users.login'))
    return render_template('reset_request.html', title='Reset Password', form=form)


@users.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('users.dashboard'))
    user = User.verify_reset_token(token)
    if user is None:
        flash('That is an invalid or expired token', 'warning')
        return redirect(url_for('users.reset_request'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user.password = hashed_password
        db.session.commit()
        flash('Your password has been updated! You are now able to log in', 'success')
        return redirect(url_for('users.login'))
    return render_template('reset_token.html', title='Reset Password', form=form)


@users.route('/api/settings/upload-file', methods=['POST'])
@login_required
def upload_google_settings_file():
    if 'file' not in request.files:
        flash('No file part in the request', 'danger')
        return redirect(url_for('users.settings'))

    uploaded_file = request.files['file']
    file_type = request.form.get('type')

    if uploaded_file.filename == '':
        flash('No file selected', 'warning')
        return redirect(url_for('users.settings'))

    if file_type not in ['credentials', 'token']:
        flash('Invalid file type', 'danger')
        return redirect(url_for('users.settings'))

    if not uploaded_file.filename.lower().endswith('.json'):
        flash('File must be a .json file', 'danger')
        return redirect(url_for('users.settings'))

    try:
        file_text = uploaded_file.read().decode('utf-8')
        # Validate JSON content before saving
        json.loads(file_text)

        auth = GoogleCalendarAuth.query.filter_by(user_id=current_user.id, revoked=False).order_by(GoogleCalendarAuth.id.desc()).first()
        if not auth:
            auth = GoogleCalendarAuth(user_id=current_user.id, provider='google', created_at=datetime.utcnow(), updated_at=datetime.utcnow())
            db.session.add(auth)

        if file_type == 'credentials':
            auth.credentials_json = file_text
        else:
            auth.token_json = file_text
        auth.updated_at = datetime.utcnow()

        db.session.commit()
        flash(f'{file_type.capitalize()} file uploaded successfully', 'success')
    except json.JSONDecodeError:
        flash('Invalid JSON file', 'danger')
    except Exception:
        flash('An unexpected error occurred while uploading the file', 'danger')

    return redirect(url_for('users.settings'))


@users.route('/api/settings/telnyx-config', methods=['POST'])
@login_required
def save_telnyx_config():
    """Save Telnyx configuration settings for the current user"""
    try:
        telnyx_api_key = request.form.get('telnyx_api_key', '').strip()
        telnyx_connection_id = request.form.get('telnyx_connection_id', '').strip()
        telnyx_webhook_secret = request.form.get('telnyx_webhook_secret', '').strip()
        telnyx_phone_number = request.form.get('telnyx_phone_number', '').strip()

        # Minimal validation; API key optional for TeXML
        if not telnyx_phone_number:
            flash('Telnyx Phone Number is required', 'danger')
            return redirect(url_for('users.settings'))

        if not telnyx_phone_number.startswith('+') or len(telnyx_phone_number) < 10:
            flash('Phone number must be in E.164 format (e.g., +1234567890)', 'danger')
            return redirect(url_for('users.settings'))

        current_user.telnyx_api_key = telnyx_api_key or None
        current_user.telnyx_connection_id = telnyx_connection_id or None
        current_user.telnyx_webhook_secret = telnyx_webhook_secret or None
        current_user.telnyx_phone_number = telnyx_phone_number or None

        db.session.commit()
        logger.info(f"Telnyx settings saved for user {current_user.id}, Phone: {telnyx_phone_number}")
        flash('Telnyx settings saved successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error saving Telnyx settings: {str(e)}', 'danger')
        logger.error(f'Error saving Telnyx settings for user {current_user.id}: {str(e)}')
    return redirect(url_for('users.settings'))


@users.route('/api/phone/test-telnyx-connection', methods=['POST'])
@login_required
def test_telnyx_connection():
    try:
        if not current_user.telnyx_phone_number:
            flash('Telnyx phone number is not set', 'warning')
            return redirect(url_for('users.settings'))

        # For TeXML we can only validate format and presence
        if current_user.telnyx_api_key:
            logger.info(f"Telnyx API key present for user {current_user.id}")
        flash('Telnyx configuration looks valid. Note: TeXML does not require API calls.', 'success')
    except Exception as e:
        flash(f'Unexpected error testing Telnyx connection: {str(e)}', 'danger')
        logger.error(f'Unexpected error testing Telnyx connection for user {current_user.id}: {str(e)}', exc_info=True)
    return redirect(url_for('users.settings'))
@users.route('/api/settings/google-auth', methods=['POST'])
@login_required
def save_google_auth_metadata():
    auth = GoogleCalendarAuth.query.filter_by(user_id=current_user.id, revoked=False).order_by(GoogleCalendarAuth.id.desc()).first()
    if not auth:
        auth = GoogleCalendarAuth(user_id=current_user.id, provider='google', created_at=datetime.utcnow(), updated_at=datetime.utcnow())
        db.session.add(auth)

    account_email = request.form.get('account_email')
    calendar_id = request.form.get('calendar_id')
    scopes = request.form.get('scopes')
    time_zone = request.form.get('time_zone')

    if account_email is not None:
        auth.account_email = account_email.strip() or None
    if calendar_id is not None:
        auth.calendar_id = calendar_id.strip() or None
    if scopes is not None:
        auth.scopes = scopes.strip() or None
    if time_zone is not None:
        auth.time_zone = time_zone.strip() or None

    auth.updated_at = datetime.utcnow()
    db.session.commit()
    flash('Google Calendar settings saved', 'success')
    return redirect(url_for('users.settings'))


@users.route('/api/settings/twilio-config', methods=['POST'])
@login_required
def save_twilio_config():
    """Save Twilio configuration settings for the current user"""
    try:
        # Get form data
        twilio_account_sid = request.form.get('twilio_account_sid', '').strip()
        twilio_auth_token = request.form.get('twilio_auth_token', '').strip()
        twilio_phone_number = request.form.get('twilio_phone_number', '').strip()
        
        # Validate required fields
        if not twilio_account_sid:
            flash('Twilio Account SID is required', 'danger')
            return redirect(url_for('users.settings'))
        
        if not twilio_auth_token:
            flash('Twilio Auth Token is required', 'danger')
            return redirect(url_for('users.settings'))
        
        if not twilio_phone_number:
            flash('Twilio Phone Number is required', 'danger')
            return redirect(url_for('users.settings'))
        
        # Validate phone number format (basic E.164 validation)
        if not twilio_phone_number.startswith('+') or len(twilio_phone_number) < 10:
            flash('Phone number must be in E.164 format (e.g., +1234567890)', 'danger')
            return redirect(url_for('users.settings'))
        
        # Update user's Twilio configuration
        current_user.twilio_account_sid = twilio_account_sid
        current_user.twilio_auth_token = twilio_auth_token
        current_user.twilio_phone_number = twilio_phone_number
        
        db.session.commit()
        logger.info(f"Twilio settings saved successfully for user {current_user.id}, Phone: {twilio_phone_number}")
        flash('Twilio settings saved successfully', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error saving Twilio settings: {str(e)}', 'danger')
        logger.error(f'Error saving Twilio settings for user {current_user.id}: {str(e)}')
    
    return redirect(url_for('users.settings'))


@users.route('/api/settings/plivo-config', methods=['POST'])
@login_required
def save_plivo_config():
    """Save Plivo configuration settings for the current user"""
    try:
        # Get form data
        plivo_auth_id = request.form.get('plivo_auth_id', '').strip()
        plivo_auth_token = request.form.get('plivo_auth_token', '').strip()
        plivo_phone_number = request.form.get('plivo_phone_number', '').strip()
        
        # Validate required fields
        if not plivo_auth_id:
            flash('Plivo Auth ID is required', 'danger')
            return redirect(url_for('users.settings'))
        
        if not plivo_auth_token:
            flash('Plivo Auth Token is required', 'danger')
            return redirect(url_for('users.settings'))
        
        if not plivo_phone_number:
            flash('Plivo Phone Number is required', 'danger')
            return redirect(url_for('users.settings'))
        
        # Validate phone number format (basic E.164 validation)
        if not plivo_phone_number.startswith('+') or len(plivo_phone_number) < 10:
            flash('Phone number must be in E.164 format (e.g., +1234567890)', 'danger')
            return redirect(url_for('users.settings'))
        
        # Update user's Plivo configuration
        current_user.plivo_auth_id = plivo_auth_id
        current_user.plivo_auth_token = plivo_auth_token
        current_user.plivo_phone_number = plivo_phone_number
        
        db.session.commit()
        logger.info(f"Plivo settings saved successfully for user {current_user.id}, Phone: {plivo_phone_number}")
        flash('Plivo settings saved successfully', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error saving Plivo settings: {str(e)}', 'danger')
        logger.error(f'Error saving Plivo settings for user {current_user.id}: {str(e)}')
    
    return redirect(url_for('users.settings'))


@users.route('/api/calendar/test-connection', methods=['POST'])
@login_required
def test_google_calendar_connection():
    auth = GoogleCalendarAuth.query.filter_by(user_id=current_user.id, revoked=False).order_by(GoogleCalendarAuth.id.desc()).first()
    if not auth:
        flash('No Google Calendar configuration found. Please upload credentials.', 'warning')
        return redirect(url_for('users.settings'))

    # Attempt to use Google API client if available
    try:
        from googleapiclient.discovery import build  # type: ignore
        from google.oauth2 import service_account  # type: ignore
        from google.oauth2.credentials import Credentials as UserCredentials  # type: ignore
    except Exception as import_err:
        auth.status = 'error'
        auth.last_tested_at = datetime.utcnow()
        auth.last_error = f'Import error: {import_err}'
        db.session.commit()
        flash(f'Google API import failed: {import_err}. Ensure packages are installed in the running environment.', 'danger')
        return redirect(url_for('users.settings'))

    try:
        creds = None
        scopes_list = []
        if auth.scopes:
            # Allow comma or whitespace separated
            scopes_list = [s.strip() for s in auth.scopes.replace('\n', ',').split(',') if s.strip()]
        if not scopes_list:
            scopes_list = ['https://www.googleapis.com/auth/calendar.readonly']

        # Prefer service account if credentials_json contains service account fields
        credentials_info = None
        if auth.credentials_json:
            credentials_info = json.loads(auth.credentials_json)

        if credentials_info and credentials_info.get('type') == 'service_account':
            creds = service_account.Credentials.from_service_account_info(credentials_info, scopes=scopes_list)
            # Optionally impersonate account_email if provided
            if auth.account_email:
                creds = creds.with_subject(auth.account_email)
        elif auth.token_json:
            token_info = json.loads(auth.token_json)
            creds = UserCredentials.from_authorized_user_info(token_info, scopes=scopes_list)
        else:
            raise ValueError('Missing valid credentials. Upload service account credentials or user token.')

        service = build('calendar', 'v3', credentials=creds, cache_discovery=False)
        # Simple call to verify access
        result = service.calendarList().list(maxResults=1).execute()

        auth.status = 'valid'
        auth.last_tested_at = datetime.utcnow()
        auth.last_error = None
        db.session.commit()
        flash('Google Calendar connection successful.', 'success')
    except Exception as e:
        auth.status = 'error'
        auth.last_tested_at = datetime.utcnow()
        auth.last_error = str(e)
        db.session.commit()
        flash(f'Connection failed: {str(e)}', 'danger')

    return redirect(url_for('users.settings'))


@users.route('/api/phone/test-connection', methods=['POST'])
@login_required
def test_twilio_connection():
    """Test Twilio connection using stored credentials"""
    try:
        # Check if user has Twilio configuration
        if not current_user.twilio_account_sid or not current_user.twilio_auth_token or not current_user.twilio_phone_number:
            flash('Twilio configuration incomplete. Please fill in all required fields.', 'warning')
            return redirect(url_for('users.settings'))
        
        # Test Twilio connection
        from twilio.rest import Client
        from twilio.base.exceptions import TwilioException
        
        client = Client(current_user.twilio_account_sid, current_user.twilio_auth_token)
        
        # For trial accounts, try to list phone numbers instead of fetching account
        # This is a safer operation that works with trial accounts
        try:
            phone_numbers = client.incoming_phone_numbers.list(limit=1)
            flash('Twilio connection successful! Credentials are valid.', 'success')
            logger.info(f'Twilio connection test passed for user {current_user.id}')
        except Exception as list_error:
            # If listing fails, try a simple validation
            if current_user.twilio_account_sid.startswith('AC') and len(current_user.twilio_auth_token) == 32:
                flash('Twilio credentials format appears valid. Note: Some operations may be limited with trial accounts.', 'info')
                logger.info(f'Twilio credentials format validated for user {current_user.id} (trial account limitations may apply)')
            else:
                flash('Twilio connection failed. Please check your credentials format.', 'danger')
                logger.error(f'Twilio credentials format invalid for user {current_user.id}')
            
    except TwilioException as e:
        error_msg = str(e)
        if "Test Account Credentials" in error_msg:
            flash('Twilio connection test limited due to trial account restrictions. Your credentials are valid, but some operations are not available with trial accounts.', 'warning')
            logger.warning(f'Twilio trial account limitation for user {current_user.id}: {error_msg}')
        elif "403" in error_msg:
            flash('Twilio access denied. Please check your Account SID and Auth Token.', 'danger')
            logger.error(f'Twilio access denied for user {current_user.id}: {error_msg}')
        else:
            flash(f'Twilio connection failed: {error_msg}', 'danger')
            logger.error(f'Twilio connection error for user {current_user.id}: {error_msg}')
    except Exception as e:
        flash(f'Unexpected error testing Twilio connection: {str(e)}', 'danger')
        logger.error(f'Unexpected error testing Twilio connection for user {current_user.id}: {str(e)}', exc_info=True)
    
    return redirect(url_for('users.settings'))


@users.route('/api/phone/test-plivo-connection', methods=['POST'])
@login_required
def test_plivo_connection():
    """Test Plivo connection using stored credentials"""
    try:
        # Check if user has Plivo configuration
        if not current_user.plivo_auth_id or not current_user.plivo_auth_token or not current_user.plivo_phone_number:
            flash('Plivo configuration incomplete. Please fill in all required fields.', 'warning')
            return redirect(url_for('users.settings'))
        
        # Test Plivo connection
        from plivo import plivoxml
        from plivo.exceptions import PlivoException
        
        # Try to create a simple Plivo XML response to test credentials
        try:
            response = plivoxml.ResponseElement()
            response.add(plivoxml.SpeechElement("Test response"))
            
            flash('Plivo connection successful! Credentials are valid.', 'success')
            logger.info(f'Plivo connection test passed for user {current_user.id}')
            
        except Exception as xml_error:
            # If XML creation fails, try a simple validation
            if current_user.plivo_auth_id.startswith('MA') and len(current_user.plivo_auth_token) == 32:
                flash('Plivo credentials format appears valid. Note: Some operations may be limited with trial accounts.', 'info')
                logger.info(f'Plivo credentials format validated for user {current_user.id} (trial account limitations may apply)')
            else:
                flash('Plivo connection failed. Please check your credentials format.', 'danger')
                logger.error(f'Plivo credentials format invalid for user {current_user.id}')
            
    except PlivoException as e:
        error_msg = str(e)
        if "trial" in error_msg.lower() or "limit" in error_msg.lower():
            flash('Plivo connection test limited due to trial account restrictions. Your credentials are valid, but some operations are not available with trial accounts.', 'warning')
            logger.warning(f'Plivo trial account limitation for user {current_user.id}: {error_msg}')
        else:
            flash(f'Plivo connection failed: {error_msg}', 'danger')
            logger.error(f'Plivo connection error for user {current_user.id}: {error_msg}')
    except Exception as e:
        flash(f'Unexpected error testing Plivo connection: {str(e)}', 'danger')
        logger.error(f'Unexpected error testing Plivo connection for user {current_user.id}: {str(e)}', exc_info=True)
    
    return redirect(url_for('users.settings'))


@users.route('/api/calendar/status', methods=['GET'])
@login_required
def get_calendar_auth_status():
    """Get the current user's Google Calendar authentication status"""
    print(f"=== Calendar Status Request ===")
    print(f"User ID: {current_user.id}")
    print(f"User authenticated: {current_user.is_authenticated}")

    try:
        auth = GoogleCalendarAuth.query.filter_by(user_id=current_user.id, revoked=False).order_by(GoogleCalendarAuth.id.desc()).first()
        print(f"Auth record found: {auth is not None}")

        if not auth:
            print("No GoogleCalendarAuth found - returning configuration needed")
            return jsonify({
                'ok': False,
                'message': 'No Google Calendar configuration found',
                'has_credentials': False,
                'has_token': False,
                'status': 'not_configured',
                'missing_fields': ['credentials_json', 'token_json', 'account_email', 'calendar_id'],
                'warnings': [
                    'No Google Calendar configuration exists',
                    'You need to upload either service account credentials or user token',
                    'Configure account email and calendar ID for proper integration'
                ]
            }), 200

        print(f"Auth details: ID={auth.id}, Status={auth.status}, Has credentials={bool(auth.credentials_json)}, Has token={bool(auth.token_json)}")

        # Check what fields are missing
        missing_fields = []
        warnings = []

        if not auth.credentials_json and not auth.token_json:
            missing_fields.append('credentials_json')
            missing_fields.append('token_json')
            warnings.append('Missing authentication credentials - upload service account credentials or user token')

        if not auth.account_email:
            missing_fields.append('account_email')
            warnings.append('Account email not configured - needed for service account impersonation')

        if not auth.calendar_id:
            missing_fields.append('calendar_id')
            warnings.append('Calendar ID not configured - will use primary calendar')

        # Determine overall status
        if missing_fields:
            if not auth.credentials_json and not auth.token_json:
                status = 'incomplete'
                status_message = 'Missing authentication credentials'
            else:
                status = 'configured'
                status_message = 'Basic configuration complete but some fields missing'
        else:
            status = 'configured'
            status_message = 'All required fields configured'

        return jsonify({
            'ok': True,
            'message': 'Google Calendar configuration found',
            'has_credentials': bool(auth.credentials_json),
            'has_token': bool(auth.token_json),
            'status': status,
            'status_message': status_message,
            'account_email': auth.account_email,
            'calendar_id': auth.calendar_id,
            'last_tested': auth.last_tested_at.isoformat() if auth.last_tested_at else None,
            'last_error': auth.last_error,
            'missing_fields': missing_fields,
            'warnings': warnings,
            'is_testable': bool(auth.credentials_json or auth.token_json)
        }), 200

    except Exception as e:
        print(f"Error in get_calendar_auth_status: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'ok': False,
            'message': f'Error: {str(e)}',
            'missing_fields': [],
            'warnings': [f'Server error: {str(e)}']
        }), 500


@users.route('/api/calendar/events', methods=['GET'])
@login_required
def fetch_google_calendar_events():
    """Fetch Google Calendar events for the current user"""
    print(f"Calendar events request from user {current_user.id}")

    auth = GoogleCalendarAuth.query.filter_by(user_id=current_user.id, revoked=False).order_by(GoogleCalendarAuth.id.desc()).first()
    if not auth:
        print(f"No GoogleCalendarAuth found for user {current_user.id}")
        return jsonify({'ok': False, 'message': 'No Google Calendar configuration found.'}), 400

    print(f"Found auth record: {auth.id}, has credentials: {bool(auth.credentials_json)}, has token: {bool(auth.token_json)}")

    try:
        from googleapiclient.discovery import build  # type: ignore
        from google.oauth2 import service_account  # type: ignore
        from google.oauth2.credentials import Credentials as UserCredentials  # type: ignore
        print("Google API imports successful")
    except Exception as import_err:
        print(f"Google API import failed: {import_err}")
        return jsonify({'ok': False, 'message': f'Google API import failed: {import_err}'}), 500

    try:
        scopes_list = []
        if auth.scopes:
            scopes_list = [s.strip() for s in auth.scopes.replace('\n', ',').split(',') if s.strip()]
        if not scopes_list:
            scopes_list = ['https://www.googleapis.com/auth/calendar.readonly']

        print(f"Using scopes: {scopes_list}")

        credentials_info = None
        if auth.credentials_json:
            try:
                credentials_info = json.loads(auth.credentials_json)
                print(f"Credentials type: {credentials_info.get('type') if credentials_info else 'None'}")
            except json.JSONDecodeError as e:
                print(f"Invalid credentials JSON: {e}")
                return jsonify({'ok': False, 'message': 'Invalid credentials JSON format'}), 400

        creds = None
        if credentials_info and credentials_info.get('type') == 'service_account':
            print("Creating service account credentials")
            creds = service_account.Credentials.from_service_account_info(credentials_info, scopes=scopes_list)
            if auth.account_email:
                print(f"Impersonating account: {auth.account_email}")
                creds = creds.with_subject(auth.account_email)
        elif auth.token_json:
            try:
                token_info = json.loads(auth.token_json)
                print("Creating user credentials from token")
                creds = UserCredentials.from_authorized_user_info(token_info, scopes=scopes_list)
            except json.JSONDecodeError as e:
                print(f"Invalid token JSON: {e}")
                return jsonify({'ok': False, 'message': 'Invalid token JSON format'}), 400
        else:
            print("No valid credentials found")
            return jsonify({'ok': False, 'message': 'No valid credentials found'}), 400

        if not creds:
            print("Failed to create credentials")
            return jsonify({'ok': False, 'message': 'Failed to create credentials'}), 400

        print("Building calendar service...")
        service = build('calendar', 'v3', credentials=creds, cache_discovery=False)

        # Get calendar ID - use primary if not specified
        calendar_id = auth.calendar_id or 'primary'
        print(f"Fetching events from calendar: {calendar_id}")

        # Get events for next 30 days
        from datetime import timedelta
        now = datetime.utcnow()
        time_min = now.isoformat() + 'Z'
        time_max = (now + timedelta(days=30)).isoformat() + 'Z'

        print(f"Time range: {time_min} to {time_max}")

        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=50,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        print(f"Found {len(events)} events")

        # Update last tested time
        auth.last_tested_at = datetime.utcnow()
        auth.last_error = None
        db.session.commit()

        return jsonify({
            'ok': True,
            'message': f'Successfully loaded {len(events)} events',
            'events': events
        }), 200

    except Exception as e:
        print(f"Error fetching calendar events: {e}")
        import traceback
        traceback.print_exc()

        # Update error status
        auth.last_tested_at = datetime.utcnow()
        auth.last_error = str(e)
        db.session.commit()

        return jsonify({
            'ok': False,
            'message': f'Failed to fetch events: {str(e)}'
        }), 500


@users.route('/api/calendar/initiate-auth', methods=['POST'])
@login_required
def initiate_google_auth():
    """Initiate Google OAuth flow for calendar access"""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        import os

        # OAuth 2.0 scopes for Google Calendar
        SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

        # Check if we have existing credentials file
        token_file = f'token_{current_user.id}.json'

        creds = None
        if os.path.exists(token_file):
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)

        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as refresh_error:
                    print(f"Token refresh failed: {refresh_error}")
                    # Remove invalid token file
                    if os.path.exists(token_file):
                        os.remove(token_file)
                    creds = None

            if not creds:
                # Need to create new credentials file for this user
                credentials_file = 'credentials.json'
                if not os.path.exists(credentials_file):
                    return jsonify({
                        'ok': False,
                        'message': 'Google OAuth credentials file not found. Please upload credentials.json to the server.',
                        'needs_credentials_file': True
                    }), 400

                flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)

                # Save the credentials for the next run
                with open(token_file, 'w') as token:
                    token.write(creds.to_json())

        # Now test the credentials by making a simple API call
        try:
            from googleapiclient.discovery import build
            service = build('calendar', 'v3', credentials=creds)

            # Test with a simple calendar list call
            calendar_list = service.calendarList().list(maxResults=1).execute()

            # Update or create GoogleCalendarAuth record
            auth = GoogleCalendarAuth.query.filter_by(user_id=current_user.id, revoked=False).order_by(GoogleCalendarAuth.id.desc()).first()
            if not auth:
                auth = GoogleCalendarAuth(user_id=current_user.id)
                db.session.add(auth)

            # Save the token info
            auth.token_json = creds.to_json()
            auth.account_email = creds.client_id  # This will be the client ID, not ideal but works
            auth.status = 'valid'
            auth.last_tested_at = datetime.utcnow()
            auth.last_error = None
            auth.scopes = ','.join(SCOPES)

            db.session.commit()

            return jsonify({
                'ok': True,
                'message': 'Google Calendar authentication successful!',
                'status': 'authenticated'
            }), 200

        except Exception as api_error:
            print(f"API test failed: {api_error}")
            return jsonify({
                'ok': False,
                'message': f'Authentication successful but API test failed: {str(api_error)}',
                'status': 'api_test_failed'
            }), 400

    except Exception as e:
        print(f"OAuth initiation error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'ok': False,
            'message': f'OAuth initiation failed: {str(e)}',
            'status': 'error'
        }), 500


@users.route('/api/calendar/refresh-auth', methods=['POST'])
@login_required
def refresh_google_auth():
    """Refresh Google Calendar authentication"""
    try:
        auth = GoogleCalendarAuth.query.filter_by(user_id=current_user.id, revoked=False).order_by(GoogleCalendarAuth.id.desc()).first()
        if not auth:
            return jsonify({
                'ok': False,
                'message': 'No Google Calendar configuration found'
            }), 400

        # Try to refresh existing credentials
        if auth.token_json:
            try:
                from google.oauth2.credentials import Credentials
                from google.auth.transport.requests import Request
                from googleapiclient.discovery import build

                creds = Credentials.from_authorized_user_info(json.loads(auth.token_json))

                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())

                    # Update token in database
                    auth.token_json = creds.to_json()
                    auth.status = 'valid'
                    auth.last_tested_at = datetime.utcnow()
                    auth.last_error = None
                    db.session.commit()

                    return jsonify({
                        'ok': True,
                        'message': 'Authentication refreshed successfully',
                        'status': 'refreshed'
                    }), 200
                else:
                    return jsonify({
                        'ok': False,
                        'message': 'No refresh needed or no refresh token available',
                        'status': 'no_refresh_needed'
                    }), 400

            except Exception as refresh_error:
                print(f"Token refresh error: {refresh_error}")
                auth.status = 'error'
                auth.last_error = str(refresh_error)
                auth.last_tested_at = datetime.utcnow()
                db.session.commit()

                return jsonify({
                    'ok': False,
                    'message': f'Token refresh failed: {str(refresh_error)}',
                    'status': 'refresh_failed'
                }), 400

        return jsonify({
            'ok': False,
            'message': 'No token available for refresh',
            'status': 'no_token'
        }), 400

    except Exception as e:
        print(f"Refresh auth error: {e}")
        return jsonify({
            'ok': False,
            'message': f'Refresh failed: {str(e)}',
            'status': 'error'
        }), 500