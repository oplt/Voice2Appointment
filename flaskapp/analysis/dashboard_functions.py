import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import base64, io, json, os, folium, pycountry
import plotly.express as px
import plotly.io as pio
from folium.plugins import Fullscreen
from datetime import timezone
import requests
from functools import lru_cache


# Optional: robust phone parsing when 'from_country' is not present
try:
    import phonenumbers
    from phonenumbers import geocoder as pn_geocoder
except Exception:
    phonenumbers = None

try:
    import pycountry
except Exception:
    pycountry = None

import requests
from functools import lru_cache

# @lru_cache(maxsize=1)
# def get_world_geo():
#     url = "https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson"
#     resp = requests.get(url, timeout=10)
#     resp.raise_for_status()  # will raise if network error
#     return resp.json()


def process_twilio_data(call_data, start_dt, end_dt):
    """Process Twilio call data and generate analytics (UTC-safe; robust parsing)."""
    if not call_data:
        return None

    df = pd.DataFrame(call_data)

    # ---- Parse/clean columns ----
    # start_time → UTC-aware datetime
    if 'start_time' in df.columns:
        df['start_time'] = pd.to_datetime(df['start_time'], utc=True, errors='coerce')
    else:
        df['start_time'] = pd.NaT

    # duration_sec may be str/None
    df['duration_sec'] = pd.to_numeric(df.get('duration_sec', None), errors='coerce')
    # price may be str/None
    df['price'] = pd.to_numeric(df.get('price', None), errors='coerce')

    # Drop rows without a valid start time
    df = df.dropna(subset=['start_time'])
    if df.empty:
        return None

    # ---- Date range filtering in UTC ----
    # Normalize user-provided datetimes to UTC (assume UTC if naive)
    if start_dt is not None:
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        else:
            start_dt = start_dt.astimezone(timezone.utc)
    if end_dt is not None:
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        else:
            end_dt = end_dt.astimezone(timezone.utc)

    if start_dt:
        df = df[df['start_time'] >= start_dt]
    if end_dt:
        df = df[df['start_time'] <= end_dt]

    if df.empty:
        return None

    # ---- Basic stats ----
    total_calls = len(df)
    total_minutes = (df['duration_sec'].fillna(0).sum()) / 60.0
    avg_minutes = (df['duration_sec'].fillna(0).mean() / 60.0) if total_calls else 0.0
    total_cost = df['price'].fillna(0).sum()

    # ---- Plots you already had (unchanged) ----
    calls_over_time = plot_calls_over_time(df)
    duration_distribution = plot_duration_distribution(df)
    cost_over_time = plot_cost_over_time(df)
    top_numbers = plot_top_numbers(df)

    # ---- Folium world map HTML ----
    world_map_html = build_folium_world_map(df)

    # Prepare call details for table
    call_details = df.to_dict('records')

    return {
        'total_calls': int(total_calls),
        'total_duration': round(total_minutes, 2),
        'avg_duration': round(avg_minutes, 2),
        'total_cost': round(float(total_cost), 4),
        'calls_over_time': calls_over_time,
        'duration_distribution': duration_distribution,
        'cost_over_time': cost_over_time,
        'top_numbers': top_numbers,
        'world_map_html': world_map_html,
        'call_details': call_details
    }




def plot_calls_over_time(df):
    """Generate calls over time plot with larger fonts"""
    # Group by date
    daily_calls = df.resample('D', on='start_time').size()

    plt.figure(figsize=(12, 6))
    daily_calls.plot(kind='line', title='Calls Over Time')
    plt.xlabel('Date', fontsize=25)
    plt.ylabel('Number of Calls', fontsize=25)
    plt.title('Calls Over Time', fontsize=25)
    plt.xticks(fontsize=25)
    plt.yticks(fontsize=25)
    plt.grid(True)

    # Save to base64
    img = io.BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight')
    img.seek(0)
    plt.close()

    return base64.b64encode(img.getvalue()).decode()

def plot_duration_distribution(df):
    """Generate duration distribution plot with larger fonts"""
    plt.figure(figsize=(12, 6))
    plt.hist(df['duration_sec'].dropna() / 60, bins=20, alpha=0.7, color='#219EBC')
    plt.title('Call Duration Distribution', fontsize=25)
    plt.xlabel('Duration (minutes)', fontsize=25)
    plt.ylabel('Frequency', fontsize=25)
    plt.xticks(fontsize=25)
    plt.yticks(fontsize=25)
    plt.grid(True)

    # Save to base64
    img = io.BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight')
    img.seek(0)
    plt.close()

    return base64.b64encode(img.getvalue()).decode()

