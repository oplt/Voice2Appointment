import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
import base64


def process_twilio_data(call_data, start_dt, end_dt):
    """Process Twilio call data and generate analytics"""
    if not call_data:
        return None

    # Convert to DataFrame
    df = pd.DataFrame(call_data)

    # Convert start_time to datetime
    df['start_time'] = pd.to_datetime(df['start_time'])

    # Handle timezone issues - convert all to timezone-naive
    if df['start_time'].dt.tz is not None:
        df['start_time'] = df['start_time'].dt.tz_convert(None)

    # Make sure our filter dates are timezone naive
    start_dt = start_dt.replace(tzinfo=None)
    end_dt = end_dt.replace(tzinfo=None)

    # Filter by date range
    df = df[(df['start_time'] >= start_dt) & (df['start_time'] <= end_dt)]

    if df.empty:
        return None

    # Calculate basic statistics
    total_calls = len(df)
    total_duration = df['duration_sec'].sum() / 60  # Convert to minutes
    avg_duration = df['duration_sec'].mean() / 60 if total_calls > 0 else 0  # Convert to minutes
    total_cost = df['price'].sum()

    # Generate charts
    calls_over_time = plot_calls_over_time(df)
    duration_distribution = plot_duration_distribution(df)
    cost_over_time = plot_cost_over_time(df)
    top_numbers = plot_top_numbers(df)

    # Prepare call details for table
    call_details = df.to_dict('records')

    return {
        'total_calls': total_calls,
        'total_duration': round(total_duration, 2),
        'avg_duration': round(avg_duration, 2),
        'total_cost': round(total_cost, 4),
        'calls_over_time': calls_over_time,
        'duration_distribution': duration_distribution,
        'cost_over_time': cost_over_time,
        'top_numbers': top_numbers,
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