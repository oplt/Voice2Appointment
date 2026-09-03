"""Relative date resolution and local date context (zoneinfo, no pytz)."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings

_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
    "maandag": 0,
    "dinsdag": 1,
    "woensdag": 2,
    "donderdag": 3,
    "vrijdag": 4,
    "zaterdag": 5,
    "zondag": 6,
    "lundi": 0,
    "mardi": 1,
    "mercredi": 2,
    "jeudi": 3,
    "vendredi": 4,
    "samedi": 5,
    "dimanche": 6,
    "montag": 0,
    "dienstag": 1,
    "mittwoch": 2,
    "donnerstag": 3,
    "freitag": 4,
    "samstag": 5,
    "sonntag": 6,
    "pazartesi": 0,
    "salı": 1,
    "sali": 1,
    "çarşamba": 2,
    "carsamba": 2,
    "perşembe": 3,
    "persembe": 3,
    "cuma": 4,
    "cumartesi": 5,
    "pazar": 6,
}


def get_zone(name: str | None) -> ZoneInfo:
    tz_name = (name or settings.default_timezone or "UTC").strip()
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def now_in_zone(tz_name: str | None = None, *, now: datetime | None = None) -> datetime:
    tz = get_zone(tz_name)
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc).astimezone(tz)
    return now.astimezone(tz)


def next_weekday_date(local_now: datetime, weekday: int) -> date:
    """Next occurrence of weekday (0=Mon). If today matches, returns +7 days."""
    days = (weekday - local_now.weekday()) % 7
    if days == 0:
        days = 7
    return (local_now + timedelta(days=days)).date()


def resolve_relative_date(
    phrase: str,
    *,
    timezone_name: str | None = None,
    now: datetime | None = None,
) -> date:
    """Resolve common relative date phrases to a local calendar date."""
    local_now = now_in_zone(timezone_name, now=now)
    text = re.sub(r"\s+", " ", (phrase or "").strip().lower())

    if text in {"today", "vandaag", "aujourd'hui", "heute", "bugün", "bugun"}:
        return local_now.date()
    if text in {"tomorrow", "morgen", "demain", "yarın", "yarin"}:
        return (local_now + timedelta(days=1)).date()
    if text in {"next week"}:
        return (local_now + timedelta(days=7)).date()
    if text in {"this evening", "this afternoon", "tonight"}:
        return local_now.date()

    m = re.fullmatch(
        r"(?:next |nächsten |nachsten )?(monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
        r"maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag|"
        r"lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|"
        r"montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag|"
        r"pazartesi|sal[iı]|çarşamba|carsamba|perşembe|persembe|cuma|cumartesi|pazar)"
        r"(?: prochain)?",
        text,
    )
    if m:
        return next_weekday_date(local_now, _WEEKDAYS[m.group(1)])

    raise ValueError(f"Unsupported relative date phrase: {phrase!r}")


def resolve_relative_datetime(
    phrase: str,
    *,
    timezone_name: str | None = None,
    now: datetime | None = None,
    default_time: time | None = None,
) -> datetime:
    """Resolve relative phrases to a timezone-aware local datetime."""
    local_now = now_in_zone(timezone_name, now=now)
    text = re.sub(r"\s+", " ", (phrase or "").strip().lower())
    day = resolve_relative_date(text, timezone_name=timezone_name, now=now)

    if text == "this afternoon":
        t = time(12, 0)
    elif text in {"this evening", "tonight"}:
        t = time(17, 0)
    else:
        t = default_time or time(9, 0)

    return datetime.combine(day, t, tzinfo=local_now.tzinfo)


def get_current_date_context(*, timezone_name: str | None = None, now: datetime | None = None) -> str:
    local_now = now_in_zone(timezone_name, now=now)
    tz_name = str(local_now.tzinfo) if local_now.tzinfo else (timezone_name or "UTC")
    now_utc = local_now.astimezone(timezone.utc)

    def fmt_next(weekday: int) -> str:
        return next_weekday_date(local_now, weekday).strftime("%Y-%m-%d")

    return f"""
Current Date and Time Context:
- Current UTC time: {now_utc.strftime("%Y-%m-%d %H:%M:%S")} UTC
- Current local time ({tz_name}): {local_now.strftime("%Y-%m-%d %H:%M:%S")} {tz_name}
- Today: {local_now.strftime("%A, %B %d, %Y")}
- Tomorrow: {(local_now + timedelta(days=1)).strftime("%A, %B %d, %Y")}
- Next week: {(local_now + timedelta(days=7)).strftime("%A, %B %d, %Y")}
- Current working hours: 9:00 AM - 5:00 PM {tz_name}
- Current day of week: {local_now.strftime("%A")}
- Current month: {local_now.strftime("%B")}
- Current year: {local_now.year}

Date Reference Guide:
- "today" = {local_now.strftime("%Y-%m-%d")}
- "tomorrow" = {(local_now + timedelta(days=1)).strftime("%Y-%m-%d")}
- "next week" = {(local_now + timedelta(days=7)).strftime("%Y-%m-%d")}
- "this afternoon" = {local_now.strftime("%Y-%m-%d")} 12:00
- "this evening" = {local_now.strftime("%Y-%m-%d")} 17:00
- "next Monday" = {fmt_next(0)}
- "next Tuesday" = {fmt_next(1)}
- "next Wednesday" = {fmt_next(2)}
- "next Thursday" = {fmt_next(3)}
- "next Friday" = {fmt_next(4)}
- "next Saturday" = {fmt_next(5)}
- "next Sunday" = {fmt_next(6)}
""".strip()
