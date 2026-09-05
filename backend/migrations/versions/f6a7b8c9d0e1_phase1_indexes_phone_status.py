"""Phase 1: indexes, E.164 routing, Twilio call status.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
"""

from __future__ import annotations

from collections import defaultdict

import phonenumbers
import sqlalchemy as sa
from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def _canonical_e164(raw: str) -> str | None:
    """Canonicalize only unambiguous legacy E.164 input."""
    value = raw.strip()
    if not value.startswith("+"):
        return None
    try:
        parsed = phonenumbers.parse(value, None)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def _preflight_legacy_phone_numbers() -> dict[int, str]:
    """Account for every configured value before changing routing ownership."""
    bind = op.get_bind()
    rows = list(
        bind.execute(
            sa.text(
                "SELECT id, twilio_phone_number FROM res_user "
                "WHERE twilio_phone_number IS NOT NULL ORDER BY id"
            )
        )
    )
    canonical_by_id: dict[int, str] = {}
    invalid: list[int] = []
    owners: dict[str, list[int]] = defaultdict(list)
    for user_id, raw in rows:
        canonical = _canonical_e164(str(raw))
        if canonical is None:
            invalid.append(int(user_id))
            continue
        canonical_by_id[int(user_id)] = canonical
        owners[canonical].append(int(user_id))

    duplicate_ids = sorted(
        user_id for ids in owners.values() if len(ids) > 1 for user_id in ids
    )
    if invalid or duplicate_ids:
        raise RuntimeError(
            "Twilio phone preflight failed; resolve the reported user IDs before "
            "retrying. Non-E.164 legacy values require an explicit country context. "
            f"invalid_or_ambiguous_user_ids={invalid}; "
            f"duplicate_user_ids={duplicate_ids}"
        )
    return canonical_by_id


def upgrade() -> None:
    canonical_by_id = _preflight_legacy_phone_numbers()
    with op.batch_alter_table("res_user") as batch_op:
        batch_op.add_column(sa.Column("twilio_phone_e164", sa.String(length=20), nullable=True))
    for user_id, canonical in canonical_by_id.items():
        op.get_bind().execute(
            sa.text(
                "UPDATE res_user SET twilio_phone_e164 = :e164 WHERE id = :id"
            ),
            {"e164": canonical, "id": user_id},
        )
    with op.batch_alter_table("res_user") as batch_op:
        batch_op.create_index(
            "ix_res_user_twilio_phone_e164", ["twilio_phone_e164"], unique=True
        )

    with op.batch_alter_table("twilio_call") as batch_op:
        batch_op.add_column(sa.Column("status", sa.String(length=32), nullable=True))
        batch_op.create_index("ix_twilio_call_user_status", ["user_id", "status"])

    op.create_index(
        "ix_callsession_user_started",
        "callsession",
        ["user_id", "started_at"],
    )
    op.create_index(
        "ix_appointment_user_start_id",
        "appointment",
        ["user_id", "start_datetime", "id"],
    )

def downgrade() -> None:
    op.drop_index("ix_appointment_user_start_id", table_name="appointment")
    op.drop_index("ix_callsession_user_started", table_name="callsession")
    with op.batch_alter_table("twilio_call") as batch_op:
        batch_op.drop_index("ix_twilio_call_user_status")
        batch_op.drop_column("status")
    with op.batch_alter_table("res_user") as batch_op:
        batch_op.drop_index("ix_res_user_twilio_phone_e164")
        batch_op.drop_column("twilio_phone_e164")
