"""Phase 1: resumable sync, durable cache generations, and bounded indexes.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
"""

from __future__ import annotations

from collections import defaultdict

import phonenumbers
import sqlalchemy as sa
from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def _canonical_e164(raw: str) -> str | None:
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


def _preflight_and_backfill_phones() -> None:
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

    duplicates = {key: ids for key, ids in owners.items() if len(ids) > 1}
    if invalid or duplicates:
        duplicate_ids = sorted({uid for ids in duplicates.values() for uid in ids})
        raise RuntimeError(
            "Twilio phone preflight failed; resolve values before retrying. "
            f"invalid_or_ambiguous_user_ids={invalid}; duplicate_user_ids={duplicate_ids}"
        )

    for user_id, canonical in canonical_by_id.items():
        bind.execute(
            sa.text(
                "UPDATE res_user SET twilio_phone_e164 = :canonical WHERE id = :id"
            ),
            {"canonical": canonical, "id": user_id},
        )


def upgrade() -> None:
    _preflight_and_backfill_phones()
    with op.batch_alter_table("res_user") as batch_op:
        batch_op.add_column(sa.Column("twilio_sync_page_token", sa.String(255)))
        batch_op.add_column(sa.Column("twilio_sync_window_started_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("twilio_sync_window_high_water", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("twilio_active_refresh_cursor", sa.String(64)))
        batch_op.add_column(sa.Column("twilio_active_refresh_due_at", sa.DateTime(timezone=True)))
        for name in (
            "cache_calendar_version",
            "cache_dashboard_version",
            "cache_analytics_version",
            "cache_settings_version",
        ):
            batch_op.add_column(
                sa.Column(name, sa.Integer(), nullable=False, server_default="0")
            )

    with op.batch_alter_table("twilio_call") as batch_op:
        batch_op.add_column(sa.Column("provider_updated_at", sa.DateTime(timezone=True)))

    op.create_index(
        "ix_appointment_user_created", "appointment", ["user_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_appointment_user_created", table_name="appointment")
    with op.batch_alter_table("twilio_call") as batch_op:
        batch_op.drop_column("provider_updated_at")
    with op.batch_alter_table("res_user") as batch_op:
        for name in (
            "cache_settings_version",
            "cache_analytics_version",
            "cache_dashboard_version",
            "cache_calendar_version",
            "twilio_active_refresh_due_at",
            "twilio_active_refresh_cursor",
            "twilio_sync_window_high_water",
            "twilio_sync_window_started_at",
            "twilio_sync_page_token",
        ):
            batch_op.drop_column(name)
