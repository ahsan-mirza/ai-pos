"""Menu and floor bootstrap rows, and durable same-table conflict review.

Revision ID: 20261122_0132
Revises: 20261122_0131
Create Date: 2026-11-22

Additive. Not applied to a protected database.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261122_0132"
down_revision: str | None = "20261122_0131"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bootstrap_dataset_items",
        sa.Column("session_id", sa.Uuid(), primary_key=True),
        sa.Column("dataset", sa.String(length=16), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("record_id", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_table(
        "table_session_conflicts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("table_id", sa.Uuid(), sa.ForeignKey("dining_tables.id"), nullable=True),
        sa.Column("primary_order_id", sa.Uuid(), sa.ForeignKey("open_orders.id"), nullable=False),
        sa.Column("conflicting_order_id", sa.Uuid(), sa.ForeignKey("open_orders.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("origin_device_id", sa.String(length=64), nullable=False),
        sa.Column("origin_actor_id", sa.Uuid(), nullable=False),
        sa.Column("primary_revision", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=True),
        sa.Column("decided_by_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_table_session_conflicts_key"),
    )
    op.create_index("ix_table_session_conflicts_tenant_id", "table_session_conflicts", ["tenant_id"])
    op.create_index("ix_table_session_conflicts_store_id", "table_session_conflicts", ["store_id"])
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text('ALTER TABLE "bootstrap_dataset_items" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text('ALTER TABLE "bootstrap_dataset_items" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            """
            CREATE POLICY tenant_isolation ON "bootstrap_dataset_items"
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            """
        )
    )
    op.execute(sa.text('ALTER TABLE "table_session_conflicts" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text('ALTER TABLE "table_session_conflicts" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            """
            CREATE POLICY tenant_isolation ON "table_session_conflicts"
            USING (
              tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
              AND store_id = NULLIF(current_setting('app.store_id', true), '')::uuid
            )
            WITH CHECK (
              tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
              AND store_id = NULLIF(current_setting('app.store_id', true), '')::uuid
            )
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_table_session_conflicts_store_id", table_name="table_session_conflicts")
    op.drop_index("ix_table_session_conflicts_tenant_id", table_name="table_session_conflicts")
    op.drop_table("table_session_conflicts")
    op.drop_table("bootstrap_dataset_items")
