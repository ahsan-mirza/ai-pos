"""Console tenant data reset and restore records.

Revision ID: control_0037
Revises: control_0036
Create Date: 2026-11-15

Stores operation metadata only. Snapshot payloads stay in the private
data_reset_dir, encrypted, and are not columns in this database.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0037"
down_revision: str | None = "control_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_data_operations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("operator_id", sa.Uuid(as_uuid=True), sa.ForeignKey("operators.id"), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("store_ids", sa.JSON(), nullable=False),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.Column("preview", sa.JSON(), nullable=False),
        sa.Column("authorized_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("restore_authorized_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot_relpath", sa.String(length=240), nullable=True),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=True),
        sa.Column("snapshot_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_reset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_restored", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conflicts", sa.JSON(), nullable=True),
        sa.Column("failure", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("restore_operator_id", sa.Uuid(as_uuid=True), sa.ForeignKey("operators.id"), nullable=True),
        sa.CheckConstraint(
            "status IN ('PREVIEWED', 'AUTHORIZED', 'SNAPSHOTTING', 'SNAPSHOT_VERIFIED', 'RESETTING', "
            "'COMPLETED', 'FAILED', 'RESTORE_REQUESTED', 'RESTORING', 'RESTORED', 'RESTORE_FAILED')",
            name="ck_tenant_data_operations_status_known",
        ),
        sa.CheckConstraint("scope IN ('store', 'tenant')", name="ck_tenant_data_operations_scope_known"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_tenant_data_operations_idempotency"),
    )
    op.create_index("ix_tenant_data_operations_tenant_id", "tenant_data_operations", ["tenant_id"])
    op.create_index("ix_tenant_data_operations_operator_id", "tenant_data_operations", ["operator_id"])
    op.create_index("ix_tenant_data_operations_status", "tenant_data_operations", ["status"])
    op.create_table(
        "console_reset_guards",
        sa.Column("operator_id", sa.Uuid(as_uuid=True), sa.ForeignKey("operators.id"), primary_key=True),
        sa.Column("failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("window_started", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("console_reset_guards")
    op.drop_index("ix_tenant_data_operations_status", table_name="tenant_data_operations")
    op.drop_index("ix_tenant_data_operations_operator_id", table_name="tenant_data_operations")
    op.drop_index("ix_tenant_data_operations_tenant_id", table_name="tenant_data_operations")
    op.drop_table("tenant_data_operations")
