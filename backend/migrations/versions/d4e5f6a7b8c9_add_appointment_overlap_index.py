"""Add appointment overlap composite index.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-03
"""
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_appointment_overlap",
        "appointment",
        ["user_id", "status", "start_datetime", "end_datetime"],
    )


def downgrade() -> None:
    op.drop_index("ix_appointment_overlap", table_name="appointment")
