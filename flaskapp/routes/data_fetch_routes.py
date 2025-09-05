import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import io
import base64
from datetime import datetime, timedelta
from flask import  request, session, Blueprint
import twilio.rest
from flask_login import login_required
from flask import current_app, redirect, flash, url_for


fetch_data_bp = Blueprint('fetch_data_bp', __name__)


@fetch_data_bp.route('/fetch_twilio_data')
@login_required
def fetch_twilio_data():
    try:
        # Initialize Twilio client
        account_sid = current_app.config.get('TWILIO_ACCOUNT_SID')
        auth_token = current_app.config.get('TWILIO_AUTH_TOKEN')

        if not account_sid or not auth_token:
            flash('Twilio credentials not configured', 'error')
            return redirect(url_for('users.dashboard', tab='analytics'))

        client = twilio.rest.Client(account_sid, auth_token)

        # Fetch calls from Twilio
        calls = client.calls.list(limit=100)

        # Prepare data for JSON serialization
        call_data = []
        for c in calls:
            call_data.append({
                "sid": c.sid,
                "from": c.from_,
                "to": c.to,
                "start_time": c.start_time.isoformat() if c.start_time else None,
                "duration_sec": int(c.duration) if c.duration else None,
                "price": float(c.price) if c.price else None,
                "price_unit": c.price_unit,
                "direction": getattr(c, "direction", None),
                "from_formatted": getattr(c, "from_formatted", None),
            })

        # Store in session
        session['twilio_data'] = call_data
        session.modified = True

        flash('Twilio data fetched successfully', 'success')
        # Redirect back to analytics tab
        return redirect(url_for('users.dashboard', tab='analytics'))

    except Exception as e:
        # Handle errors
        flash(f'Error fetching Twilio data: {str(e)}', 'error')
        return redirect(url_for('users.dashboard', tab='analytics'))
