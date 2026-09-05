"""SQL-backed Twilio analytics aggregates (P5-06)."""

from __future__ import annotations

import hashlib
import hmac
from collections import defaultdict
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import case, cast, func, select
from sqlalchemy.orm import Session
from sqlalchemy.types import Date, Integer

from app.db.models import TwilioCall

WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Default analytics never re-identifies; no privileged unmask path in this API.
PHONE_REIDENTIFICATION_ALLOWED = False


def mask_phone_label(value: str | None, *, user_id: int = 0) -> str:
    """Collision-safe masked label: last-4 + tenant-keyed pseudonym suffix.

    Distinct E.164 numbers that share the same last four digits remain distinguishable
    without exposing the full identifier in default payloads.
    """
    if not value:
        return "***"
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if len(digits) < 4:
        return "***"
    digest = hmac.new(
        f"analytics-phone:{int(user_id)}".encode(),
        digits.encode(),
        hashlib.sha256,
    ).hexdigest()[:4]
    return f"***{digits[-4:]}·{digest}"


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def provider_price_to_net_cost(value: Any) -> float:
    """Twilio debits are negative; expose positive spend and negative credits."""
    return -_as_float(value)


def prior_period(start: date, end: date) -> tuple[date, date]:
    """Equal-length period immediately before ``start`` (inclusive dates)."""
    span = (end - start).days + 1
    prior_end = start.fromordinal(start.toordinal() - 1)
    prior_start = prior_end.fromordinal(prior_end.toordinal() - span + 1)
    return prior_start, prior_end


