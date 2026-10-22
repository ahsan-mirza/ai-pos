"""Trade-ins of used devices; store credit vouchers no longer need a return.

Revision ID: 20261020_0033
Revises: 20261020_0032
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261020_0033"
down_revision: str | None = "20261020_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("store_credits") as batch:
        batch.alter_column("return_id", existing_type=sa.Uuid(as_uuid=True), nullable=True)
    op.create_table(
        "trade_ins",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("number", sa.String(40), nullable=False, unique=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False, index=True),
        sa.Column("product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column(
            "resale_product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id"), nullable=False, index=True
        ),
        sa.Column("serial_number_id", sa.Uuid(as_uuid=True), sa.ForeignKey("serial_numbers.id"), nullable=False),
        sa.Column("identifier_kind", sa.String(16), nullable=False),
        sa.Column("identifier_hash", sa.String(64), nullable=False, index=True),
        sa.Column("grade", sa.String(1), nullable=False),
        sa.Column("checklist", sa.JSON(), nullable=False),
        sa.Column("notes", sa.String(500), nullable=False, server_default=""),
        sa.Column("seller_name", sa.String(120), nullable=False),
        sa.Column("seller_phone", sa.String(40), nullable=False),
        sa.Column("seller_id_encrypted", sa.Text(), nullable=False),
        sa.Column("seller_id_last4", sa.String(4), nullable=False),
        sa.Column("customer_id", sa.Uuid(as_uuid=True), sa.ForeignKey("customers.id"), nullable=True, index=True),
        sa.Column("offer_cents", sa.Integer(), nullable=False),
        sa.Column("resale_price_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("payout", sa.String(12), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="ACCEPTED", index=True),
        sa.Column("sale_id", sa.Uuid(as_uuid=True), sa.ForeignKey("sales.id"), nullable=True),
        sa.Column("store_credit_id", sa.Uuid(as_uuid=True), sa.ForeignKey("store_credits.id"), nullable=True),
        sa.Column("batch_item_id", sa.Uuid(as_uuid=True), sa.ForeignKey("batch_items.id"), nullable=True),
        sa.Column("cashier_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("offer_cents >= 0", name="trade_in_offer_nonnegative"),
    )


def downgrade() -> None:
    op.drop_table("trade_ins")
    with op.batch_alter_table("store_credits") as batch:
        batch.alter_column("return_id", existing_type=sa.Uuid(as_uuid=True), nullable=False)
