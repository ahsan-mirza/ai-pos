"""Fail closed on bypass and on a missing branch for store-scoped offline tables.

Revision ID: 20261122_0131
Revises: 20261122_0130
Create Date: 2026-11-22

An application login that sets app.bypass_rls no longer widens users, products,
or sync_events. Store-scoped allocation and bootstrap rows require app.store_id.
Empty or unknown store context returns no rows. The table owner can still migrate.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261122_0131"
down_revision: str | None = "20261122_0130"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _tenant_policy(table: str) -> None:
    predicate = """
        USING (
          tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
          tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
    """
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"'))
    op.execute(sa.text(f'CREATE POLICY tenant_isolation ON "{table}" {predicate}'))


def _store_policy(table: str, *, device: bool) -> None:
    device_clause = """
            AND (
              NULLIF(current_setting('app.device_id', true), '') IS NULL
              OR device_id = NULLIF(current_setting('app.device_id', true), '')::uuid
            )
    """ if device else ""
    predicate = f"""
        USING (
          tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
          AND store_id = NULLIF(current_setting('app.store_id', true), '')::uuid
          {device_clause}
        )
        WITH CHECK (
          tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
          AND store_id = NULLIF(current_setting('app.store_id', true), '')::uuid
          {device_clause}
        )
    """
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"'))
    op.execute(sa.text(f'CREATE POLICY tenant_isolation ON "{table}" {predicate}'))


def _common() -> list[sa.Column]:
    return [
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("store_id", sa.Uuid(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="submitted"),
        sa.Column("posting_status", sa.String(32), nullable=False, server_default="awaiting_approval"),
        sa.Column("submitted_by_id", sa.Uuid(), nullable=False),
        sa.Column("decided_by_id", sa.Uuid(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    ]


def _tables() -> None:
    op.create_table(
        "lost_terminal_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        *_common(),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("allocation_id", sa.Uuid(), nullable=True),
        sa.Column("last_sequence", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
    )
    op.create_table(
        "conflict_adjustment_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        *_common(),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("original_hash", sa.String(128), nullable=False),
        sa.Column("proposed_hash", sa.String(128), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
    )


def upgrade() -> None:
    if not _postgres():
        return
    _tables()
    names = op.get_bind().execute(
        sa.text(
            """
            SELECT c.relname
            FROM pg_policy p
            JOIN pg_class c ON c.oid = p.polrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND p.polname = 'tenant_isolation'
            """
        )
    ).scalars()
    for table in names:
        _tenant_policy(table)
    for table in ("terminal_allocations", "bootstrap_sessions", "lost_terminal_requests"):
        _store_policy(table, device=True)
    _store_policy("conflict_adjustment_requests", device=False)


def downgrade() -> None:
    if not _postgres():
        return
    for table in ("lost_terminal_requests", "conflict_adjustment_requests"):
        op.execute(sa.text(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"'))
        op.drop_table(table)
