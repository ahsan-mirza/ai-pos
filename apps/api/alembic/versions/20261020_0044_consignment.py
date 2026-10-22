"""Consignment: supplier-owned purchase batches and the settlements that bill sold units.

Revision ID: 20261020_0044
Revises: 20261020_0043
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261020_0044"
down_revision: str | None = "20261020_0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.add_column(
        "purchase_batches", sa.Column("is_consignment", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.create_index("ix_purchase_batches_is_consignment", "purchase_batches", ["is_consignment"])
    op.create_table(
        "consignment_settlements",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("number", sa.String(length=32), nullable=False),
        sa.Column("supplier_id", sa.Uuid(as_uuid=True), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("bill_id", sa.Uuid(as_uuid=True), sa.ForeignKey("supplier_bills.id"), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        *timestamps(),
        sa.UniqueConstraint("number", name="uq_consignment_settlements_number"),
        sa.UniqueConstraint("bill_id", name="uq_consignment_settlements_bill_id"),
    )
    op.create_index("ix_consignment_settlements_supplier_id", "consignment_settlements", ["supplier_id"])
    op.create_table(
        "consignment_settlement_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "settlement_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("consignment_settlements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("batch_item_id", sa.Uuid(as_uuid=True), sa.ForeignKey("batch_items.id"), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_cost_cents", sa.Integer(), nullable=False),
        *timestamps(),
        sa.CheckConstraint("quantity >= 1", name="ck_consignment_settlement_lines_settled_quantity_positive"),
    )
    op.create_index("ix_consignment_settlement_lines_settlement_id", "consignment_settlement_lines", ["settlement_id"])
    op.create_index("ix_consignment_settlement_lines_batch_item_id", "consignment_settlement_lines", ["batch_item_id"])


def downgrade() -> None:
    op.drop_table("consignment_settlement_lines")
    op.drop_table("consignment_settlements")
    op.drop_index("ix_purchase_batches_is_consignment", table_name="purchase_batches")
    op.drop_column("purchase_batches", "is_consignment")
