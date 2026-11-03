"""Campaign media files and event suggestions. Does not change earlier Reach revisions.

Revision ID: 20261103_0097
Revises: 20261103_0096
Create Date: 2026-11-03

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261103_0097"
down_revision: str | None = "20261103_0096"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLICY = (
    "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on') "
    "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on')"
)


def _rls(table: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'CREATE POLICY tenant_isolation ON "{table}" {POLICY}'))


def upgrade() -> None:
    op.add_column("reach_campaigns", sa.Column("origin", sa.String(length=16), nullable=False, server_default="manual"))
    op.add_column(
        "reach_campaigns",
        sa.Column("approval_state", sa.String(length=24), nullable=False, server_default="not_required"),
    )
    op.add_column("reach_campaigns", sa.Column("content_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("reach_campaigns", sa.Column("approved_version", sa.Integer(), nullable=True))
    op.add_column("reach_campaigns", sa.Column("approved_by_id", sa.Uuid(), nullable=True))
    op.add_column("reach_campaigns", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "reach_media_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(length=160), nullable=False),
        sa.Column("mime_type", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "storage_key", name="uq_reach_media_storage_key"),
    )
    op.create_index("ix_reach_media_assets_tenant_id", "reach_media_assets", ["tenant_id"])
    op.create_table(
        "reach_campaign_suggestions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("event_key", sa.String(length=80), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("audience", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["reach_campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "event_key", name="uq_reach_suggestions_event"),
    )
    op.create_index("ix_reach_campaign_suggestions_tenant_id", "reach_campaign_suggestions", ["tenant_id"])
    for table in ("reach_media_assets", "reach_campaign_suggestions"):
        _rls(table)


def downgrade() -> None:
    op.drop_index("ix_reach_campaign_suggestions_tenant_id", table_name="reach_campaign_suggestions")
    op.drop_table("reach_campaign_suggestions")
    op.drop_index("ix_reach_media_assets_tenant_id", table_name="reach_media_assets")
    op.drop_table("reach_media_assets")
    op.drop_column("reach_campaigns", "approved_at")
    op.drop_column("reach_campaigns", "approved_by_id")
    op.drop_column("reach_campaigns", "approved_version")
    op.drop_column("reach_campaigns", "content_version")
    op.drop_column("reach_campaigns", "approval_state")
    op.drop_column("reach_campaigns", "origin")
