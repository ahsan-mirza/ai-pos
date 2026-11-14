"""Independent campaign runs. Existing recipient rows stay attached to their campaign.

Revision ID: 20261114_0112
Revises: 20261114_0111
Create Date: 2026-11-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261114_0112"
down_revision: str | None = "20261114_0111"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "reach_campaign_runs" not in tables:
        return
    columns = {column["name"] for column in inspector.get_columns("reach_campaign_runs")}
    additions = {
        "prepare_after_id": sa.Column("prepare_after_id", sa.Uuid(), nullable=True),
        "content_snapshot": sa.Column("content_snapshot", sa.JSON(), nullable=True),
        "total_candidates": sa.Column("total_candidates", sa.Integer(), nullable=False, server_default="0"),
        "invalid_contact_count": sa.Column("invalid_contact_count", sa.Integer(), nullable=False, server_default="0"),
        "no_consent_count": sa.Column("no_consent_count", sa.Integer(), nullable=False, server_default="0"),
        "duplicate_count": sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        "report_version": sa.Column("report_version", sa.Integer(), nullable=False, server_default="0"),
        "report_dirty": sa.Column("report_dirty", sa.Boolean(), nullable=False, server_default=sa.false()),
    }
    for name, column in additions.items():
        if name not in columns:
            op.add_column("reach_campaign_runs", column)
    if "reach_recipients" in tables:
        recipient_columns = {column["name"] for column in inspector.get_columns("reach_recipients")}
        if "processing_started_at" not in recipient_columns:
            op.add_column("reach_recipients", sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True))
        if "lease_until" not in recipient_columns:
            op.add_column("reach_recipients", sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True))
    if "reach_report_artifacts" not in tables:
        op.create_table(
            "reach_report_artifacts",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
            sa.Column("run_id", sa.Uuid(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("kind", sa.String(length=8), nullable=False),
            sa.Column("storage_key", sa.String(length=240), nullable=False),
            sa.Column("file_name", sa.String(length=120), nullable=False),
            sa.Column("content_type", sa.String(length=80), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("checksum", sa.String(length=64), nullable=False),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["run_id"], ["reach_campaign_runs.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "run_id", "version", "kind", name="uq_reach_report_artifact"),
        )
        op.create_index("ix_reach_report_artifacts_run_id", "reach_report_artifacts", ["run_id"])
        op.create_index("ix_reach_report_artifacts_tenant_id", "reach_report_artifacts", ["tenant_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "reach_report_artifacts" in tables:
        op.drop_index("ix_reach_report_artifacts_tenant_id", table_name="reach_report_artifacts")
        op.drop_index("ix_reach_report_artifacts_run_id", table_name="reach_report_artifacts")
        op.drop_table("reach_report_artifacts")
    if "reach_recipients" in tables:
        columns = {column["name"] for column in inspector.get_columns("reach_recipients")}
        if "lease_until" in columns:
            op.drop_column("reach_recipients", "lease_until")
        if "processing_started_at" in columns:
            op.drop_column("reach_recipients", "processing_started_at")
    if "reach_campaign_runs" in tables:
        columns = {column["name"] for column in inspector.get_columns("reach_campaign_runs")}
        for name in (
            "report_dirty",
            "report_version",
            "duplicate_count",
            "no_consent_count",
            "invalid_contact_count",
            "total_candidates",
            "content_snapshot",
            "prepare_after_id",
        ):
            if name in columns:
                op.drop_column("reach_campaign_runs", name)
