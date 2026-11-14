"""Independent campaign runs. Existing recipient rows stay attached to their campaign.

Revision ID: 20261114_0111
Revises: 20261113_0110
Create Date: 2026-11-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261114_0111"
down_revision: str | None = "20261113_0110"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "reach_campaigns" not in tables or "reach_recipients" not in tables:
        return
    if "reach_campaign_runs" not in tables:
        op.create_table(
            "reach_campaign_runs",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
            sa.Column("campaign_id", sa.Uuid(), nullable=False),
            sa.Column("run_number", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("channel", sa.String(length=40), nullable=False),
            sa.Column("audience_type", sa.String(length=24), nullable=False),
            sa.Column("audience_snapshot", sa.JSON(), nullable=False),
            sa.Column("total_recipients", sa.Integer(), nullable=False),
            sa.Column("eligible_recipients", sa.Integer(), nullable=False),
            sa.Column("excluded_recipients", sa.Integer(), nullable=False),
            sa.Column("queued_count", sa.Integer(), nullable=False),
            sa.Column("processing_count", sa.Integer(), nullable=False),
            sa.Column("sent_count", sa.Integer(), nullable=False),
            sa.Column("delivered_count", sa.Integer(), nullable=False),
            sa.Column("read_count", sa.Integer(), nullable=False),
            sa.Column("failed_count", sa.Integer(), nullable=False),
            sa.Column("skipped_count", sa.Integer(), nullable=False),
            sa.Column("cancelled_count", sa.Integer(), nullable=False),
            sa.Column("initiated_by_id", sa.Uuid(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("retry_of_run_id", sa.Uuid(), nullable=True),
            sa.Column("report_built_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("delivery_updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["campaign_id"], ["reach_campaigns.id"]),
            sa.ForeignKeyConstraint(["initiated_by_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["retry_of_run_id"], ["reach_campaign_runs.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "campaign_id", "run_number", name="uq_reach_campaign_runs_number"),
        )
        op.create_index("ix_reach_campaign_runs_campaign_id", "reach_campaign_runs", ["campaign_id"])
        op.create_index("ix_reach_campaign_runs_status", "reach_campaign_runs", ["status"])
        op.create_index("ix_reach_campaign_runs_tenant_id", "reach_campaign_runs", ["tenant_id"])
    columns = {column["name"] for column in inspector.get_columns("reach_recipients")}
    if "campaign_run_id" not in columns:
        op.add_column("reach_recipients", sa.Column("campaign_run_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            "fk_reach_recipients_campaign_run_id",
            "reach_recipients",
            "reach_campaign_runs",
            ["campaign_run_id"],
            ["id"],
        )
        op.create_index("ix_reach_recipients_campaign_run_id", "reach_recipients", ["campaign_run_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "reach_recipients" in tables:
        columns = {column["name"] for column in inspector.get_columns("reach_recipients")}
        if "campaign_run_id" in columns:
            op.drop_index("ix_reach_recipients_campaign_run_id", table_name="reach_recipients")
            op.drop_constraint("fk_reach_recipients_campaign_run_id", "reach_recipients", type_="foreignkey")
            op.drop_column("reach_recipients", "campaign_run_id")
    if "reach_campaign_runs" in tables:
        op.drop_index("ix_reach_campaign_runs_tenant_id", table_name="reach_campaign_runs")
        op.drop_index("ix_reach_campaign_runs_status", table_name="reach_campaign_runs")
        op.drop_index("ix_reach_campaign_runs_campaign_id", table_name="reach_campaign_runs")
        op.drop_table("reach_campaign_runs")
