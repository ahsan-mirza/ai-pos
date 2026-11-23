"""Cashier-facing takeaway and delivery order tags.

Revision ID: 20261123_0136
Revises: 20261122_0135
Create Date: 2026-11-23

Additive. A tag is issued once per order id and is unique inside the store.
Not applied to a protected database.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261123_0136"
down_revision: str | None = "20261122_0135"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "order_tags",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("service_type", sa.String(length=10), nullable=False),
        sa.Column("tag", sa.String(length=24), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "store_id", "tag", name="uq_order_tags_store_tag"),
    )
    op.create_index("ix_order_tags_tenant_id", "order_tags", ["tenant_id"])
    op.create_index("ix_order_tags_store_id", "order_tags", ["store_id"])
    op.create_table(
        "order_tag_counters",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("service_type", sa.String(length=10), nullable=False),
        sa.Column("last_value", sa.Integer(), nullable=False),
        sa.UniqueConstraint("tenant_id", "store_id", "service_type", name="uq_order_tag_counters_scope"),
    )
    op.create_index("ix_order_tag_counters_tenant_id", "order_tag_counters", ["tenant_id"])
    op.create_index("ix_order_tag_counters_store_id", "order_tag_counters", ["store_id"])
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in ("order_tags", "order_tag_counters"):
        op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
        op.execute(
            sa.text(
                f"""
                CREATE POLICY tenant_isolation ON "{table}"
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
    op.drop_index("ix_order_tag_counters_store_id", table_name="order_tag_counters")
    op.drop_index("ix_order_tag_counters_tenant_id", table_name="order_tag_counters")
    op.drop_table("order_tag_counters")
    op.drop_index("ix_order_tags_store_id", table_name="order_tags")
    op.drop_index("ix_order_tags_tenant_id", table_name="order_tags")
    op.drop_table("order_tags")
