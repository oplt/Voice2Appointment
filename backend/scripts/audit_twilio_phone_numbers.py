"""Audit legacy Twilio routing values without printing phone-number PII."""

from __future__ import annotations

import json
import os
from collections import defaultdict

from sqlalchemy import create_engine, text

from app.telephony.phones import canonical_e164


def audit(database_url: str) -> dict[str, object]:
    engine = create_engine(database_url)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT id, twilio_phone_number FROM res_user "
                "WHERE twilio_phone_number IS NOT NULL ORDER BY id"
            )
        ).all()
    engine.dispose()

    valid_ids: list[int] = []
    invalid_ids: list[int] = []
    ambiguous_ids: list[int] = []
    owners: dict[str, list[int]] = defaultdict(list)
    for user_id, raw in rows:
        value = str(raw).strip()
        if not value.startswith("+"):
            ambiguous_ids.append(int(user_id))
            continue
        canonical = canonical_e164(value)
        if canonical is None:
            invalid_ids.append(int(user_id))
            continue
        valid_ids.append(int(user_id))
        owners[canonical].append(int(user_id))
    duplicate_groups = [ids for ids in owners.values() if len(ids) > 1]
    return {
        "rows": len(rows),
        "valid_user_ids": valid_ids,
        "invalid_user_ids": invalid_ids,
        "ambiguous_region_user_ids": ambiguous_ids,
        "duplicate_user_id_groups": duplicate_groups,
        "ok": not invalid_ids and not ambiguous_ids and not duplicate_groups,
    }


def main() -> int:
    database_url = (os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    result = audit(database_url)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
