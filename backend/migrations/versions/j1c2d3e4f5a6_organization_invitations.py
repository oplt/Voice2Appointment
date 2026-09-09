"""Add durable organization invitations for membership onboarding.

Revision ID: j1c2d3e4f5a6
Revises: i1c2d3e4f5a6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "j1c2d3e4f5a6"
down_revision = "i1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_invitation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invited_by_user_id", sa.Integer(), sa.ForeignKey("res_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "email", name="uq_org_invitation_email"),
    )
    op.create_index("ix_organization_invitation_organization_id", "organization_invitation", ["organization_id"])
    op.create_index("ix_organization_invitation_invited_by_user_id", "organization_invitation", ["invited_by_user_id"])
    op.create_index("ix_org_invitation_token_hash", "organization_invitation", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_org_invitation_token_hash", table_name="organization_invitation")
    op.drop_index("ix_organization_invitation_invited_by_user_id", table_name="organization_invitation")
    op.drop_index("ix_organization_invitation_organization_id", table_name="organization_invitation")
    op.drop_table("organization_invitation")
