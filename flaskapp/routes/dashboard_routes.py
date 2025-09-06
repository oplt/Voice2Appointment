from flask import request, send_file, abort, session
import io
import pandas as pd
from flaskapp.analysis.dashboard_functions import process_twilio_data
from flask import render_template, url_for, redirect, request, Blueprint, flash, session
from datetime import datetime, timedelta
from flask_login import current_user, login_required
from flaskapp.database.models import GoogleCalendarAuth
from flask import current_app
from flaskapp.database.models import Category, Product, Menu, MenuItem
from flaskapp.routes.menu_routes import ensure_default_categories


dashboard_bp = Blueprint('dashboard_bp', __name__)



@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    auth = GoogleCalendarAuth.query.filter_by(user_id=current_user.id).first()
    calendar_url = auth.embedded_link if auth and auth.embedded_link else None

    active_tab = request.args.get('tab', 'calendar')
    start_date = request.args.get('start_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')

    # --- defaults for non-menu tabs (prevents UnboundLocalError) ---
    menus = []
    current_menu = None
    categories = []
    products_by_cat = {}

    analytics_data = None
    if active_tab == 'analytics' and 'twilio_data' in session and session['twilio_data']:
        try:
            analytics_data = process_twilio_data(session['twilio_data'], start_dt, end_dt)
        except Exception as e:
            current_app.logger.error(f"Error processing Twilio data: {str(e)}")
            analytics_data = None

    if active_tab == 'menu':
        ensure_default_categories()

        menu_id = request.args.get('menu_id', type=int)
        menus = Menu.query.order_by(Menu.name.asc()).all()
        current_menu = Menu.query.filter_by(id=menu_id).first() if menu_id else None

        categories = Category.query.order_by(Category.sort_order.asc()).all()
        products_by_cat = {
            c.id: Product.query.filter_by(category_id=c.id)
            .order_by(Product.sort_order.asc()).all()
            for c in categories
        }

    return render_template(
        'dashboard.html',
        calendar_url=calendar_url,
        active_tab=active_tab,
        start_date=start_date,
        end_date=end_date,
        analytics_data=analytics_data,
        menus=menus,
        current_menu=current_menu,
        categories=categories,
        products_by_cat=products_by_cat
    )


def _parse_dates_from_args():
    fmt = '%Y-%m-%d'
    start_str = request.args.get('start_date')
    end_str = request.args.get('end_date')
    start_dt = datetime.strptime(start_str, fmt) if start_str else None
    end_dt = datetime.strptime(end_str, fmt) if end_str else None
    return start_dt, end_dt


@dashboard_bp.route('/dashboard/export/csv')
def export_calls_csv():
    start_dt, end_dt = _parse_dates_from_args()
    call_data = session.get('twilio_data', [])
    analytics = process_twilio_data(call_data, start_dt, end_dt)
    if not analytics:
        abort(404)

    df = pd.DataFrame(analytics['call_details'])
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    return send_file(
        io.BytesIO(buf.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f"calls_{request.args.get('start_date','all')}_to_{request.args.get('end_date','all')}.csv",
    )

def _make_excel_safe(df: pd.DataFrame) -> pd.DataFrame:
    """Convert any tz-aware datetime columns to tz-naive (UTC) for Excel."""
    df = df.copy()
    tz_cols = df.select_dtypes(include=['datetimetz']).columns
    for c in tz_cols:
        # Keep UTC values but drop tz info
        df[c] = df[c].dt.tz_convert('UTC').dt.tz_localize(None)
    return df


@dashboard_bp.route('/dashboard/export/excel')
@login_required
def export_calls_excel():
    start_dt, end_dt = _parse_dates_from_args()
    call_data = session.get('twilio_data', [])
    analytics = process_twilio_data(call_data, start_dt, end_dt)
    if not analytics:
        abort(404)

    df = pd.DataFrame(analytics['call_details'])
    df = _make_excel_safe(df)  # <-- key line

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter', datetime_format='yyyy-mm-dd hh:mm:ss') as writer:
        df.to_excel(writer, sheet_name='Calls', index=False)
    buf.seek(0)

    return send_file(
        buf,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f"calls_{request.args.get('start_date','all')}_to_{request.args.get('end_date','all')}.xlsx",
    )
