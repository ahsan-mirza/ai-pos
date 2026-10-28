"""Store-level add-on access for individual users.

Revision ID: 20261028_0080
Revises: 20261028_0079
Create Date: 2026-10-28

The store subscription stays on business settings. This table only records which
users may use a paid module, and which of that module's actions they may perform.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261028_0080"
down_revision: str | None = "20261028_0079"
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
    op.create_table(
        "user_addon_access",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("module_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="granted"),
        sa.Column("permissions", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("store_id", sa.Uuid(), sa.ForeignKey("stores.id"), nullable=True),
        sa.Column("granted_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("revoked_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_user_addon_access"),
        sa.UniqueConstraint("tenant_id", "user_id", "module_key", name="uq_user_addon_access_user_module"),
    )
    op.create_index("ix_user_addon_access_tenant_id", "user_addon_access", ["tenant_id"])
    op.create_index("ix_user_addon_access_user_id", "user_addon_access", ["user_id"])
    op.create_index("ix_user_addon_access_module", "user_addon_access", ["tenant_id", "module_key"])
    _rls("user_addon_access")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text('DROP POLICY IF EXISTS tenant_isolation ON "user_addon_access"'))
    op.drop_index("ix_user_addon_access_module", table_name="user_addon_access")
    op.drop_index("ix_user_addon_access_user_id", table_name="user_addon_access")
    op.drop_index("ix_user_addon_access_tenant_id", table_name="user_addon_access")
    op.drop_table("user_addon_access")
