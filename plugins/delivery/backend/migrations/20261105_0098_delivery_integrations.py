"""Delivery Integrations connections. Does not replace delivery_channels.

Revision ID: 20261105_0098
Revises: 20261103_0097
Create Date: 2026-11-05

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261105_0098"
down_revision: str | None = "20261103_0097"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLICY = (
    "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on') "
    "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on')"
)

GRANTS = {
    "Super Admin": ("delivery:view", "delivery:manage"),
    "Store Manager": ("delivery:view", "delivery:manage"),
}


def _rls(table: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'CREATE POLICY tenant_isolation ON "{table}" {POLICY}'))


def _grant() -> None:
    bind = op.get_bind()
    roles = sa.table(
        "roles",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("is_system", sa.Boolean()),
        sa.column("tenant_id", sa.Uuid()),
    )
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Uuid()),
        sa.column("permission", sa.String()),
        sa.column("tenant_id", sa.Uuid()),
    )
    for name, permissions in GRANTS.items():
        found = bind.execute(
            sa.select(roles.c.id, roles.c.tenant_id).where(roles.c.name == name, roles.c.is_system.is_(True))
        ).all()
        for role_id, tenant_id in found:
            held = {
                row[0]
                for row in bind.execute(
                    sa.select(role_permissions.c.permission).where(role_permissions.c.role_id == role_id)
                )
            }
            missing = [
                {"role_id": role_id, "permission": item, "tenant_id": tenant_id}
                for item in permissions
                if item not in held
            ]
            if missing:
                op.bulk_insert(role_permissions, missing)


def upgrade() -> None:
    op.create_table(
        "delivery_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("provider_code", sa.String(length=32), nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False, server_default=""),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("channel_id", sa.Uuid(), nullable=True),
        sa.Column("credential_encrypted", sa.String(length=500), nullable=True),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["delivery_channels.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "provider_code", "store_id", name="uq_delivery_connections_provider_store"),
    )
    op.create_index("ix_delivery_connections_tenant_id", "delivery_connections", ["tenant_id"])
    _rls("delivery_connections")
    _grant()


def downgrade() -> None:
    op.drop_index("ix_delivery_connections_tenant_id", table_name="delivery_connections")
    op.drop_table("delivery_connections")