def aggregate_twilio_sql(
    db: Session,
    user_id: int,
    *,
    bound_start: datetime,
    bound_end: datetime,
    zone: ZoneInfo,
    reporting_currency: str | None = None,
) -> dict[str, Any] | None:
    """Grouped SQL aggregates for TwilioCall in [bound_start, bound_end)."""
    base = (
        TwilioCall.user_id == user_id,
        TwilioCall.start_time >= bound_start,
        TwilioCall.start_time < bound_end,
    )

    totals = db.execute(
        select(
            func.count().label("total_calls"),
            func.coalesce(func.sum(TwilioCall.duration_sec), 0).label("duration_sum"),
        ).where(*base)
    ).one()
    total_calls = int(totals.total_calls or 0)
    if total_calls == 0:
        return None

    duration_sum = int(totals.duration_sum or 0)
    total_minutes = duration_sum / 60.0
    avg_minutes = total_minutes / total_calls if total_calls else 0.0

    currency_rows = db.execute(
        select(
            func.upper(func.coalesce(TwilioCall.price_unit, "UNKNOWN")).label("unit"),
            func.count().label("calls"),
            func.coalesce(func.sum(-TwilioCall.price), 0).label("total_cost"),
        )
        .where(*base)
        .group_by(func.upper(func.coalesce(TwilioCall.price_unit, "UNKNOWN")))
    ).all()
    by_currency: dict[str, dict[str, float]] = {}
    for row in currency_rows:
        unit = str(row.unit or "UNKNOWN")
        by_currency[unit] = {
            "calls": int(row.calls),
            "total_cost": round(_as_float(row.total_cost), 4),
        }

    reporting = reporting_currency or None
    total_cost: float | None = 0.0
    if reporting is not None:
        total_cost = by_currency.get(reporting, {}).get("total_cost", 0.0)
    elif len(by_currency) == 1:
        reporting = next(iter(by_currency))
        total_cost = by_currency[reporting]["total_cost"]
    elif len(by_currency) > 1:
        # Never sum unlike currencies into one total or one unlabeled series.
        total_cost = None
        reporting = None

    bind = db.get_bind()
    dialect = bind.dialect.name if bind is not None else ""
    day_expr: Any
    hour_expr: Any
    dow_expr: Any
    if dialect == "postgresql":
        local_day = func.timezone(str(zone), TwilioCall.start_time)
        day_expr = cast(local_day, Date)
        hour_expr = func.extract("hour", local_day)
        dow_expr = cast((func.extract("dow", local_day) + 6) % 7, Integer)
    else:
        day_expr = func.date(TwilioCall.start_time)
        hour_expr = cast(func.strftime("%H", TwilioCall.start_time), Integer)
        dow_expr = (cast(func.strftime("%w", TwilioCall.start_time), Integer) + 6) % 7

    day_rows = db.execute(
        select(day_expr.label("day"), func.count().label("n"))
        .where(*base)
        .group_by(day_expr)
        .order_by(day_expr)
    ).all()
    calls_labels = [str(r.day) for r in day_rows]
    calls_values = [int(r.n) for r in day_rows]

    cost_rows = db.execute(
        select(
            day_expr.label("day"),
            func.upper(func.coalesce(TwilioCall.price_unit, "UNKNOWN")).label("unit"),
            func.coalesce(func.sum(-TwilioCall.price), 0).label("cost"),
        )
        .where(*base)
        .group_by(day_expr, func.upper(func.coalesce(TwilioCall.price_unit, "UNKNOWN")))
        .order_by(day_expr, func.upper(func.coalesce(TwilioCall.price_unit, "UNKNOWN")))
    ).all()
    costs_by_currency: dict[str, dict[str, list[Any]]] = {}
    for row in cost_rows:
        series = costs_by_currency.setdefault(
            str(row.unit or "UNKNOWN"), {"labels": [], "values": []}
        )
        series["labels"].append(str(row.day))
        series["values"].append(round(_as_float(row.cost), 4))

    if reporting:
        selected_cost = costs_by_currency.get(reporting, {"labels": [], "values": []})
    else:
        selected_cost = {"labels": [], "values": []}

    edges = [0, 1, 2, 5, 10, 20, 30, 60, 120]
    minutes_expr = TwilioCall.duration_sec / 60.0
    bucket_cases = []
    labels: list[str] = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        labels.append(f"{lo}-{hi}")
        bucket_cases.append(
            func.coalesce(
                func.sum(
                    case(
                        (
                            TwilioCall.duration_sec.is_not(None)
                            & (minutes_expr >= lo)
                            & (minutes_expr < hi),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label(f"b{i}")
        )
    labels.append(f"{edges[-1]}+")
    bucket_cases.append(
        func.coalesce(
            func.sum(
                case(
                    (
                        TwilioCall.duration_sec.is_not(None)
                        & (minutes_expr >= edges[-1]),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ).label("b_tail")
    )
    dist = db.execute(select(*bucket_cases).where(*base)).one()
    dist_values = [int(dist[i] or 0) for i in range(len(labels))]

    top_rows = db.execute(
        select(TwilioCall.to_number, func.count().label("n"))
        .where(*base, TwilioCall.to_number.is_not(None))
        .group_by(TwilioCall.to_number)
        .order_by(func.count().desc())
        .limit(10)
    ).all()
    top_numbers = {
        "labels": [mask_phone_label(r.to_number, user_id=user_id) for r in top_rows],
        "values": [int(r.n) for r in top_rows],
    }

    heat_rows = db.execute(
        select(dow_expr.label("dow"), hour_expr.label("hour"), func.count().label("n"))
        .where(*base)
        .group_by(dow_expr, hour_expr)
    ).all()
    matrix = [[0 for _ in range(24)] for _ in range(7)]
    for r in heat_rows:
        try:
            dow = int(r.dow)
            hour = int(r.hour)
        except (TypeError, ValueError):
            continue
        if 0 <= dow < 7 and 0 <= hour < 24:
            matrix[dow][hour] += int(r.n)

    # Bound high-cardinality country grouping: top source numbers only.
    from_rows = db.execute(
        select(
            TwilioCall.from_number,
            func.upper(func.coalesce(TwilioCall.price_unit, "UNKNOWN")).label("unit"),
            func.count().label("n"),
            func.coalesce(func.sum(-TwilioCall.price), 0).label("cost"),
        )
        .where(*base, TwilioCall.from_number.is_not(None))
        .group_by(
            TwilioCall.from_number,
            func.upper(func.coalesce(TwilioCall.price_unit, "UNKNOWN")),
        )
        .order_by(func.count().desc())
        .limit(500)
    ).all()
    top_countries, geo_counts = _countries_from_numbers(
        [
            (r.from_number, int(r.n), str(r.unit), _as_float(r.cost))
            for r in from_rows
        ],
        reporting_currency=reporting,
    )

    return {
        "total_calls": total_calls,
        "total_duration": round(total_minutes, 2),
        "avg_duration": round(avg_minutes, 2),
        "total_cost": None if total_cost is None else round(float(total_cost), 4),
        "totals_by_currency": {
            unit: {
                "calls": int(stats["calls"]),
                "total_cost": round(float(stats["total_cost"]), 4),
            }
            for unit, stats in sorted(by_currency.items())
        },
        "reporting_currency": reporting,
        "calls_over_time": {"labels": calls_labels, "values": calls_values},
        "duration_distribution": {"labels": labels, "values": dist_values},
        "cost_over_time": selected_cost,
        "cost_over_time_by_currency": costs_by_currency,
        "top_numbers": top_numbers,
        "peak_hours_days": {
            "weekdays": WEEKDAY_LABELS,
            "hours": list(range(24)),
            "matrix": matrix,
        },
        "top_countries": top_countries,
        "geo_country_counts": geo_counts,
        "phone_reidentification_allowed": PHONE_REIDENTIFICATION_ALLOWED,
    }


def _countries_from_numbers(
    pairs: list[tuple[str | None, int, str, float]],
    *,
    reporting_currency: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    import phonenumbers
    import pycountry

    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"calls": 0, "costs": defaultdict(float)}
    )
    for raw, n, currency, cost in pairs:
        if not raw or not str(raw).startswith("+"):
            continue
        try:
            num = phonenumbers.parse(str(raw), None)
            reg = phonenumbers.region_code_for_number(num)
        except phonenumbers.NumberParseException:
            continue
        if not reg or len(reg) != 2:
            continue
        country = pycountry.countries.get(alpha_2=reg.upper())
        if not country:
            continue
        buckets[country.alpha_3]["calls"] += n
        buckets[country.alpha_3]["costs"][currency] += cost

    ranked = []
    for iso3, values in buckets.items():
        country = pycountry.countries.get(alpha_3=iso3)
        costs = {
            currency: round(amount, 4)
            for currency, amount in sorted(values["costs"].items())
        }
        one_currency = reporting_currency or (
            next(iter(costs)) if len(costs) == 1 else None
        )
        ranked.append(
            {
                "country": country.name if country else iso3,
                "iso3": iso3,
                "calls": int(values["calls"]),
                "total_cost": (costs.get(one_currency, 0.0) if one_currency else None),
                "currency": one_currency,
                "costs_by_currency": costs,
                "avg_duration_min": 0.0,
            }
        )
    ranked.sort(key=lambda r: -int(r["calls"]))
    top = ranked[:15]
    geo = [
        {"country": c["country"], "iso3": c["iso3"], "calls": c["calls"]}
        for c in ranked[:50]
    ]
    return top, geo
