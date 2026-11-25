"""Row-level security for the offline catalogue, allocation, and staff tables.

Revision ID: 20261122_0130
Revises: 20261122_0129
Create Date: 2026-11-22

Tenant isolation matches the pharmacy predicate in 20261119_0119. A session may
also set app.store_id or app.device_id. When those settings are empty, the
tenant predicate is the only database filter and the service checks remain in
force. The application role does not bypass RLS. Not applied by this audit to
any protected database.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261122_0130"
down_revision: str | None = "20261122_0129"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT = (
    "bootstrap_snapshot_items",
    "bootstrap_setting_snapshots",
    "catalog_changes",
    "catalog_feed_counters",
    "terminal_allocation_consumptions",
)

SCOPED = {
    "bootstrap_sessions": ("store_id", "device_id"),
    "terminal_allocations": ("store_id", "device_id"),
}


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _predicate(table: str, store: str | None, device: str | None) -> str:
    extra = ""
    if store is not None:
        extra += (
            f" AND (NULLIF(current_setting('app.store_id', true), '') IS NULL"
            f" OR {store} = NULLIF(current_setting('app.store_id', true), '')::uuid)"
        )
    if device is not None:
        extra += (
            f" AND (NULLIF(current_setting('app.device_id', true), '') IS NULL"
            f" OR {device} = NULLIF(current_setting('app.device_id', true), '')::uuid)"
        )
    return f"""
        USING (
          (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid{extra})
          OR app_owner_may_bypass('{table}'::regclass)
        )
        WITH CHECK (
          (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid{extra})
          OR app_owner_may_bypass('{table}'::regclass)
        )
    """


def _apply(table: str, store: str | None = None, device: str | None = None) -> None:
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"'))
    op.execute(sa.text(f'CREATE POLICY tenant_isolation ON "{table}" {_predicate(table, store, device)}'))


def _ensure_feed_counter() -> None:
    """0125 gained this table after some databases had already stamped that revision."""
    if "catalog_feed_counters" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "catalog_feed_counters",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("retain_after", sa.Integer(), nullable=False),
        sa.UniqueConstraint("tenant_id"),
    )


def upgrade() -> None:
    _ensure_feed_counter()
    if not _postgres():
        return
    for table in TENANT:
        _apply(table)
    for table, (store, device) in SCOPED.items():
        _apply(table, store, device)
    _apply("staff_provisioning_events")


def downgrade() -> None:
    if not _postgres():
        return
    for table in (*TENANT, *SCOPED, "staff_provisioning_events"):
        op.execute(sa.text(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"'))
        op.execute(sa.text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))
