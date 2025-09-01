"""
Date utility functions for parsing and converting common date expressions
"""

from datetime import datetime, timedelta
import pytz
import re
from typing import Optional, Tuple


def parse_relative_date(date_expression: str, base_date: Optional[datetime] = None, timezone: str = 'Europe/Brussels') -> Optional[datetime]:
    """
    Parse relative date expressions like 'tomorrow', 'next week', 'this afternoon', etc.
    
    Args:
        date_expression: String like 'tomorrow', 'next week', 'this afternoon'
        base_date: Base date to calculate from (defaults to current date)
        timezone: Timezone string (defaults to Europe/Brussels)
    
    Returns:
        Parsed datetime object or None if parsing fails
    """
    if base_date is None:
        # Get current time in specified timezone
        try:
            tz = pytz.timezone(timezone)
            base_date = datetime.now(pytz.UTC).astimezone(tz)
        except pytz.exceptions.UnknownTimeZoneError:
            base_date = datetime.now()
    
    # Normalize the expression
    expression = date_expression.lower().strip()
    
    # Handle "today" variations
    if expression in ['today', 'this day']:
        return base_date.replace(hour=9, minute=0, second=0, microsecond=0)
    
    # Handle "tomorrow" variations
    if expression in ['tomorrow', 'next day']:
        tomorrow = base_date + timedelta(days=1)
        return tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
    
    # Handle "yesterday" variations
    if expression in ['yesterday', 'previous day']:
        yesterday = base_date - timedelta(days=1)
        return yesterday.replace(hour=9, minute=0, second=0, microsecond=0)
    
    # Handle "next week" variations
    if expression in ['next week', 'following week']:
        next_week = base_date + timedelta(days=7)
        return next_week.replace(hour=9, minute=0, second=0, microsecond=0)
    
    # Handle "this week" variations
    if expression in ['this week', 'current week']:
        # Get Monday of current week
        days_since_monday = base_date.weekday()
        monday = base_date - timedelta(days=days_since_monday)
        return monday.replace(hour=9, minute=0, second=0, microsecond=0)
    
    # Handle "next [day]" patterns
    day_pattern = r'next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)'
    day_match = re.search(day_pattern, expression)
    if day_match:
        target_day = day_match.group(1)
        return get_next_weekday(base_date, target_day)
    
    # Handle "this [time]" patterns
    time_pattern = r'this\s+(morning|afternoon|evening|night)'
    time_match = re.search(time_pattern, expression)
    if time_match:
        time_of_day = time_match.group(1)
        return get_time_of_day(base_date, time_of_day)
    
    # Handle specific time expressions
    if expression in ['morning', 'this morning']:
        return base_date.replace(hour=9, minute=0, second=0, microsecond=0)
    elif expression in ['afternoon', 'this afternoon']:
        return base_date.replace(hour=13, minute=0, second=0, microsecond=0)
    elif expression in ['evening', 'this evening']:
        return base_date.replace(hour=17, minute=0, second=0, microsecond=0)
    elif expression in ['night', 'tonight']:
        return base_date.replace(hour=20, minute=0, second=0, microsecond=0)
    
    # Handle "in X days/weeks/months"
    time_unit_pattern = r'in\s+(\d+)\s+(day|days|week|weeks|month|months)'
    time_unit_match = re.search(time_unit_pattern, expression)
    if time_unit_match:
        amount = int(time_unit_match.group(1))
        unit = time_unit_match.group(2).rstrip('s')  # Remove plural
        return add_time_unit(base_date, amount, unit)
    
    return None


def get_next_weekday(base_date: datetime, target_day: str) -> datetime:
    """Get the next occurrence of a specific weekday"""
    # Map day names to weekday numbers (0=Monday, 6=Sunday)
    day_map = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
        'friday': 4, 'saturday': 5, 'sunday': 6
    }
    
    target_weekday = day_map.get(target_day.lower())
    if target_weekday is None:
        return base_date
    
    current_weekday = base_date.weekday()
    days_ahead = target_weekday - current_weekday
    
    # If target day is today or has passed this week, get next week's occurrence
    if days_ahead <= 0:
        days_ahead += 7
    
    next_day = base_date + timedelta(days=days_ahead)
    return next_day.replace(hour=9, minute=0, second=0, microsecond=0)


def get_time_of_day(base_date: datetime, time_of_day: str) -> datetime:
    """Get a specific time of day"""
    time_map = {
        'morning': 9,
        'afternoon': 13,
        'evening': 17,
        'night': 20
    }
    
    hour = time_map.get(time_of_day, 9)
    return base_date.replace(hour=hour, minute=0, second=0, microsecond=0)


def add_time_unit(base_date: datetime, amount: int, unit: str) -> datetime:
    """Add a specific amount of time units to a date"""
    if unit == 'day':
        return base_date + timedelta(days=amount)
    elif unit == 'week':
        return base_date + timedelta(weeks=amount)
    elif unit == 'month':
        # Approximate month as 30 days
        return base_date + timedelta(days=amount * 30)
    else:
        return base_date


def format_date_for_display(date: datetime, timezone: str = 'Europe/Brussels') -> str:
    """Format a date for user-friendly display"""
    try:
        if date.tzinfo is None:
            # If no timezone info, assume it's in the specified timezone
            tz = pytz.timezone(timezone)
            date = tz.localize(date)
        
        return date.strftime('%A, %B %d, %Y at %I:%M %p')
    except Exception:
        return date.strftime('%Y-%m-%d %H:%M:%S')


def get_working_hours_slot(date: datetime, duration_minutes: int = 30, 
                           start_hour: int = 9, end_hour: int = 17) -> Tuple[datetime, datetime]:
    """
    Get a working hours time slot for a given date
    
    Args:
        date: Base date
        duration_minutes: Duration of the slot in minutes
        start_hour: Start of working hours (24-hour format)
        end_hour: End of working hours (24-hour format)
    
    Returns:
        Tuple of (start_time, end_time)
    """
    start_time = date.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(minutes=duration_minutes)
    
    # Ensure we don't exceed working hours
    if end_time.hour > end_hour:
        # Move to next available slot
        start_time = start_time + timedelta(hours=1)
        end_time = start_time + timedelta(minutes=duration_minutes)
    
    return start_time, end_time


def is_working_hours(date: datetime, start_hour: int = 9, end_hour: int = 17) -> bool:
    """Check if a given time is within working hours"""
    return start_hour <= date.hour < end_hour


def get_available_slots_for_date(date: datetime, duration_minutes: int = 30,
                                start_hour: int = 9, end_hour: int = 17) -> list:
    """
    Generate available time slots for a given date
    
    Args:
        date: Date to generate slots for
        duration_minutes: Duration of each slot
        start_hour: Start of working hours
        end_hour: End of working hours
    
    Returns:
        List of available time slots
    """
    slots = []
    current_time = date.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    end_time = date.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    
    while current_time + timedelta(minutes=duration_minutes) <= end_time:
        slot_end = current_time + timedelta(minutes=duration_minutes)
        slots.append({
            'start': current_time,
            'end': slot_end,
            'formatted': f"{current_time.strftime('%I:%M %p')} - {slot_end.strftime('%I:%M %p')}"
        })
        current_time += timedelta(minutes=duration_minutes)
    
    return slots
