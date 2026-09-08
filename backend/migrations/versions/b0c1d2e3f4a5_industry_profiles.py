"""Industry profile + waitlist tables.

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b0c1d2e3f4a5"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "industry_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False),
        sa.Column("industry_type", sa.String(32), nullable=False),
        sa.Column("scheduling_mode", sa.String(32), nullable=False, server_default="single_resource"),
        sa.Column("required_customer_fields", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("required_booking_fields", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("enabled_tools", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("confirmation_policy", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("deposit_policy", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("handoff_policy", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("privacy_policy", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("terminology", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("flow_steps", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        *_timestamps(),
        sa.UniqueConstraint("organization_id", name="uq_industry_profile_org"),
    )
    op.create_index("ix_industry_profile_organization_id", "industry_profile", ["organization_id"])

    op.create_table(
        "waitlist_entry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("location.id"), nullable=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customer.id"), nullable=True),
        sa.Column("catalog_item_id", sa.Integer(), sa.ForeignKey("catalog_item.id"), nullable=True),
        sa.Column("party_size", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("preferred_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("preferred_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="waiting"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        *_timestamps(),
    )
    op.create_index("ix_waitlist_entry_organization_id", "waitlist_entry", ["organization_id"])
    op.create_index("ix_waitlist_org_status", "waitlist_entry", ["organization_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_waitlist_org_status", table_name="waitlist_entry")
    op.drop_index("ix_waitlist_entry_organization_id", table_name="waitlist_entry")
    op.drop_table("waitlist_entry")
    op.drop_index("ix_industry_profile_organization_id", table_name="industry_profile")
    op.drop_table("industry_profile")
