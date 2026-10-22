"""Per-tenant size and activity snapshot for the console directory.

Revision ID: control_0007
Revises: control_0006
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0007"
down_revision: str | None = "control_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_stats",
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("onboarded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("business_profile", sa.String(32), nullable=True),
        sa.Column("enabled_modules", sa.JSON(), nullable=False),
        sa.Column("stores", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("registers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("users", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("customers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("products", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sales_30d_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sales_30d_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("last_sale_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("db_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("tenant_stats")
