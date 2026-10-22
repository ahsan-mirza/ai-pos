"""Per-tenant module overrides set by IT support, and each tenant's plan and owner email.

Revision ID: control_0006
Revises: control_0005
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0006"
down_revision: str | None = "control_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("plan", sa.String(32), nullable=False, server_default="standard"))
    op.add_column("tenants", sa.Column("owner_email", sa.String(254), nullable=True))
    op.create_table(
        "tenant_module_overrides",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("module_key", sa.String(32), nullable=False),
        sa.Column("state", sa.String(8), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("operator_id", sa.Uuid(as_uuid=True), sa.ForeignKey("operators.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "module_key", name="uq_tenant_module_overrides_tenant_module"),
    )
    op.create_index("ix_tenant_module_overrides_tenant_id", "tenant_module_overrides", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("tenant_module_overrides")
    op.drop_column("tenants", "owner_email")
    op.drop_column("tenants", "plan")
