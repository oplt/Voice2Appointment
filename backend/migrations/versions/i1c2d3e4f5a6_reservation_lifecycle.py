"""Add durable reservation lifecycle operation records.

Revision ID: i1c2d3e4f5a6
Revises: h0c1d2e3f4a5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "i1c2d3e4f5a6"
down_revision = "h0c1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reservation_lifecycle_operation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reservation_id",
            sa.Integer(),
            sa.ForeignKey("reservation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="processing"),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("result", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "reservation_id", "operation", "idempotency_key",
            name="uq_reservation_lifecycle_operation_idem",
        ),
    )
    op.create_index(
        "ix_reservation_lifecycle_operation_organization_id",
        "reservation_lifecycle_operation",
        ["organization_id"],
    )
    op.create_index(
        "ix_reservation_lifecycle_operation_reservation_id",
        "reservation_lifecycle_operation",
        ["reservation_id"],
    )
    op.create_index(
        "ix_reservation_lifecycle_operation_org",
        "reservation_lifecycle_operation",
        ["organization_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_reservation_lifecycle_operation_org", table_name="reservation_lifecycle_operation")
    op.drop_index("ix_reservation_lifecycle_operation_reservation_id", table_name="reservation_lifecycle_operation")
    op.drop_index("ix_reservation_lifecycle_operation_organization_id", table_name="reservation_lifecycle_operation")
    op.drop_table("reservation_lifecycle_operation")
