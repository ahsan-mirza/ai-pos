"""Demo-tenant flags on the control-plane tenant row.

Revision ID: control_0038
Revises: control_0037
Create Date: 2026-11-18

Existing tenants stay commercial: is_demo and demo_access_enabled default to false.
Downgrade drops only these columns. It does not delete tenant rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0038"
down_revision: str | None = "control_0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("tenants", sa.Column("demo_business_type", sa.String(length=32), nullable=True))
    op.add_column("tenants", sa.Column("demo_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tenants", sa.Column("demo_status", sa.String(length=16), nullable=True))
    op.add_column("tenants", sa.Column("demo_seed_version", sa.Integer(), nullable=True))
    op.add_column("tenants", sa.Column("demo_last_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "tenants",
        sa.Column("demo_access_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("tenants", sa.Column("demo_created_by", sa.Uuid(as_uuid=True), nullable=True))
    op.create_index("ix_tenants_is_demo_demo_status", "tenants", ["is_demo", "demo_status"])
    op.create_index("ix_tenants_demo_expires_at", "tenants", ["demo_expires_at"])
    # SQLite cannot ALTER in a check or a foreign key. create_all still builds both for tests.
    if _postgres():
        op.create_check_constraint(
            "ck_tenants_demo_status_known",
            "tenants",
            "demo_status IS NULL OR demo_status IN ('active', 'disabled', 'resetting')",
        )
        op.create_check_constraint(
            "ck_tenants_demo_business_type_known",
            "tenants",
            "demo_business_type IS NULL OR demo_business_type IN "
            "('restaurant', 'supermarket', 'electronics', 'fashion')",
        )
        op.create_foreign_key(
            "fk_tenants_demo_created_by_operators",
            "tenants",
            "operators",
            ["demo_created_by"],
            ["id"],
        )


def downgrade() -> None:
    if _postgres():
        op.drop_constraint("fk_tenants_demo_created_by_operators", "tenants", type_="fk")
        op.drop_constraint("ck_tenants_demo_business_type_known", "tenants", type_="check")
        op.drop_constraint("ck_tenants_demo_status_known", "tenants", type_="check")
    op.drop_index("ix_tenants_demo_expires_at", table_name="tenants")
    op.drop_index("ix_tenants_is_demo_demo_status", table_name="tenants")
    op.drop_column("tenants", "demo_created_by")
    op.drop_column("tenants", "demo_access_enabled")
    op.drop_column("tenants", "demo_last_reset_at")
    op.drop_column("tenants", "demo_seed_version")
    op.drop_column("tenants", "demo_status")
    op.drop_column("tenants", "demo_expires_at")
    op.drop_column("tenants", "demo_business_type")
    op.drop_column("tenants", "is_demo")
