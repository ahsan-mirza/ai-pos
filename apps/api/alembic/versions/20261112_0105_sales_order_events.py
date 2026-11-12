"""External order identity and the sales-order timeline.

Revision ID: 20261112_0105
Revises: 20261111_0104
Create Date: 2026-11-12

A repeated channel reference returns the original order. The timeline is separate from payment.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261112_0105"
down_revision: str | None = "20261111_0104"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _channel_constraint(*, present: bool) -> None:
    """SQLite cannot ALTER a constraint in place. Postgres adds it directly."""
    columns = ["tenant_id", "source", "channel_ref"]
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("sales_orders") as batch:
            if present:
                batch.create_unique_constraint("uq_sales_orders_channel", columns)
            else:
                batch.drop_constraint("uq_sales_orders_channel", type_="unique")
        return
    if present:
        op.create_unique_constraint("uq_sales_orders_channel", "sales_orders", columns)
    else:
        op.drop_constraint("uq_sales_orders_channel", "sales_orders", type_="unique")


def upgrade() -> None:
    _channel_constraint(present=True)
    op.create_table(
        "sales_order_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("summary", sa.String(length=240), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["sales_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sales_order_events_tenant_id", "sales_order_events", ["tenant_id"])
    op.create_index("ix_sales_order_events_order_id", "sales_order_events", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_sales_order_events_order_id", table_name="sales_order_events")
    op.drop_index("ix_sales_order_events_tenant_id", table_name="sales_order_events")
    op.drop_table("sales_order_events")
    _channel_constraint(present=False)
