"""Tenant change requests: business-type migrations and modules outside a tenant's type, handled by IT support.

Revision ID: control_0004
Revises: control_0003
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0004"
down_revision: str | None = "control_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_change_requests",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("requested_value", sa.String(40), nullable=False),
        sa.Column("current_value", sa.String(40), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("requested_by_email", sa.String(254), nullable=True),
        sa.Column("requested_by_name", sa.String(120), nullable=True),
        sa.Column("resolved_by_operator_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tenant_change_requests_tenant_id", "tenant_change_requests", ["tenant_id"])
    op.create_index("ix_tenant_change_requests_status", "tenant_change_requests", ["status"])


def downgrade() -> None:
    op.drop_table("tenant_change_requests")
