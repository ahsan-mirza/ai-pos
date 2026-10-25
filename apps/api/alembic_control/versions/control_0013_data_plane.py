"""Shared or legacy data plane, and merge checkpoints.

Revision ID: control_0013
Revises: control_0012
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0013"
down_revision: str | None = "control_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("data_plane", sa.String(length=16), nullable=False, server_default="legacy"),
    )
    op.create_table(
        "tenant_merge_checkpoints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("table_name", sa.String(length=64), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_tenant_merge_checkpoints_tenant_id_tenants"),
        sa.PrimaryKeyConstraint("id", name="pk_tenant_merge_checkpoints"),
        sa.UniqueConstraint("tenant_id", "table_name", name="uq_tenant_merge_checkpoints_table"),
    )
    op.create_index(
        "ix_tenant_merge_checkpoints_tenant_id", "tenant_merge_checkpoints", ["tenant_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_merge_checkpoints_tenant_id", table_name="tenant_merge_checkpoints")
    op.drop_table("tenant_merge_checkpoints")
    op.drop_column("tenants", "data_plane")
