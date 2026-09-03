"""Phase 1: indexes, E.164 routing, Twilio call status.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("res_user") as batch_op:
        batch_op.add_column(sa.Column("twilio_phone_e164", sa.String(length=20), nullable=True))
        batch_op.create_index("ix_res_user_twilio_phone_e164", ["twilio_phone_e164"], unique=True)

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

    # Best-effort backfill; duplicates keep the lowest user id and leave others NULL.
    bind = op.get_bind()
    rows = list(
        bind.execute(sa.text("SELECT id, twilio_phone_number FROM res_user"))
    )
    seen: set[str] = set()
    for user_id, phone in rows:
        if not phone:
            continue
        digits = "".join(ch for ch in str(phone) if ch.isdigit() or ch == "+")
        if not digits:
            continue
        if not digits.startswith("+"):
            digits = "+" + digits
        if digits in seen:
            continue
        seen.add(digits)
        bind.execute(
            sa.text(
                "UPDATE res_user SET twilio_phone_e164 = :e164 WHERE id = :id"
            ),
            {"e164": digits[:20], "id": user_id},
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
