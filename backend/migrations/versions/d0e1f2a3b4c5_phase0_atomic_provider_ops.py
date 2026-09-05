"""Phase 0: replay-safe streams and durable provider operations.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("callsession") as batch_op:
        batch_op.add_column(sa.Column("stream_token_ciphertext", sa.Text(), nullable=True))

    bind = op.get_bind()
    duplicate = bind.execute(
        sa.text(
            """
            SELECT user_id, google_calendar_event_id
            FROM appointment
            WHERE google_calendar_event_id IS NOT NULL
            GROUP BY user_id, google_calendar_event_id
            HAVING count(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot add provider event uniqueness: duplicate tenant event IDs exist"
        )

    json_type = sa.JSON().with_variant(
        postgresql.JSONB(astext_type=sa.Text()), "postgresql"
    )
    with op.batch_alter_table("appointment") as batch_op:
        batch_op.add_column(sa.Column("provider_operation", sa.String(32), nullable=True))
        batch_op.add_column(
            sa.Column("provider_operation_payload", json_type, nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "provider_attempt_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column("provider_last_error_code", sa.String(64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("provider_next_retry_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "provider_calendar_id",
                sa.String(255),
                nullable=False,
                server_default="primary",
            )
        )
        batch_op.create_unique_constraint(
            "uq_appointment_user_google_event",
            ["user_id", "google_calendar_event_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("appointment") as batch_op:
        batch_op.drop_constraint(
            "uq_appointment_user_google_event", type_="unique"
        )
        batch_op.drop_column("provider_calendar_id")
        batch_op.drop_column("provider_next_retry_at")
        batch_op.drop_column("provider_last_error_code")
        batch_op.drop_column("provider_attempt_count")
        batch_op.drop_column("provider_operation_payload")
        batch_op.drop_column("provider_operation")

    with op.batch_alter_table("callsession") as batch_op:
        batch_op.drop_column("stream_token_ciphertext")
