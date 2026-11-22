"""Catalogue bootstrap snapshot and commit-ordered product change feed.

Revision ID: 20261122_0125
Revises: 20261122_0124
Create Date: 2026-11-22

Additive catalogue tables only. Not applied to the developer, inventory acceptance, or production databases.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261122_0125"
down_revision: str | None = "20261122_0124"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bootstrap_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("product_count", sa.Integer(), nullable=False),
        sa.Column("watermark", sa.String(length=40), nullable=False),
        sa.Column("since_seq", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_bootstrap_sessions_tenant_id", "bootstrap_sessions", ["tenant_id"])
    op.create_index("ix_bootstrap_sessions_device_id", "bootstrap_sessions", ["device_id"])
    op.create_table(
        "bootstrap_snapshot_items",
        sa.Column("session_id", sa.Uuid(), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_table(
        "catalog_feed_counters",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("retain_after", sa.Integer(), nullable=False),
        sa.UniqueConstraint("tenant_id"),
    )
    op.create_table(
        "catalog_changes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("dataset", sa.String(length=32), nullable=False),
        sa.Column("record_id", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
    )
    op.create_index("ix_catalog_changes_seq", "catalog_changes", ["seq"])


def downgrade() -> None:
    op.drop_index("ix_catalog_changes_seq", table_name="catalog_changes")
    op.drop_table("catalog_changes")
    op.drop_table("catalog_feed_counters")
    op.drop_table("bootstrap_snapshot_items")
    op.drop_index("ix_bootstrap_sessions_device_id", table_name="bootstrap_sessions")
    op.drop_index("ix_bootstrap_sessions_tenant_id", table_name="bootstrap_sessions")
    op.drop_table("bootstrap_sessions")
