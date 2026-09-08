"""Extend reservation for availability/hold/sync engine fields.

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a9b0c1d2e3f4"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reservation", sa.Column("catalog_item_id", sa.Integer(), sa.ForeignKey("catalog_item.id"), nullable=True))
    op.add_column(
        "reservation",
        sa.Column("scheduling_mode", sa.String(32), nullable=False, server_default="single_resource"),
    )
    op.add_column("reservation", sa.Column("hold_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reservation", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.add_column(
        "reservation",
        sa.Column("provider_sync_status", sa.String(32), nullable=False, server_default="none"),
    )
    op.add_column(
        "reservation",
        sa.Column("allocation_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_index("ix_reservation_catalog_item_id", "reservation", ["catalog_item_id"])
    op.create_index(
        "ix_reservation_org_window",
        "reservation",
        ["organization_id", "start_datetime", "end_datetime"],
    )
    op.create_unique_constraint(
        "uq_reservation_org_idempotency",
        "reservation",
        ["organization_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_reservation_org_idempotency", "reservation", type_="unique")
    op.drop_index("ix_reservation_org_window", table_name="reservation")
    op.drop_index("ix_reservation_catalog_item_id", table_name="reservation")
    for column in (
        "allocation_json",
        "provider_sync_status",
        "idempotency_key",
        "hold_expires_at",
        "scheduling_mode",
        "catalog_item_id",
    ):
        op.drop_column("reservation", column)
