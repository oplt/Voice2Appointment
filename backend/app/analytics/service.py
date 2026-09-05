"""Analytics: compact JSON chart series for the SPA (no matplotlib/folium/pandas)."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import phonenumbers
import pycountry
from sqlalchemy.orm import Session

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
    from app.analytics.aggregate import provider_price_to_net_cost

    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        iso2 = _infer_iso2_from_row(row)
        iso3 = _iso3_from_iso2(iso2) if iso2 else None
        if not iso3:
            continue
        bucket = buckets.setdefault(
            iso3, {"calls": 0, "costs": defaultdict(float), "duration_sum": 0.0}
        )
        bucket["calls"] += 1
        currency = str(row.get("price_unit") or "UNKNOWN").upper()
        bucket["costs"][currency] += provider_price_to_net_cost(row.get("price"))
        bucket["duration_sum"] += float(_as_int(row.get("duration_sec")) or 0)
    ranked = []
    for iso3, stats in buckets.items():
        calls = int(stats["calls"])
        avg_min = (stats["duration_sum"] / 60.0 / calls) if calls else 0.0
        costs = {
            currency: round(amount, 4)
            for currency, amount in sorted(stats["costs"].items())
        }
        one_currency = next(iter(costs)) if len(costs) == 1 else None
        ranked.append(
            {
                "country": _country_name_from_iso(iso3),
                "iso3": iso3,
                "calls": calls,
                "total_cost": costs[one_currency] if one_currency else None,
                "currency": one_currency,
                "costs_by_currency": costs,
                "avg_duration_min": round(avg_min, 2),
            }
        )
    ranked.sort(
        key=lambda row: -int(row["calls"])
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


def _series_cost_over_time(
    rows: list[tuple[datetime, dict[str, Any]]], currency: str | None
) -> tuple[dict[str, list], dict[str, dict[str, list]]]:
    from app.analytics.aggregate import provider_price_to_net_cost

    totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for start, row in rows:
        unit = str(row.get("price_unit") or "UNKNOWN").upper()
        totals[unit][start.date().isoformat()] += provider_price_to_net_cost(
            row.get("price")
        )
    by_currency = {
        unit: {
            "labels": sorted(days),
            "values": [round(days[day], 4) for day in sorted(days)],
        }
        for unit, days in sorted(totals.items())
    }
    return by_currency.get(currency or "", {"labels": [], "values": []}), by_currency


def _series_top_numbers(
    rows: list[dict[str, Any]], *, user_id: int = 0
) -> dict[str, list]:
    from app.analytics.aggregate import mask_phone_label

    counts: Counter[str] = Counter()
    for row in rows:
        to_num = row.get("to")
        if to_num:
            counts[str(to_num)] += 1
    top = counts.most_common(10)
    return {
        "labels": [mask_phone_label(label, user_id=user_id) for label, _ in top],
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
    user_id: int = 0,
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
    from app.analytics.aggregate import provider_price_to_net_cost

    total_cost = 0.0
    by_currency: dict[str, dict[str, float]] = {}
    for row in rows_only:
        price = provider_price_to_net_cost(row.get("price"))
        unit = (row.get("price_unit") or "UNKNOWN").upper()
        bucket = by_currency.setdefault(unit, {"calls": 0, "total_cost": 0.0})
        bucket["calls"] += 1
        bucket["total_cost"] += price
        total_cost += price
    reporting = None
    if len(by_currency) == 1:
        reporting = next(iter(by_currency))
        total_cost = by_currency[reporting]["total_cost"]
    elif len(by_currency) > 1:
        total_cost = None  # mixed currencies — use totals_by_currency

    top_countries = compute_top_countries(rows_only, top_n=15)
    cost_over_time, cost_over_time_by_currency = _series_cost_over_time(
        filtered, reporting
    )

    payload: dict[str, Any] = {
        "total_calls": int(total_calls),
        "total_duration": round(total_minutes, 2),
        "avg_duration": round(avg_minutes, 2),
        "total_cost": None if total_cost is None else round(float(total_cost), 4),
        "totals_by_currency": {
            unit: {
                "calls": int(stats["calls"]),
                "total_cost": round(stats["total_cost"], 4),
            }
            for unit, stats in sorted(by_currency.items())
        },
        "reporting_currency": reporting,
        "currency": reporting,
        "timezone": "UTC",
        "calls_over_time": _series_calls_over_time(filtered),
        "duration_distribution": _series_duration_distribution(rows_only),
        "cost_over_time": cost_over_time,
        "cost_over_time_by_currency": cost_over_time_by_currency,
        "top_numbers": _series_top_numbers(rows_only, user_id=user_id),
        "peak_hours_days": _series_peak_heatmap(filtered),
        "top_countries": top_countries,
        "geo_country_counts": [
            {"country": c["country"], "iso3": c["iso3"], "calls": c["calls"]}
            for c in compute_top_countries(rows_only, top_n=50)
        ],
        "phone_reidentification_allowed": False,
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
        "cost_over_time_by_currency": {},
        "top_numbers": {"labels": [], "values": []},
        "peak_hours_days": {
            "weekdays": WEEKDAY_LABELS,
            "hours": list(range(24)),
            "matrix": [[0 for _ in range(24)] for _ in WEEKDAY_ORDER],
        },
        "top_countries": [],
        "geo_country_counts": [],
        "totals_by_currency": {},
        "reporting_currency": None,
        "currency": None,
        "timezone": "UTC",
        "range": {"start": None, "end": None},
        "truncated": False,
        "generated_at": None,
        "source_synced_at": None,
        "stale": False,
        "stale_reason": None,
        "cache_status": "miss",
        "funnel": None,
        "comparison": None,
        "phone_reidentification_allowed": False,
    }


class AnalyticsRangeError(ValueError):
    """Invalid analytics date range (HTTP 422)."""


def _tenant_timezone(db: Session, user_id: int) -> str:
    from app.calendars.service import get_auth_record
    from app.core.config import settings as app_settings

    auth = get_auth_record(db, user_id)
    return (
        (auth.time_zone if auth and auth.time_zone else None)
        or app_settings.default_timezone
        or "UTC"
    )


def analytics_meta(
    db: Session,
    user_id: int,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Tenant timezone and permitted range metadata for filter defaults."""
    from zoneinfo import ZoneInfo

    from app.core.config import settings as app_settings

    tz_name = _tenant_timezone(db, user_id)
    zone = ZoneInfo(tz_name)
    current = now or datetime.now(timezone.utc)
    local_today = current.astimezone(zone).date()
    default_days = app_settings.analytics_default_range_days
    default_end = local_today
    default_start = default_end - timedelta(days=default_days - 1)
    return {
        "timezone": tz_name,
        "today": local_today.isoformat(),
        "default_range_days": default_days,
        "max_range_days": app_settings.analytics_max_range_days,
        "default_range": {
            "start": default_start.isoformat(),
            "end": default_end.isoformat(),
        },
    }


