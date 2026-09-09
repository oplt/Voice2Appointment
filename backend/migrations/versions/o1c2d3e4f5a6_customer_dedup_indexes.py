"""Add partial unique indexes for customer phone/email dedup.

Revision ID: o1c2d3e4f5a6
Revises: n1c2d3e4f5a6
"""

from __future__ import annotations

from alembic import op

revision = "o1c2d3e4f5a6"
down_revision = "n1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_org_phone "
            "ON customer (organization_id, phone) WHERE phone IS NOT NULL"
        )
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_org_email "
            "ON customer (organization_id, email) WHERE email IS NOT NULL"
        )
    else:
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_org_phone "
            "ON customer (organization_id, phone) WHERE phone IS NOT NULL"
        )
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_org_email "
            "ON customer (organization_id, email) WHERE email IS NOT NULL"
        )


def downgrade() -> None:
    op.drop_index("uq_customer_org_email", table_name="customer")
    op.drop_index("uq_customer_org_phone", table_name="customer")
