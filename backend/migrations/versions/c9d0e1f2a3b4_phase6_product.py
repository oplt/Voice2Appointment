"""Phase 6: notifications, retention, transfer prefs, purge markers.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_delivery",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("res_user.id"), nullable=False),
        sa.Column(
            "appointment_id",
            sa.Integer(),
            sa.ForeignKey("appointment.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False, server_default="email"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_notification_delivery_idem"),
    )
    op.create_index(
        "ix_notification_delivery_user_appt",
        "notification_delivery",
        ["user_id", "appointment_id", "kind"],
    )
    with op.batch_alter_table("callsession") as batch_op:
        batch_op.add_column(
            sa.Column("content_purged_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("transfer_attempted_at", sa.DateTime(timezone=True), nullable=True)
        )
    with op.batch_alter_table("appointment") as batch_op:
        batch_op.add_column(
            sa.Column("transcript_purged_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("confirmation_sent_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("appointment") as batch_op:
        batch_op.drop_column("confirmation_sent_at")
        batch_op.drop_column("transcript_purged_at")
    with op.batch_alter_table("callsession") as batch_op:
        batch_op.drop_column("transfer_attempted_at")
        batch_op.drop_column("content_purged_at")
    op.drop_index("ix_notification_delivery_user_appt", table_name="notification_delivery")
    op.drop_table("notification_delivery")