def resolve_analytics_window(
    start: date | None,
    end: date | None,
    *,
    timezone_name: str,
    now: datetime | None = None,
) -> tuple[date, date, str]:
    """Return inclusive local dates and the IANA timezone used."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    from app.core.config import settings as app_settings

    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise AnalyticsRangeError("timezone must be a valid IANA timezone") from exc

    current = now or datetime.now(timezone.utc)
    local_today = current.astimezone(ZoneInfo(timezone_name)).date()
    if start is None and end is None:
        end = local_today
        start = end - timedelta(days=app_settings.analytics_default_range_days - 1)
    elif start is None:
        start = end  # type: ignore[assignment]
    elif end is None:
        end = start
    assert start is not None and end is not None
    if start > end:
        raise AnalyticsRangeError("start must be on or before end")
    span = (end - start).days + 1
    if span > app_settings.analytics_max_range_days:
        raise AnalyticsRangeError(
            f"range cannot exceed {app_settings.analytics_max_range_days} days"
        )
    return start, end, timezone_name


def _local_bounds(
    start: date, end: date, timezone_name: str
) -> tuple[datetime, datetime]:
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(timezone_name)
    bound_start = inclusive_start_datetime(start, tz=zone)
    bound_end = exclusive_end_datetime(end, tz=zone)
    return bound_start, bound_end


def _metric_delta(current: float | int | None, prior: float | int | None) -> dict[str, Any]:
    cur = 0 if current is None else float(current)
    prv = 0 if prior is None else float(prior)
    delta = cur - prv
    pct = None if prv == 0 else round(delta / prv, 4)
    return {"current": cur, "prior": prv, "delta": round(delta, 4), "delta_pct": pct}


def analytics_summary(
    db: Session,
    user_id: int,
    start: date | None = None,
    end: date | None = None,
    *,
    timezone_name: str | None = None,
    compare: bool = False,
) -> dict[str, Any]:
    from zoneinfo import ZoneInfo

    from app.analytics.aggregate import aggregate_twilio_sql, prior_period
    from app.analytics.funnel import funnel_summary
    from app.core.cache import (
        CACHE_TTL_ANALYTICS,
        CACHE_TTL_ANALYTICS_EMPTY,
        cache_get,
        cache_set,
        durable_versioned_key,
    )
    from app.core.config import settings as app_settings
    from app.db.models import User

    tz_name = timezone_name or _tenant_timezone(db, user_id)
    start, end, tz_name = resolve_analytics_window(start, end, timezone_name=tz_name)
    zone = ZoneInfo(tz_name)
    currency_key = (app_settings.reporting_currency or "auto").lower()

    cache_key = durable_versioned_key(
        db, user_id, "analytics", start, end, tz_name, currency_key, int(compare)
    )
    cached = cache_get(cache_key)
    if isinstance(cached, dict):
        hit = dict(cached)
        hit["cache_status"] = "hit"
        generated = hit.get("generated_at")
        age = None
        if isinstance(generated, str):
            try:
                gen_dt = datetime.fromisoformat(generated.replace("Z", "+00:00"))
                age = max(0, int((datetime.now(timezone.utc) - gen_dt).total_seconds()))
            except ValueError:
                age = None
        hit["cache_age_seconds"] = age
        return hit

    bound_start, bound_end = _local_bounds(start, end, tz_name)
    now = datetime.now(timezone.utc)
    user = db.get(User, user_id)
    synced_at = user.twilio_last_synced_at if user else None
    stale = False
    stale_reason = None
    if synced_at is not None:
        if (now - synced_at) > timedelta(hours=48):
            stale = True
            stale_reason = "source_older_than_48h"
    elif user and (user.twilio_account_sid and user.twilio_auth_token):
        stale = True
        stale_reason = "never_synced"

    try:
        processed = aggregate_twilio_sql(
            db,
            user_id,
            bound_start=bound_start,
            bound_end=bound_end,
            zone=zone,
            reporting_currency=app_settings.reporting_currency or None,
        )
    except Exception:
        # Observable failure — do not materialize raw TwilioCall rows in Python.
        raise

    # Normalized TwilioCall rows only; legacy raw call_data snapshots are not used.
    if processed is None:
        processed = _empty_summary()
        ttl = CACHE_TTL_ANALYTICS_EMPTY
    else:
        ttl = CACHE_TTL_ANALYTICS

    if app_settings.reporting_currency and processed.get("totals_by_currency"):
        wanted = app_settings.reporting_currency
        bucket = processed["totals_by_currency"].get(wanted)
        processed["reporting_currency"] = wanted
        processed["total_cost"] = bucket["total_cost"] if bucket else 0
        processed["cost_over_time"] = processed.get(
            "cost_over_time_by_currency", {}
        ).get(wanted, {"labels": [], "values": []})
    elif processed.get("total_cost") is None and processed.get("totals_by_currency"):
        # Mixed currencies: keep per-currency series only; never a blended cost_over_time.
        processed["cost_over_time"] = {"labels": [], "values": []}
        processed["reporting_currency"] = None

    currency = processed.get("reporting_currency")
    processed["currency"] = currency
    processed["timezone"] = tz_name
    processed["range"] = {"start": start.isoformat(), "end": end.isoformat()}
    processed.setdefault("truncated", False)
    processed["generated_at"] = now.isoformat()
    processed["source_synced_at"] = synced_at.isoformat() if synced_at else None
    processed["stale"] = stale
    processed["stale_reason"] = stale_reason
    processed["cache_status"] = "miss"
    processed["cache_age_seconds"] = 0
    processed["phone_reidentification_allowed"] = False
    processed["funnel"] = funnel_summary(
        db, user_id, start=start, end=end, timezone_name=tz_name
    )

    comparison = None
    if compare:
        p_start, p_end = prior_period(start, end)
        p_bound_start, p_bound_end = _local_bounds(p_start, p_end, tz_name)
        prior = aggregate_twilio_sql(
            db,
            user_id,
            bound_start=p_bound_start,
            bound_end=p_bound_end,
            zone=zone,
            reporting_currency=app_settings.reporting_currency or None,
        )
        prior = prior or _empty_summary()
        comparison = {
            "range": {"start": p_start.isoformat(), "end": p_end.isoformat()},
            "label": f"Prior { (end - start).days + 1 } day(s): {p_start.isoformat()} → {p_end.isoformat()}",
            "total_calls": _metric_delta(
                processed.get("total_calls"), prior.get("total_calls")
            ),
            "total_duration": _metric_delta(
                processed.get("total_duration"), prior.get("total_duration")
            ),
        }
    processed["comparison"] = comparison

    cache_set(cache_key, processed, ttl_seconds=ttl)
    return processed


from app.analytics.sync import fetch_and_store_twilio as _fetch_and_store_twilio, upsert_twilio_calls  # noqa: E402,F401
from app.telephony.providers.twilio import TwilioProvider  # noqa: E402


def fetch_and_store_twilio(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Keep the historical service-level provider seam for callers and tests."""
    return _fetch_and_store_twilio(*args, provider_factory=TwilioProvider, **kwargs)
