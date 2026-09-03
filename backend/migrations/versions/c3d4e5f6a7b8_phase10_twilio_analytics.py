"""Phase 10: tenant-scoped Twilio analytics + normalized call rows.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("res_user") as batch_op:
        batch_op.add_column(
            sa.Column("twilio_last_synced_at", sa.DateTime(timezone=True), nullable=True)
        )

    with op.batch_alter_table("twilio_call_analytics") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))

    # Backfill: assign orphan analytics rows to the oldest user when present.
    bind = op.get_bind()
    first_user = bind.execute(sa.text("SELECT id FROM res_user ORDER BY id ASC LIMIT 1")).scalar()
    if first_user is not None:
        bind.execute(
            sa.text(
                "UPDATE twilio_call_analytics SET user_id = :uid WHERE user_id IS NULL"
            ),
            {"uid": first_user},
        )
    else:
        bind.execute(sa.text("DELETE FROM twilio_call_analytics WHERE user_id IS NULL"))

    with op.batch_alter_table("twilio_call_analytics") as batch_op:
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_index(
            batch_op.f("ix_twilio_call_analytics_user_id"), ["user_id"], unique=False
        )
        batch_op.create_foreign_key(
            "fk_twilio_call_analytics_user_id_res_user",
            "res_user",
            ["user_id"],
            ["id"],
        )
        batch_op.create_unique_constraint(
            "uq_twilio_analytics_user_date", ["user_id", "date"]
        )

    op.create_table(
        "twilio_call",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("sid", sa.String(length=64), nullable=False),
        sa.Column("from_number", sa.String(length=32), nullable=True),
        sa.Column("to_number", sa.String(length=32), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("price", sa.Numeric(10, 4), nullable=True),
        sa.Column("price_unit", sa.String(length=16), nullable=True),
        sa.Column("direction", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["res_user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "sid", name="uq_twilio_call_user_sid"),
    )
    with op.batch_alter_table("twilio_call") as batch_op:
        batch_op.create_index(
            batch_op.f("ix_twilio_call_user_id"), ["user_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_twilio_call_sid"), ["sid"], unique=False)
        batch_op.create_index(
            "ix_twilio_call_user_start", ["user_id", "start_time"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("twilio_call") as batch_op:
        batch_op.drop_index("ix_twilio_call_user_start")
        batch_op.drop_index(batch_op.f("ix_twilio_call_sid"))
        batch_op.drop_index(batch_op.f("ix_twilio_call_user_id"))
    op.drop_table("twilio_call")

    with op.batch_alter_table("twilio_call_analytics") as batch_op:
        batch_op.drop_constraint("uq_twilio_analytics_user_date", type_="unique")
        batch_op.drop_constraint(
            "fk_twilio_call_analytics_user_id_res_user", type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_twilio_call_analytics_user_id"))
        batch_op.drop_column("user_id")

    with op.batch_alter_table("res_user") as batch_op:
        batch_op.drop_column("twilio_last_synced_at")
