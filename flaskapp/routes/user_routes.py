from flask import render_template, url_for, redirect, request, Blueprint, flash, session
import json, os, logging, requests
from datetime import datetime, timedelta
from flask_login import login_user, current_user, logout_user, login_required
from flaskapp import db, bcrypt
from flaskapp.users.forms import (RegistrationForm, LoginForm, UpdateAccountForm,
                                   RequestResetForm, ResetPasswordForm, GoogleCalendarForm, TwilioForm, DeepgramForm, ConfigForm)
from flaskapp.users.utils import save_picture, send_reset_email
from flaskapp.database.models import GoogleCalendarAuth, User
from flask import current_app
from flaskapp.analysis.dashboard_functions import process_twilio_data


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


@users.route("/dashboard")
@login_required
def dashboard():
    auth = GoogleCalendarAuth.query.filter_by(user_id=current_user.id).first()
    calendar_url = auth.embedded_link if auth and auth.embedded_link else None

    active_tab = request.args.get('tab', 'calendar')
    start_date = request.args.get('start_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    analytics_data = None
    if active_tab == 'analytics' and 'twilio_data' in session and session['twilio_data']:
        try:
            analytics_data = process_twilio_data(session['twilio_data'], start_dt, end_dt)
        except Exception as e:
            current_app.logger.error(f"Error processing Twilio data: {str(e)}")
            analytics_data = None
    return render_template('dashboard.html', calendar_url=calendar_url, active_tab=active_tab,
                           start_date=start_date,
                           end_date=end_date,
                           analytics_data=analytics_data)


@users.route("/settings", methods=['GET', 'POST'])
@login_required
def settings():
    logging.info(f"Settings page accessed by user {current_user.id}")
    active_tab = request.args.get('tab', 'google-calendar')
    google_form = GoogleCalendarForm()
    twilio_form = TwilioForm()
    deepgram_form = DeepgramForm()
    config_form = ConfigForm()
    account_form = UpdateAccountForm()

    google_settings = (GoogleCalendarAuth.query
                       .filter_by(user_id=current_user.id, revoked=False)
                       .order_by(GoogleCalendarAuth.id.desc())
                       .first())

    if request.method == 'POST':
        if 'submit_google' in request.form:
            active_tab = 'google-calendar'
        elif 'submit_twilio' in request.form:
            active_tab = 'twilio-info'
        elif 'submit_deepgram' in request.form:
            active_tab = 'deepgram-info'
        elif 'submit_config' in request.form:
            active_tab = 'config-json'

        if "submit_google" in request.form and google_form.validate_on_submit():
            save_google_settings(google_form)
            flash('Google Calendar settings saved!', 'success')
            return redirect(url_for('users.settings', tab='google-calendar'))

        elif 'submit_twilio' in request.form:
            if twilio_form.validate_on_submit():
                save_twilio_settings(twilio_form)
                flash('Twilio settings saved!', 'success')
                return redirect(url_for('users.settings', tab='twilio-info'))

        elif 'submit_deepgram' in request.form:
            if deepgram_form.validate_on_submit():
                save_deepgram_settings(deepgram_form)
                flash('Deepgram settings saved!', 'success')
                return redirect(url_for('users.settings', tab='deepgram-info'))

        elif 'submit_config' in request.form:
            if config_form.validate_on_submit():
                save_config_settings(config_form)
                return redirect(url_for('users.settings', tab='config-json'))
        elif 'submit_account' in request.form:
            if account_form.validate_on_submit():
                save_account_settings(account_form)
                flash('Account information updated!', 'success')
                return redirect(url_for('users.settings', tab='account_setting'))

        if current_user.config_json and not config_form.config_json.data:
            config_form.config_json.data = current_user.config_json

    # Pre-populate forms with existing data
    populate_forms(google_form, twilio_form, deepgram_form, config_form, account_form)

    return render_template('settings.html',
                           google_form=google_form,
                           twilio_form=twilio_form,
                           deepgram_form=deepgram_form,
                           active_tab=active_tab,
                           google_settings=google_settings,
                            account_form=account_form,
                           config_form=config_form)


def save_google_settings(form):
    # get latest non-revoked record for this user, or create one
    google = (GoogleCalendarAuth.query
                .filter_by(user_id=current_user.id, revoked=False)
                .order_by(GoogleCalendarAuth.id.desc())
                .first())
    if not google:
        google = GoogleCalendarAuth(user_id=current_user.id, provider='google')
        db.session.add(google)

    # plain text fields
    google.account_email = (form.account_email.data or '').strip() or None
    google.calendar_id   = (form.calendar_id.data or '').strip() or None
    google.scopes        = (form.scopes.data or '').strip() or None
    google.time_zone     = (form.time_zone.data or '').strip() or None
    google.embedded_link = (form.embedded_link.data or '').strip() or None

    # file fields -> read() -> decode() -> assign TEXT
    if form.credentials_json.data:
        f = form.credentials_json.data
        google.credentials_json = f.read().decode('utf-8')
        f.seek(0)

    if form.token_json.data:
        f = form.token_json.data
        google.token_json = f.read().decode('utf-8')
        f.seek(0)

    google.updated_at = datetime.utcnow()
    db.session.commit()

def save_twilio_settings(form):
    current_user.twilio_account_sid = form.twilio_account_sid.data
    current_user.twilio_auth_token = form.twilio_auth_token.data
    current_user.twilio_phone_number = form.twilio_phone_number.data
    db.session.commit()

def save_deepgram_settings(form):
    current_user.deepgram_api_key = form.deepgram_api_key.data
    db.session.commit()

def _write_project_config_file(payload: str | None):
    try:
        target = os.path.join(current_app.root_path, "utils", "config.json")
        if not payload:
            if os.path.exists(target):
                os.remove(target)
            return

        # Atomic write: write to temp, then replace
        tmp = f"{target}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    except Exception as e:
        logging.exception("Failed to sync config.json to project folder: %s", e)


def save_config_settings(form):
    raw = (form.config_json.data or "").strip()
    uploaded_file = getattr(form, "config_file", None)
    if uploaded_file and uploaded_file.data:
        try:
            raw = uploaded_file.data.read().decode("utf-8").strip()
            uploaded_file.data.seek(0)
        except Exception as e:
            flash(f"Could not read uploaded config file: {e}", "danger")
            return

    if not raw:
        current_user.config_json = None
        db.session.commit()
        _write_project_config_file(None)
        flash("Configuration cleared.", "success")
        return

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        flash(f"Invalid JSON: {e}", "danger")
        return

    pretty = json.dumps(parsed, indent=2, sort_keys=True, ensure_ascii=False)
    current_user.config_json = pretty
    db.session.commit()
    _write_project_config_file(pretty)
    flash("Configuration saved.", "success")

def save_account_settings(form):
    if form.picture.data:
        picture_file = save_picture(form.picture.data)
        current_user.image_file = picture_file
    current_user.username = form.username.data
    current_user.email = form.email.data
    db.session.commit()

def _masked(length: int) -> str:
    return "*" * max(1, length)

def populate_forms(google_form, twilio_form, deepgram_form, config_form=None, account_form=None):
    sid = (current_user.twilio_account_sid or "")
    tok = (current_user.twilio_auth_token  or "")
    dg  = (current_user.deepgram_api_key   or "")

    twilio_form.twilio_account_sid.data = sid
    if tok:
        twilio_form.twilio_auth_token.render_kw = {"placeholder": _masked(len(tok)), "autocomplete": "new-password"}
    if dg:
        deepgram_form.deepgram_api_key.render_kw = {"placeholder": _masked(len(dg)), "autocomplete": "new-password"}

    google_settings = (GoogleCalendarAuth.query
                       .filter_by(user_id=current_user.id, revoked=False)
                       .order_by(GoogleCalendarAuth.id.desc())
                       .first())
    if google_settings:
        google_form.account_email.data = google_settings.account_email
        google_form.calendar_id.data = google_settings.calendar_id
        google_form.scopes.data = google_settings.scopes
        google_form.time_zone.data = google_settings.time_zone
        google_form.embedded_link.data = google_settings.embedded_link

    twilio_form.twilio_account_sid.data = current_user.twilio_account_sid
    twilio_form.twilio_auth_token.data = current_user.twilio_auth_token
    twilio_form.twilio_phone_number.data = current_user.twilio_phone_number

    deepgram_form.deepgram_api_key.data = current_user.deepgram_api_key

    if config_form is not None:
        saved_cfg = (current_user.config_json or "").strip()
        if saved_cfg:
            config_form.config_json.data = saved_cfg

    if account_form is not None:
        account_form.username.data = current_user.username
        account_form.email.data = current_user.email

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


@users.route('/check-google-calendar-conn', methods=['GET', 'POST'])
@login_required
def check_google_calendar_connection():
    auth = GoogleCalendarAuth.query.filter_by(user_id=current_user.id, revoked=False).order_by(GoogleCalendarAuth.id.desc()).first()
    if not auth:
        flash('No Google Calendar configuration found. Please upload credentials.', 'warning')
        return redirect(url_for('users.settings', tab='google-calendar'))

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
        return redirect(url_for('users.settings', tab='google-calendar'))

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

    return redirect(url_for('users.settings', tab='google-calendar'))


@users.route("/check-twilio-conn", methods=["POST"])
@login_required
def check_twilio_credentials():

    def pick(v, fb):
        v = (v or "").strip()
        return v if v else (fb or "").strip()

    form = request.form

    form_sid     = form.get("twilio_account_sid")
    form_token   = form.get("twilio_auth_token")
    form_api_key = form.get("twilio_api_key")
    form_api_sec = form.get("twilio_api_secret")

    account_sid = pick(form_sid,     getattr(current_user, "twilio_account_sid", None))
    auth_token  = pick(form_token,   getattr(current_user, "twilio_auth_token", None))
    api_key     = pick(form_api_key, getattr(current_user, "twilio_api_key", None))
    api_secret  = pick(form_api_sec, getattr(current_user, "twilio_api_secret", None))

    # Require at least one credential pair
    if not ((account_sid and auth_token) or (api_key and api_secret)):
        flash("Enter Account SID + Auth Token, or API Key + Secret to check.", "warning")
        return redirect(url_for('users.settings', tab='twilio-info'))

    auth_pairs = []
    if api_key and api_secret:
        auth_pairs.append((api_key, api_secret, "API Key/Secret"))
    if account_sid and auth_token:
        auth_pairs.append((account_sid, auth_token, "Account SID/Auth Token"))

    TWILIO_API = "https://api.twilio.com/2010-04-01"
    url = f"{TWILIO_API}/Accounts/{account_sid}/Usage/Records.json?PageSize=1"

    #  try each auth pair until one succeeds
    for user, pwd, label in auth_pairs:
        try:
            r = requests.get(url, auth=(user, pwd), timeout=6)
        except requests.Timeout:
            flash("Twilio request timed out. Please try again.", "warning")
            return redirect(url_for('users.settings', tab='twilio-info'))
        except requests.RequestException as e:
            flash(f"Network error contacting Twilio: {e}", "danger")
            return redirect(url_for('users.settings', tab='twilio-info'))

        if r.status_code == 200:
            flash(f"✅ Twilio credentials are valid ({label}).", "success")
            return redirect(url_for('users.settings', tab='twilio-info'))
        if r.status_code in (401, 403):
            # Try next auth pair (if any). If this was the last, fall through to error below.
            continue
        if r.status_code == 404:
            flash("Twilio says the Account SID was not found or doesn’t match these credentials.", "danger")
            return redirect(url_for('users.settings', tab='twilio-info'))
        # Other statuses: show brief snippet for debugging, but never echo secrets
        snippet = (r.text or "")[:200]
        flash(f"Twilio error {r.status_code}: {snippet}", "danger")
        return redirect(url_for('users.settings', tab='twilio-info'))

    flash("❌ Invalid Twilio credentials (unauthorized). Check your values and try again.", "danger")
    return redirect(url_for('users.settings', tab='twilio-info'))


@users.route('/check-deepgram-apikey', methods=['POST'])
@login_required
def check_deepgram_apikey():
    candidate = (request.form.get('deepgram_api_key') or current_user.deepgram_api_key or '').strip()

    if not candidate:
        flash('Enter your Deepgram API key (or save one) to check it.', 'warning')
        return redirect(url_for('users.settings', tab='deepgram-info'))

    try:
        r = requests.get(
            'https://api.deepgram.com/v1/projects',
            headers={'Authorization': f'Token {candidate}'},
            timeout=6
        )
    except requests.Timeout:
        flash('Deepgram request timed out. Please try again.', 'warning')
        return redirect(url_for('users.settings', tab='deepgram-info'))
    except requests.RequestException as e:
        flash(f'Network error while contacting Deepgram: {e}', 'danger')
        return redirect(url_for('users.settings', tab='deepgram-info'))

    if r.status_code == 200:
        flash('✅ Deepgram API key is valid.', 'success')
    elif r.status_code in (401, 403):
        flash('❌ Invalid Deepgram API key.', 'danger')
    elif r.status_code == 429:
        retry = r.headers.get('Retry-After')
        msg = f'Rate limited by Deepgram. Try again{f" after {retry}s" if retry else ""}.'
        flash(msg, 'warning')
    else:
        snippet = (r.text or '')[:160]
        flash(f'Deepgram error {r.status_code}: {snippet}', 'danger')

    return redirect(url_for('users.settings', tab='deepgram-info'))

