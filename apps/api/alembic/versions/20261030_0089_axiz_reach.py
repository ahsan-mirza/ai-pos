"""AxizReach channel settings, campaigns, and one-time usage rows.

Revision ID: 20261030_0089
Revises: 20261030_0088
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261030_0089"
down_revision: str | None = "20261030_0088"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "messaging_channels",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=12), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("provider", sa.String(length=24), nullable=False),
        sa.Column("public_config", sa.JSON(), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "channel", name="uq_messaging_channels_channel"),
    )
    op.create_index("ix_messaging_channels_tenant_id", "messaging_channels", ["tenant_id"])
    op.create_table(
        "reach_campaigns",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("objective", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("channels", sa.JSON(), nullable=False),
        sa.Column("audience", sa.JSON(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("eligible_count", sa.Integer(), nullable=False),
        sa.Column("suppressed_count", sa.Integer(), nullable=False),
        sa.Column("queued_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_reach_campaigns_idempotency"),
    )
    op.create_index("ix_reach_campaigns_tenant_id", "reach_campaigns", ["tenant_id"])
    op.create_index("ix_reach_campaigns_status", "reach_campaigns", ["status"])
    op.create_table(
        "reach_usage",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("outbound_message_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=True),
        sa.Column("channel", sa.String(length=12), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("cost_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["outbound_message_id"], ["outbound_messages.id"]),
        sa.ForeignKeyConstraint(["campaign_id"], ["reach_campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "outbound_message_id", name="uq_reach_usage_message"),
    )
    op.create_index("ix_reach_usage_tenant_id", "reach_usage", ["tenant_id"])
    op.create_index("ix_reach_usage_campaign_id", "reach_usage", ["campaign_id"])


def downgrade() -> None:
    op.drop_table("reach_usage")
    op.drop_table("reach_campaigns")
    op.drop_table("messaging_channels")
