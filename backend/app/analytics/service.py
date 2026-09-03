"""Analytics: compact JSON chart series for the SPA (no matplotlib/folium/pandas)."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import phonenumbers
import pycountry
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import TwilioCall, TwilioCallAnalytics
from app.telephony.providers.twilio import TwilioProvider

WEEKDAY_ORDER = [0, 1, 2, 3, 4, 5, 6]
WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def exclusive_end_datetime(end: date | datetime, *, tz=timezone.utc) -> datetime:
    """Half-open interval end: include the full calendar day of ``end``."""
    if isinstance(end, datetime):
        end_date = end.astimezone(tz).date() if end.tzinfo else end.date()
    else:
        end_date = end
    return datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)


def inclusive_start_datetime(start: date | datetime, *, tz=timezone.utc) -> datetime:
    if isinstance(start, datetime):
        if start.tzinfo is None:
            return start.replace(tzinfo=tz)
        return start.astimezone(tz)
    return datetime.combine(start, time.min, tzinfo=tz)


def _parse_start(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _infer_iso2_from_row(row: dict[str, Any]) -> str | None:
    iso2 = None
    raw_country = row.get("from_country")
    if raw_country:
        iso2 = str(raw_country).upper()
    if not iso2:
        from_num = row.get("from")
        if isinstance(from_num, str) and from_num.startswith("+"):
            try:
                num = phonenumbers.parse(from_num, None)
                reg = phonenumbers.region_code_for_number(num)
                if reg and len(reg) == 2:
                    iso2 = reg.upper()
            except phonenumbers.NumberParseException:
                pass
    return iso2


def _iso3_from_iso2(iso2: str | None) -> str | None:
    if not iso2:
        return None
    country = pycountry.countries.get(alpha_2=iso2.upper())
    return country.alpha_3 if country else None


def _country_name_from_iso(any_iso: str | None) -> str | None:
    if not any_iso:
        return None
    any_iso = any_iso.upper()
    if len(any_iso) == 2:
        country = pycountry.countries.get(alpha_2=any_iso)
    else:
        country = pycountry.countries.get(alpha_3=any_iso)
    return country.name if country else any_iso


def compute_top_countries(
    rows: list[dict[str, Any]], top_n: int = 15
) -> list[dict[str, Any]]:
    if not rows:
        return []
    buckets: dict[str, dict[str, float]] = {}
    for row in rows:
        iso2 = _infer_iso2_from_row(row)
        iso3 = _iso3_from_iso2(iso2) if iso2 else None
        if not iso3:
            continue
        bucket = buckets.setdefault(
            iso3, {"calls": 0, "total_cost": 0.0, "duration_sum": 0.0}
        )
        bucket["calls"] += 1
        price = _as_float(row.get("price")) or 0.0
        bucket["total_cost"] += price
        bucket["duration_sum"] += float(_as_int(row.get("duration_sec")) or 0)
    ranked = []
    for iso3, stats in buckets.items():
        calls = int(stats["calls"])
        avg_min = (stats["duration_sum"] / 60.0 / calls) if calls else 0.0
        ranked.append(
            {
                "country": _country_name_from_iso(iso3),
                "iso3": iso3,
                "calls": calls,
                "total_cost": round(stats["total_cost"], 4),
                "avg_duration_min": round(avg_min, 2),
            }
        )
    ranked.sort(
        key=lambda r: (-int(r["calls"]), -float(r["total_cost"]))  # type: ignore[arg-type]
    )
    return ranked[:top_n]


def _series_calls_over_time(rows: list[tuple[datetime, dict[str, Any]]]) -> dict[str, list]:
    counts: Counter[str] = Counter()
    for start, _ in rows:
        counts[start.date().isoformat()] += 1
    labels = sorted(counts.keys())
    return {"labels": labels, "values": [counts[d] for d in labels]}


def _series_duration_distribution(rows: list[dict[str, Any]]) -> dict[str, list]:
    minutes = []
    for row in rows:
        sec = _as_int(row.get("duration_sec"))
        if sec is not None:
            minutes.append(sec / 60.0)
    if not minutes:
        return {"labels": [], "values": []}
    edges = [0, 1, 2, 5, 10, 20, 30, 60, 120]
    labels: list[str] = []
    values: list[int] = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        labels.append(f"{lo}-{hi}")
        values.append(sum(1 for m in minutes if lo <= m < hi))
    labels.append(f"{edges[-1]}+")
    values.append(sum(1 for m in minutes if m >= edges[-1]))
    return {"labels": labels, "values": values}


def _series_cost_over_time(rows: list[tuple[datetime, dict[str, Any]]]) -> dict[str, list]:
    totals: dict[str, float] = defaultdict(float)
    for start, row in rows:
        totals[start.date().isoformat()] += _as_float(row.get("price")) or 0.0
    labels = sorted(totals.keys())
    return {
        "labels": labels,
        "values": [round(totals[d], 4) for d in labels],
    }


def _series_top_numbers(rows: list[dict[str, Any]]) -> dict[str, list]:
    counts: Counter[str] = Counter()
    for row in rows:
        to_num = row.get("to")
        if to_num:
            counts[str(to_num)] += 1
    top = counts.most_common(10)
    return {
        "labels": [label for label, _ in top],
        "values": [value for _, value in top],
    }


def _series_peak_heatmap(rows: list[tuple[datetime, dict[str, Any]]]) -> dict[str, Any]:
    matrix = [[0 for _ in range(24)] for _ in WEEKDAY_ORDER]
    for start, _ in rows:
        matrix[start.weekday()][start.hour] += 1
    return {
        "weekdays": WEEKDAY_LABELS,
        "hours": list(range(24)),
        "matrix": matrix,
    }


def process_twilio_data(
    call_data: list[dict[str, Any]],
    start_dt: date | datetime | None,
    end_dt: date | datetime | None,
    *,
    include_call_details: bool = False,
) -> dict[str, Any] | None:
    if not call_data:
        return None

    prepared: list[tuple[datetime, dict[str, Any]]] = []
    for raw in call_data:
        start = _parse_start(raw.get("start_time"))
        if start is None:
            continue
        prepared.append((start, raw))
    if not prepared:
        return None

    bound_start = inclusive_start_datetime(start_dt) if start_dt is not None else None
    exclusive_end = exclusive_end_datetime(end_dt) if end_dt is not None else None

    filtered: list[tuple[datetime, dict[str, Any]]] = []
    for start, row in prepared:
        if bound_start is not None and start < bound_start:
            continue
        if exclusive_end is not None and start >= exclusive_end:
            continue
        filtered.append((start, row))
    if not filtered:
        return None

    rows_only = [row for _, row in filtered]
    total_calls = len(filtered)
    duration_sum = sum(_as_int(row.get("duration_sec")) or 0 for row in rows_only)
    total_minutes = duration_sum / 60.0
    avg_minutes = (duration_sum / 60.0 / total_calls) if total_calls else 0.0
    total_cost = sum(_as_float(row.get("price")) or 0.0 for row in rows_only)
    top_countries = compute_top_countries(rows_only, top_n=15)

    payload: dict[str, Any] = {
        "total_calls": int(total_calls),
        "total_duration": round(total_minutes, 2),
        "avg_duration": round(avg_minutes, 2),
        "total_cost": round(float(total_cost), 4),
        "calls_over_time": _series_calls_over_time(filtered),
        "duration_distribution": _series_duration_distribution(rows_only),
        "cost_over_time": _series_cost_over_time(filtered),
        "top_numbers": _series_top_numbers(rows_only),
        "peak_hours_days": _series_peak_heatmap(filtered),
        "top_countries": top_countries,
        "geo_country_counts": [
            {"country": c["country"], "iso3": c["iso3"], "calls": c["calls"]}
            for c in compute_top_countries(rows_only, top_n=50)
        ],
    }
    if include_call_details:
        details = []
        for start, row in filtered:
            item = dict(row)
            item["start_time"] = start.strftime("%Y-%m-%dT%H:%M:%SZ")
            details.append(item)
        payload["call_details"] = details
    return payload


def _empty_summary() -> dict[str, Any]:
    return {
        "total_calls": 0,
        "total_duration": 0,
        "avg_duration": 0,
        "total_cost": 0,
        "calls_over_time": {"labels": [], "values": []},
        "duration_distribution": {"labels": [], "values": []},
        "cost_over_time": {"labels": [], "values": []},
        "top_numbers": {"labels": [], "values": []},
        "peak_hours_days": {
            "weekdays": WEEKDAY_LABELS,
            "hours": list(range(24)),
            "matrix": [[0 for _ in range(24)] for _ in WEEKDAY_ORDER],
        },
        "top_countries": [],
        "geo_country_counts": [],
    }


def analytics_summary(
    db: Session,
    user_id: int,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, Any]:
    from app.core.cache import cache_get, cache_set

    cache_key = f"analytics:summary:{user_id}:{start}:{end}"
    cached = cache_get(cache_key)
    if isinstance(cached, dict):
        return cached

    # Prefer normalized TwilioCall rows (Phase 10).
    stmt = select(TwilioCall).where(TwilioCall.user_id == user_id)
    if start:
        stmt = stmt.where(TwilioCall.start_time >= inclusive_start_datetime(start))
    if end:
        stmt = stmt.where(TwilioCall.start_time < exclusive_end_datetime(end))
    rows = list(db.scalars(stmt.order_by(TwilioCall.start_time.asc())).all())

    all_calls: list[dict[str, Any]] = [
        {
            "sid": r.sid,
            "from": r.from_number,
            "to": r.to_number,
            "start_time": r.start_time.isoformat() if r.start_time else None,
            "duration_sec": r.duration_sec,
            "price": float(r.price) if r.price is not None else None,
            "price_unit": r.price_unit,
            "direction": r.direction,
        }
        for r in rows
    ]

    # Fallback: legacy daily JSON blobs for this user.
    if not all_calls:
        a_stmt = select(TwilioCallAnalytics).where(TwilioCallAnalytics.user_id == user_id)
        if start:
            a_stmt = a_stmt.where(TwilioCallAnalytics.date >= start)
        if end:
            a_stmt = a_stmt.where(TwilioCallAnalytics.date <= end)
        for row in db.scalars(a_stmt.order_by(TwilioCallAnalytics.date.asc())).all():
            data = row.call_data
            if isinstance(data, list):
                all_calls.extend(data)
            elif isinstance(data, dict) and "calls" in data:
                all_calls.extend(data["calls"])

    # Compact chart JSON only — no call_details / PNG / GeoJSON payloads.
    processed = process_twilio_data(
        all_calls, start, end, include_call_details=False
    )
    if processed is None:
        return _empty_summary()
    cache_set(cache_key, processed, ttl_seconds=300)
    return processed


def _parse_call_start(value: str | None) -> datetime | None:
    return _parse_start(value)


def upsert_twilio_calls(
    db: Session, user_id: int, call_data: list[dict[str, Any]]
) -> int:
    """Idempotent upsert by (user_id, sid). Returns number of rows touched."""
    touched = 0
    for item in call_data:
        sid = item.get("sid")
        if not sid:
            continue
        existing = db.scalar(
            select(TwilioCall).where(
                TwilioCall.user_id == user_id, TwilioCall.sid == sid
            )
        )
        start_time = _parse_call_start(item.get("start_time"))
        price = item.get("price")
        fields = {
            "from_number": item.get("from"),
            "to_number": item.get("to"),
            "start_time": start_time,
            "duration_sec": item.get("duration_sec"),
            "price": price,
            "price_unit": item.get("price_unit"),
            "direction": item.get("direction"),
        }
        if existing is None:
            db.add(TwilioCall(user_id=user_id, sid=sid, **fields))
        else:
            for key, value in fields.items():
                setattr(existing, key, value)
        touched += 1
    db.commit()
    return touched


def fetch_and_store_twilio(
    db: Session,
    *,
    user_id: int,
    account_sid: str,
    auth_token: str,
    limit: int = 100,
) -> dict[str, Any]:
    """Incremental Twilio sync for one tenant (Phase 10.2–10.3)."""
    from app.core.cache import invalidate_user_analytics_caches
    from app.db.models import User

    user = db.get(User, user_id)
    if user is None:
        raise ValueError("user not found")

    provider = TwilioProvider(account_sid=account_sid, auth_token=auth_token)
    start_after = user.twilio_last_synced_at
    call_data = provider.fetch_calls(limit=limit, start_time_after=start_after)
    upsert_twilio_calls(db, user_id, call_data)

    today = date.today()
    metrics = process_twilio_data(call_data, None, None) or {}
    existing = db.scalar(
        select(TwilioCallAnalytics).where(
            TwilioCallAnalytics.user_id == user_id,
            TwilioCallAnalytics.date == today,
        )
    )
    if existing:
        prev = existing.call_data if isinstance(existing.call_data, dict) else {}
        prev_calls = list(prev.get("calls") or [])
        by_sid = {c.get("sid"): c for c in prev_calls if c.get("sid")}
        for c in call_data:
            if c.get("sid"):
                by_sid[c["sid"]] = c
        existing.call_data = {"calls": list(by_sid.values())}
        existing.processed_metrics = (
            process_twilio_data(list(by_sid.values()), None, None) or metrics
        )
    else:
        db.add(
            TwilioCallAnalytics(
                user_id=user_id,
                date=today,
                call_data={"calls": call_data},
                processed_metrics=metrics,
            )
        )

    newest = user.twilio_last_synced_at
    for item in call_data:
        st = _parse_call_start(item.get("start_time"))
        if st is not None and (newest is None or st > newest):
            newest = st
    if newest is not None:
        user.twilio_last_synced_at = newest
    db.commit()
    invalidate_user_analytics_caches(user_id)
    result = metrics if metrics else {"total_calls": 0, "synced": len(call_data)}
    result["message"] = "Twilio data synced"
    result["synced"] = len(call_data)
    return result