def plot_cost_over_time(df):
    """Generate cost over time plot with larger fonts"""
    # Group by date and sum costs
    daily_cost = df.resample('D', on='start_time')['price'].sum()

    plt.figure(figsize=(12, 6))
    daily_cost.plot(kind='line', title='Cost Over Time', color='#023047')
    plt.xlabel('Date', fontsize=25)
    plt.ylabel('Cost ($)', fontsize=25)
    plt.title('Cost Over Time', fontsize=25)
    plt.xticks(fontsize=25)
    plt.yticks(fontsize=25)
    plt.grid(True)

    # Save to base64
    img = io.BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight')
    img.seek(0)
    plt.close()

    return base64.b64encode(img.getvalue()).decode()

def plot_top_numbers(df):
    """Generate top called numbers plot with larger fonts"""
    # Count calls by 'to' number
    top_numbers = df['to'].value_counts().head(10)

    plt.figure(figsize=(12, 6))
    colors = ['#8ECAE6', '#219EBC', '#023047', '#FFB703', '#FB8500']
    top_numbers.plot(kind='bar', color=colors * 2)  # Repeat colors if needed
    plt.title('Top Called Numbers', fontsize=25)
    plt.xlabel('Phone Number', fontsize=25)
    plt.ylabel('Number of Calls', fontsize=25)
    plt.xticks(rotation=45, fontsize=25)
    plt.yticks(fontsize=25)
    plt.tight_layout()

    # Save to base64
    img = io.BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight')
    img.seek(0)
    plt.close()

    return base64.b64encode(img.getvalue()).decode()

def plot_world_map(df):
    """Generate a world map showing incoming calls by country"""
    if df.empty or 'from' not in df.columns:
        return None

    # Extract country codes from phone numbers
    def extract_country_code(phone_number):
        # Simple extraction - you might need a more robust solution
        # This assumes numbers are in E.164 format with country code
        if phone_number and str(phone_number).startswith('+'):
            # Try to extract the country code (first 1-3 digits after +)
            for i in range(1, 4):
                try:
                    code = phone_number[1:1+i]
                    country = pycountry.countries.get(alpha_2=code)
                    if country:
                        return country.alpha_3
                except:
                    continue
        return None

    # Count calls by country
    df['country_code'] = df['from'].apply(extract_country_code)
    country_counts = df['country_code'].value_counts().reset_index()
    country_counts.columns = ['country_code', 'call_count']

    # Create the world map
    fig = px.choropleth(
        country_counts,
        locations="country_code",
        color="call_count",
        hover_name="country_code",
        color_continuous_scale=px.colors.sequential.Plasma,
        title="Incoming Calls by Country"
    )

    fig.update_layout(
        geo=dict(
            showframe=False,
            showcoastlines=True,
            projection_type='equirectangular'
        )
    )

    # Convert to base64
    img_bytes = pio.to_image(fig, format="png")
    return base64.b64encode(img_bytes).decode()

