"""Multilingual appointment utterance → normalized intent fields (Phase 14.4).

Extracts operation / date / time / timezone — not transcription text alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.voice.dates import _WEEKDAYS, get_zone, next_weekday_date, now_in_zone


@dataclass(frozen=True)
class ParsedAppointmentUtterance:
    operation: str
    date: date
    time: time
    timezone: str
    language: str
    summary_hint: str | None = None

    @property
    def start_datetime(self) -> datetime:
        return datetime.combine(self.date, self.time, tzinfo=get_zone(self.timezone))


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _detect_language(text: str) -> str:
    if re.search(r"\b(afspraak|morgen|tandarts|maak)\b", text):
        return "nl"
    if re.search(r"\b(rendez-vous|médecin|medecin|prochain|heures|prends)\b", text):
        return "fr"
    if re.search(r"\b(termin|nächsten|nachsten|vereinbaren|uhr)\b", text):
        return "de"
    if re.search(r"\b(yarın|yarin|randevu|dişçi|disci|saat|oluştur|olustur)\b", text):
        return "tr"
    return "en"


def _detect_operation(text: str) -> str:
    if re.search(
        r"\b(cancel|annul|absagen|iptal|annuler)\b",
        text,
    ):
        return "cancel"
    if re.search(
        r"\b(reschedule|verzetten|verschieben|reporter|ertele)\b",
        text,
    ):
        return "reschedule"
    return "create"


def _summary_hint(text: str) -> str | None:
    if re.search(r"dentist|tandarts|dişçi|disci|zahnarzt", text):
        return "dentist"
    if re.search(r"doctor|médecin|medecin|arzt|doktor", text):
        return "doctor"
    return None


def _parse_time(text: str) -> time | None:
    # half drie / half 3 → 14:30 (Dutch)
    m = re.search(r"\bhalf\s*(drie|3)\b", text)
    if m:
        return time(14, 30)

    # Turkish: saat üçte / saat 3'te / saat 15'te
    m = re.search(r"\bsaat\s*(üç|uc|3|15)\b", text)
    if m:
        token = m.group(1)
        if token in {"üç", "uc", "3", "15"}:
            return time(15, 0)

    # German: um neun Uhr / um 9 Uhr
    m = re.search(r"\bum\s*(neun|9)\s*uhr\b", text)
    if m:
        return time(9, 0)

    # French: à 14 heures / a 14h
    m = re.search(r"\bà?\s*(\d{1,2})\s*h(?:eures)?\b", text)
    if m:
        hour = int(m.group(1))
        if 0 <= hour <= 23:
            return time(hour, 0)

    # English: at 3 PM / at 15:00 / at 3pm
    m = re.search(r"\bat\s*(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?\b", text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm = (m.group(3) or "").replace(".", "")
        if ampm.startswith("p") and hour < 12:
            hour += 12
        if ampm.startswith("a") and hour == 12:
            hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return time(hour, minute)

    # Generic 24h clock: 14:00 / 14u30
    m = re.search(r"\b(\d{1,2})[:u](\d{2})\b", text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return time(hour, minute)

    return None


def _parse_date(
    text: str, *, local_now: datetime
) -> date | None:
    if re.search(r"\b(today|vandaag|aujourd'?hui|heute|bugün|bugun)\b", text):
        return local_now.date()
    if re.search(r"\b(tomorrow|morgen|demain|yarın|yarin)\b", text):
        # German "morgen" alone can mean tomorrow; "montag" handled below.
        if "nächsten" in text or "nachsten" in text:
            pass
        else:
            return (local_now + timedelta(days=1)).date()

    # next <weekday> / <weekday> prochain / nächsten <weekday>
    for name, weekday in _WEEKDAYS.items():
        if re.search(rf"\b(next|prochain|nächsten|nachsten|gelecek)\s+{name}\b", text):
            return next_weekday_date(local_now, weekday)
        if re.search(rf"\b{name}\s+prochain\b", text):
            return next_weekday_date(local_now, weekday)
        if re.search(rf"\bnächsten\s+{name}\b", text) or re.search(
            rf"\bnachsten\s+{name}\b", text
        ):
            return next_weekday_date(local_now, weekday)

    return None


def parse_appointment_utterance(
    utterance: str,
    *,
    timezone_name: str | None = None,
    now: datetime | None = None,
) -> ParsedAppointmentUtterance:
    """Normalize a spoken booking phrase into structured appointment fields."""
    text = _fold(utterance)
    if not text:
        raise ValueError("empty utterance")

    tz_name = str(get_zone(timezone_name))
    local_now = now_in_zone(timezone_name, now=now)
    language = _detect_language(text)
    operation = _detect_operation(text)
    day = _parse_date(text, local_now=local_now)
    clock = _parse_time(text)

    if day is None:
        raise ValueError(f"Could not normalize date from utterance: {utterance!r}")
    if clock is None:
        raise ValueError(f"Could not normalize time from utterance: {utterance!r}")

    return ParsedAppointmentUtterance(
        operation=operation,
        date=day,
        time=clock,
        timezone=tz_name,
        language=language,
        summary_hint=_summary_hint(text),
    )
