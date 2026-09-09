"""Add Order and SecureLinkDelivery tables for Phase 9 voice tools.

Revision ID: m1c2d3e4f5a6
Revises: l1c2d3e4f5a6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "m1c2d3e4f5a6"
down_revision = "l1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_order",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="unknown"),
        sa.Column(
            "customer_id",
            sa.Integer(),
            sa.ForeignKey("customer.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id", "external_id", name="uq_customer_order_org_external"
        ),
    )
    op.create_index(
        "ix_customer_order_organization_id", "customer_order", ["organization_id"]
    )
    op.create_index("ix_customer_order_customer_id", "customer_order", ["customer_id"])
    op.create_index(
        "ix_customer_order_org_status", "customer_order", ["organization_id", "status"]
    )

    op.create_table(
        "secure_link_delivery",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            sa.Integer(),
            sa.ForeignKey("customer.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("purpose", sa.String(length=64), nullable=False, server_default="payment"),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("recipient", sa.String(length=255), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_ciphertext", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="scheduled"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_secure_link_delivery_idem"),
    )
    op.create_index(
        "ix_secure_link_delivery_organization_id",
        "secure_link_delivery",
        ["organization_id"],
    )
    op.create_index(
        "ix_secure_link_delivery_customer_id", "secure_link_delivery", ["customer_id"]
    )
    op.create_index(
        "ix_secure_link_delivery_org_status",
        "secure_link_delivery",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_secure_link_delivery_token_hash",
        "secure_link_delivery",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_secure_link_delivery_token_hash", table_name="secure_link_delivery"
    )
    op.drop_index(
        "ix_secure_link_delivery_org_status", table_name="secure_link_delivery"
    )
    op.drop_index(
        "ix_secure_link_delivery_customer_id", table_name="secure_link_delivery"
    )
    op.drop_index(
        "ix_secure_link_delivery_organization_id", table_name="secure_link_delivery"
    )
    op.drop_table("secure_link_delivery")
    op.drop_index("ix_customer_order_org_status", table_name="customer_order")
    op.drop_index("ix_customer_order_customer_id", table_name="customer_order")
    op.drop_index("ix_customer_order_organization_id", table_name="customer_order")
    op.drop_table("customer_order")