def build_folium_world_map(df):
    """
    Build an interactive Folium map of origins by country (ISO3).
    - Uses E.164 "from" to infer country via `phonenumbers` (if installed).
    - Maps ISO2 → ISO3 via `pycountry` (if installed).
    - Choropleth if 'static/data/world-countries.json' exists with properties.ISO_A3.
    - Adds a marker cluster with bubble sizes by volume (centroids from GeoJSON bbox if available).
    Returns a full HTML string for embedding.
    """
    if df is None or df.empty:
        return None

    # ---- Country inference helpers ----
    def iso2_from_e164(e164):
        if not phonenumbers or not isinstance(e164, str) or not e164.startswith('+'):
            return None
        try:
            num = phonenumbers.parse(e164, None)
            reg = pn_geocoder.region_code_for_number(num)  # ISO-2 (e.g., "US")
            if reg and len(reg) == 2:
                return reg.upper()
        except Exception:
            return None
        return None

    def iso3_from_iso2(iso2):
        if not iso2:
            return None
        if pycountry:
            try:
                c = pycountry.countries.get(alpha_2=iso2.upper())
                return c.alpha_3 if c else None
            except Exception:
                return None
        # No pycountry: pass through ISO2 as a fallback key
        return iso2.upper()

    # Prefer explicit Twilio country if you add it later; otherwise infer from 'from'
    # Note: Twilio may return non-E.164 identifiers like 'client:xxx' or 'sip:...'; these will safely return None.
    src_iso3 = []
    for _, row in df.iterrows():
        iso2 = None
        # If you later add row.get('from_country') (ISO-2), prefer that:
        if 'from_country' in df.columns and pd.notna(row.get('from_country')):
            iso2 = str(row.get('from_country')).upper()
        if not iso2:
            iso2 = iso2_from_e164(row.get('from'))
        src_iso3.append(iso3_from_iso2(iso2))

    df = df.copy()
    df['iso3'] = src_iso3

    # Aggregate by iso3
    counts = (
        df.dropna(subset=['iso3'])
        .groupby('iso3')
        .size()
        .reset_index(name='call_count')
        .sort_values('call_count', ascending=False)
    )

    # Base map
    fmap = folium.Map(location=[20, 0], zoom_start=2, tiles="CartoDB positron")
    Fullscreen(position='topleft', title='Fullscreen', title_cancel='Exit').add_to(fmap)
    geojson_path = os.path.join('flaskapp', 'static', 'data', 'world-countries.json')
    world_geo = None
    added_choropleth = False
    if os.path.exists(geojson_path):
        try:
            with open(geojson_path, 'r', encoding='utf-8') as f:
                world_geo = json.load(f)

            bins = [0, 1, 5, 10, 50, 100, 500]
            world_geo = add_counts_to_geojson(world_geo, counts)

            folium.Choropleth(
                geo_data=world_geo,
                name='Call intensity',
                data=counts,
                columns=['iso3', 'call_count'],
                key_on='feature.properties.ISO_A3',
                fill_color='OrRd',
                fill_opacity=0.2,
                line_opacity=0.2,
                legend_name='Incoming calls',
                threshold_scale=bins,
            ).add_to(fmap)
            added_choropleth = True

            # Hover hints for country names
            folium.GeoJson(
                world_geo,
                name='Countries',
                style_function=lambda x: {'fillOpacity': 0, 'color': 'transparent'},
                tooltip=folium.features.GeoJsonTooltip(
                    fields=['name', 'ISO_A3', 'call_count'],
                    aliases=['Country', 'ISO Code', 'Calls'],
                    localize=True,
                    sticky=True)
            ).add_to(fmap)

        except Exception:
            added_choropleth = False

    # Add a marker cluster with simple centroids (from GeoJSON bbox if available)
    # mc = MarkerCluster(name='Country summaries').add_to(fmap)
    centroids = {}

    if world_geo and isinstance(world_geo, dict):
        for feat in world_geo.get('features', []):
            props = feat.get('properties', {})
            iso3 = props.get('ISO_A3')
            bbox = feat.get('bbox')  # [minLon, minLat, maxLon, maxLat]
            if iso3 and bbox and len(bbox) == 4:
                lat = (bbox[1] + bbox[3]) / 2
                lon = (bbox[0] + bbox[2]) / 2
                centroids[iso3] = (lat, lon)

    # for _, r in counts.iterrows():
    #     iso3 = r['iso3']
    #     cnt = int(r['call_count'])
    #     lat, lon = centroids.get(iso3, (20, 0))
    #     folium.CircleMarker(
    #         location=[lat, lon],
    #         radius=max(4, min(22, 4 + int(cnt ** 0.8))),
    #         popup=folium.Popup(html=f"<b>{iso3}</b><br/>Calls: {cnt}", max_width=220),
    #         fill=True,
    #         fill_opacity=0.7,
    #     ).add_to(mc)

    folium.LayerControl(collapsed=True).add_to(fmap)
    return fmap.get_root().render()

def add_counts_to_geojson(world_geo, counts_df):
    counts_map = dict(zip(counts_df['iso3'], counts_df['call_count']))

    for feature in world_geo['features']:
        iso3 = feature['properties'].get('ISO_A3')
        feature['properties']['call_count'] = counts_map.get(iso3, 0)  # default 0

    return world_geo



