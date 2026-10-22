"""Sales returns, refund tenders, store credit, and the audit log.

Revision ID: 20261019_0003
Revises: 20261019_0002
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0003"
down_revision: str | None = "20261019_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "returns",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("original_sale_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("store_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("cashier_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("approved_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("subtotal_cents", sa.Integer(), nullable=False),
        sa.Column("tax_refund_cents", sa.Integer(), nullable=False),
        sa.Column("restocking_fee_cents", sa.Integer(), nullable=False),
        sa.Column("total_refund_cents", sa.Integer(), nullable=False),
        sa.Column("refund_method", sa.String(length=32), nullable=False),
        sa.Column("reason_notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("subtotal_cents >= 0", name="ck_returns_subtotal_nonnegative"),
        sa.CheckConstraint("tax_refund_cents >= 0", name="ck_returns_tax_refund_nonnegative"),
        sa.CheckConstraint("restocking_fee_cents >= 0", name="ck_returns_restocking_fee_nonnegative"),
        sa.CheckConstraint("total_refund_cents >= 0", name="ck_returns_total_refund_nonnegative"),
        sa.ForeignKeyConstraint(["original_sale_id"], ["sales.id"], name="fk_returns_original_sale_id_sales"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_returns_store_id_stores"),
        sa.ForeignKeyConstraint(["cashier_id"], ["users.id"], name="fk_returns_cashier_id_users"),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], name="fk_returns_approved_by_id_users"),
    )
    op.create_index("ix_returns_original_sale_id", "returns", ["original_sale_id"])
    op.create_index("ix_returns_store_id", "returns", ["store_id"])
    op.create_index("ix_returns_cashier_id", "returns", ["cashier_id"])
    op.create_index("ix_returns_approved_by_id", "returns", ["approved_by_id"])
    op.create_index("ix_returns_currency", "returns", ["currency"])
    op.create_index("ix_returns_created_at", "returns", ["created_at"])

    op.create_table(
        "return_items",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("return_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("sale_item_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("serial_number_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False),
        sa.Column("tax_refund_cents", sa.Integer(), nullable=False),
        sa.Column("restocking_fee_cents", sa.Integer(), nullable=False),
        sa.Column("refund_cents", sa.Integer(), nullable=False),
        sa.Column("condition_status", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=32), nullable=False),
        sa.CheckConstraint("quantity >= 1", name="ck_return_items_quantity_positive"),
        sa.CheckConstraint("unit_price_cents >= 0", name="ck_return_items_unit_price_nonnegative"),
        sa.CheckConstraint("tax_refund_cents >= 0", name="ck_return_items_tax_refund_nonnegative"),
        sa.CheckConstraint("restocking_fee_cents >= 0", name="ck_return_items_restocking_fee_nonnegative"),
        sa.CheckConstraint("refund_cents >= 0", name="ck_return_items_refund_nonnegative"),
        sa.ForeignKeyConstraint(["return_id"], ["returns.id"], name="fk_return_items_return_id_returns"),
        sa.ForeignKeyConstraint(["sale_item_id"], ["sale_items.id"], name="fk_return_items_sale_item_id_sale_items"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_return_items_product_id_products"),
        sa.ForeignKeyConstraint(
            ["serial_number_id"],
            ["serial_numbers.id"],
            name="fk_return_items_serial_number_id_serial_numbers",
        ),
    )
    op.create_index("ix_return_items_return_id", "return_items", ["return_id"])
    op.create_index("ix_return_items_sale_item_id", "return_items", ["sale_item_id"])
    op.create_index("ix_return_items_product_id", "return_items", ["product_id"])
    op.create_index("ix_return_items_condition_status", "return_items", ["condition_status"])

    op.create_table(
        "store_credits",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("store_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("return_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("initial_cents", sa.Integer(), nullable=False),
        sa.Column("balance_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("initial_cents >= 1", name="ck_store_credits_initial_positive"),
        sa.CheckConstraint("balance_cents >= 0", name="ck_store_credits_balance_nonnegative"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_store_credits_store_id_stores"),
        sa.ForeignKeyConstraint(["return_id"], ["returns.id"], name="fk_store_credits_return_id_returns"),
        sa.UniqueConstraint("code", name="uq_store_credits_code"),
    )
    op.create_index("ix_store_credits_store_id", "store_credits", ["store_id"])
    op.create_index("ix_store_credits_return_id", "store_credits", ["return_id"])

    op.create_table(
        "return_tenders",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("return_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("store_credit_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.CheckConstraint("amount_cents >= 1", name="ck_return_tenders_amount_positive"),
        sa.ForeignKeyConstraint(["return_id"], ["returns.id"], name="fk_return_tenders_return_id_returns"),
        sa.ForeignKeyConstraint(
            ["store_credit_id"],
            ["store_credits.id"],
            name="fk_return_tenders_store_credit_id_store_credits",
        ),
    )
    op.create_index("ix_return_tenders_return_id", "return_tenders", ["return_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("actor_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("approver_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_audit_logs_store_id_stores"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name="fk_audit_logs_actor_id_users"),
        sa.ForeignKeyConstraint(["approver_id"], ["users.id"], name="fk_audit_logs_approver_id_users"),
    )
    op.create_index("ix_audit_logs_store_id", "audit_logs", ["store_id"])
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_approver_id", "audit_logs", ["approver_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("return_tenders")
    op.drop_table("store_credits")
    op.drop_table("return_items")
    op.drop_table("returns")
