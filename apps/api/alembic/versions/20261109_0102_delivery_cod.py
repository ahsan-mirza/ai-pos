"""Delivery payment arrangement and rider cash handover.

Revision ID: 20261109_0102
Revises: 20261109_0101
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261109_0102"
down_revision: str | None = "20261109_0101"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("open_orders", sa.Column("payment_arrangement", sa.String(length=16), nullable=True))
    op.add_column("open_orders", sa.Column("delivery_status", sa.String(length=24), nullable=True))
    op.add_column("open_orders", sa.Column("rider_id", sa.Uuid(), nullable=True))
    op.add_column("open_orders", sa.Column("delivery_phone", sa.String(length=40), nullable=True))
    op.add_column("open_orders", sa.Column("delivery_address", sa.String(length=255), nullable=True))
    op.add_column("open_orders", sa.Column("cod_expected_cents", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("open_orders", sa.Column("cod_collected_cents", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("open_orders", sa.Column("cod_handed_cents", sa.Integer(), nullable=False, server_default="0"))
    op.create_foreign_key("fk_open_orders_rider_id_users", "open_orders", "users", ["rider_id"], ["id"])
    op.create_table(
        "cod_handovers",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("sale_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("rider_id", sa.Uuid(), nullable=True),
        sa.Column("cashier_id", sa.Uuid(), nullable=False),
        sa.Column("shift_id", sa.Uuid(), nullable=False),
        sa.Column("expected_cents", sa.Integer(), nullable=False),
        sa.Column("collected_cents", sa.Integer(), nullable=False),
        sa.Column("received_cents", sa.Integer(), nullable=False),
        sa.Column("outstanding_after_cents", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("received_cents >= 1", name="ck_cod_handovers_cod_received_positive"),
        sa.ForeignKeyConstraint(["cashier_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["open_orders.id"]),
        sa.ForeignKeyConstraint(["rider_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"]),
        sa.ForeignKeyConstraint(["shift_id"], ["register_shifts.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_cod_handovers"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_cod_handovers_key"),
    )
    op.create_index("ix_cod_handovers_tenant_id", "cod_handovers", ["tenant_id"])
    op.create_index("ix_cod_handovers_order_id", "cod_handovers", ["order_id"])
    op.create_index("ix_cod_handovers_sale_id", "cod_handovers", ["sale_id"])
    op.create_index("ix_cod_handovers_store_id", "cod_handovers", ["store_id"])
    op.create_index("ix_cod_handovers_shift_id", "cod_handovers", ["shift_id"])


def downgrade() -> None:
    op.drop_index("ix_cod_handovers_shift_id", table_name="cod_handovers")
    op.drop_index("ix_cod_handovers_store_id", table_name="cod_handovers")
    op.drop_index("ix_cod_handovers_sale_id", table_name="cod_handovers")
    op.drop_index("ix_cod_handovers_order_id", table_name="cod_handovers")
    op.drop_index("ix_cod_handovers_tenant_id", table_name="cod_handovers")
    op.drop_table("cod_handovers")
    op.drop_constraint("fk_open_orders_rider_id_users", "open_orders", type_="foreignkey")
    op.drop_column("open_orders", "cod_handed_cents")
    op.drop_column("open_orders", "cod_collected_cents")
    op.drop_column("open_orders", "cod_expected_cents")
    op.drop_column("open_orders", "delivery_address")
    op.drop_column("open_orders", "delivery_phone")
    op.drop_column("open_orders", "rider_id")
    op.drop_column("open_orders", "delivery_status")
    op.drop_column("open_orders", "payment_arrangement")
