"""Pro AI promotional trial, separate from the subscription trial.

Revision ID: control_0025
Revises: control_0024
Create Date: 2026-11-09

One row per tenant. Starting it does not change subscriptions or invoices.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0025"
down_revision: str | None = "control_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "billing_policy",
        sa.Column("pro_ai_trial_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "promotional_trials",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("trial_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("base_plan_code", sa.String(32), nullable=False),
        sa.Column("promotional_plan_code", sa.String(32), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("granted_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("expiration_reason", sa.String(80), nullable=True),
        sa.Column("notices_sent", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "trial_type", name="uq_promotional_trials_tenant_type"),
    )
    op.create_index("ix_promotional_trials_tenant_id", "promotional_trials", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_promotional_trials_tenant_id", table_name="promotional_trials")
    op.drop_table("promotional_trials")
    op.drop_column("billing_policy", "pro_ai_trial_enabled")
