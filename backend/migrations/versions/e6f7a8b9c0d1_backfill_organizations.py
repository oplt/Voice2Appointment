"""Backfill one organization per existing user and add parallel organization IDs.

Revision ID: g9b0c1d2e3f4
Revises: f8a9b0c1d2e3
"""

from __future__ import annotations

import sqlalchemy as sa
from datetime import datetime, timezone
from alembic import op

revision = "g9b0c1d2e3f4"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("res_user") as batch:
        batch.add_column(sa.Column("organization_id", sa.Integer(), nullable=True))
        batch.create_index("ix_res_user_organization_id", ["organization_id"])
        batch.create_foreign_key("fk_res_user_organization", "organization", ["organization_id"], ["id"])
    for table in ("appointment", "callsession"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("organization_id", sa.Integer(), nullable=True))
            batch.create_index(f"ix_{table}_organization_id", ["organization_id"])
            batch.create_foreign_key(f"fk_{table}_organization", "organization", ["organization_id"], ["id"])

    bind = op.get_bind()
    users = bind.execute(sa.text("SELECT id, username FROM res_user")).mappings().all()
    now = datetime.now(timezone.utc)
    for user in users:
        user_id = int(user["id"])
        bind.execute(
            sa.text("INSERT INTO organization (id, name, slug, default_timezone, active, metadata_json, created_at, updated_at) VALUES (:id, :name, :slug, 'UTC', true, '{}', :now, :now)"),
            {"id": user_id, "name": user["username"], "slug": f"legacy-{user_id}", "now": now},
        )
        bind.execute(
            sa.text("INSERT INTO organization_member (organization_id, user_id, role, created_at, updated_at) VALUES (:id, :id, 'owner', :now, :now)"),
            {"id": user_id, "now": now},
        )
        bind.execute(sa.text("UPDATE res_user SET organization_id = :id WHERE id = :id"), {"id": user_id})
        bind.execute(sa.text("UPDATE appointment SET organization_id = :id WHERE user_id = :id"), {"id": user_id})
        bind.execute(sa.text("UPDATE callsession SET organization_id = :id WHERE user_id = :id"), {"id": user_id})


def downgrade() -> None:
    for table in ("callsession", "appointment"):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_organization", type_="foreignkey")
            batch.drop_index(f"ix_{table}_organization_id")
            batch.drop_column("organization_id")
    with op.batch_alter_table("res_user") as batch:
        batch.drop_constraint("fk_res_user_organization", type_="foreignkey")
        batch.drop_index("ix_res_user_organization_id")
        batch.drop_column("organization_id")
