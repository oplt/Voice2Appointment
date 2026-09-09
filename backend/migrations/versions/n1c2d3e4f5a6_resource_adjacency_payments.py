"""Add ResourceAdjacency and PaymentIntent tables.

Revision ID: n1c2d3e4f5a6
Revises: m1c2d3e4f5a6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "n1c2d3e4f5a6"
down_revision = "m1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resource_adjacency",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "resource_a_id",
            sa.Integer(),
            sa.ForeignKey("resource.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "resource_b_id",
            sa.Integer(),
            sa.ForeignKey("resource.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "resource_a_id < resource_b_id", name="ck_resource_adjacency_ordered"
        ),
        sa.UniqueConstraint(
            "resource_a_id", "resource_b_id", name="uq_resource_adjacency_pair"
        ),
    )
    op.create_index(
        "ix_resource_adjacency_organization_id",
        "resource_adjacency",
        ["organization_id"],
    )
    op.create_index(
        "ix_resource_adjacency_resource_a_id", "resource_adjacency", ["resource_a_id"]
    )
    op.create_index(
        "ix_resource_adjacency_resource_b_id", "resource_adjacency", ["resource_b_id"]
    )

    op.create_table(
        "payment_intent",
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
            sa.ForeignKey("reservation.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "customer_id",
            sa.Integer(),
            sa.ForeignKey("customer.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="EUR"),
        sa.Column("purpose", sa.String(length=32), nullable=False, server_default="deposit"),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("provider_ref", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column(
            "secure_link_delivery_id",
            sa.Integer(),
            sa.ForeignKey("secure_link_delivery.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_payment_intent_organization_id", "payment_intent", ["organization_id"]
    )
    op.create_index(
        "ix_payment_intent_org_status", "payment_intent", ["organization_id", "status"]
    )
    op.create_index(
        "ix_payment_intent_reservation_id", "payment_intent", ["reservation_id"]
    )
    op.create_index("ix_payment_intent_customer_id", "payment_intent", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_intent_customer_id", table_name="payment_intent")
    op.drop_index("ix_payment_intent_reservation_id", table_name="payment_intent")
    op.drop_index("ix_payment_intent_org_status", table_name="payment_intent")
    op.drop_index("ix_payment_intent_organization_id", table_name="payment_intent")
    op.drop_table("payment_intent")

    op.drop_index("ix_resource_adjacency_resource_b_id", table_name="resource_adjacency")
    op.drop_index("ix_resource_adjacency_resource_a_id", table_name="resource_adjacency")
    op.drop_index(
        "ix_resource_adjacency_organization_id", table_name="resource_adjacency"
    )
    op.drop_table("resource_adjacency")
