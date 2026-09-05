"""Durable append-only booking funnel events.

Revision ID: f1a2b3c4d5e6
Revises: e1f2a3b4c5d6
"""

import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "booking_funnel_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("res_user.id"), nullable=False),
        sa.Column("call_session_id", sa.Integer(), sa.ForeignKey("callsession.id"), nullable=True),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_booking_funnel_event_key"),
    )
    op.create_index("ix_booking_funnel_event_user_time", "booking_funnel_event", ["user_id", "occurred_at"])
    op.create_index("ix_booking_funnel_event_call_stage", "booking_funnel_event", ["call_session_id", "stage"])


def downgrade() -> None:
    op.drop_table("booking_funnel_event")
