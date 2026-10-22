"""Accounts payable (supplier bills, payments, allocations) and the back-office permissions.

Revision ID: 20261020_0031
Revises: 20261019_0030
Create Date: 2026-10-20
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261020_0031"
down_revision: str | None = "20261019_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUPER_ADMIN_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
STORE_MANAGER_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a2")
NEW_PERMISSIONS = ("payables:manage", "expenses:manage", "pos:trade_in", "promotions:manage")


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _grant(bind: sa.engine.Connection) -> None:
    roles = sa.table("roles", sa.column("id", sa.Uuid(as_uuid=True)))
    role_permissions = sa.table(
        "role_permissions", sa.column("role_id", sa.Uuid(as_uuid=True)), sa.column("permission", sa.String(64))
    )
    for role_id in (SUPER_ADMIN_ROLE_ID, STORE_MANAGER_ROLE_ID):
        if bind.execute(sa.select(roles.c.id).where(roles.c.id == role_id)).first() is None:
            continue
        held = {
            row[0]
            for row in bind.execute(
                sa.select(role_permissions.c.permission).where(role_permissions.c.role_id == role_id)
            )
        }
        missing = [{"role_id": role_id, "permission": item} for item in NEW_PERMISSIONS if item not in held]
        if missing:
            op.bulk_insert(role_permissions, missing)


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("payment_terms_days", sa.Integer(), nullable=False, server_default="30"))
    op.add_column("suppliers", sa.Column("trn", sa.String(15), nullable=True))
    op.create_table(
        "supplier_bills",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("supplier_id", sa.Uuid(as_uuid=True), sa.ForeignKey("suppliers.id"), nullable=False, index=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False, index=True),
        sa.Column("number", sa.String(40), nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(as_uuid=True), sa.ForeignKey("purchase_orders.id"), nullable=True),
        sa.Column(
            "goods_receipt_id", sa.Uuid(as_uuid=True), sa.ForeignKey("goods_receipts.id"), nullable=True, unique=True
        ),
        sa.Column("bill_date", sa.Date(), nullable=False, index=True),
        sa.Column("due_date", sa.Date(), nullable=False, index=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("subtotal_cents", sa.Integer(), nullable=False),
        sa.Column("tax_cents", sa.Integer(), nullable=False),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("paid_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(8), nullable=False, server_default="OPEN", index=True),
        sa.Column("note", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("supplier_id", "number", name="uq_supplier_bills_supplier_number"),
        sa.CheckConstraint("total_cents >= 0", name="bill_total_nonnegative"),
        sa.CheckConstraint("paid_cents >= 0 AND paid_cents <= total_cents", name="bill_paid_within_total"),
    )
    op.create_table(
        "supplier_bill_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "bill_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("supplier_bills.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id"), nullable=True),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_cost_cents", sa.Integer(), nullable=False),
        sa.Column("tax_category", sa.String(8), nullable=False, server_default="STANDARD"),
        sa.Column("tax_cents", sa.Integer(), nullable=False),
        sa.Column("line_total_cents", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity >= 1", name="bill_line_quantity_positive"),
    )
    op.create_table(
        "supplier_payments",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("supplier_id", sa.Uuid(as_uuid=True), sa.ForeignKey("suppliers.id"), nullable=False, index=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("reference", sa.String(64), nullable=False, server_default=""),
        sa.Column("paid_on", sa.Date(), nullable=False, index=True),
        sa.Column("cheque_number", sa.String(32), nullable=True),
        sa.Column("cheque_bank", sa.String(80), nullable=True),
        sa.Column("cheque_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(8), nullable=False, server_default="POSTED", index=True),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("amount_cents > 0", name="supplier_payment_positive"),
    )
    op.create_table(
        "supplier_payment_allocations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "payment_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("supplier_payments.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("bill_id", sa.Uuid(as_uuid=True), sa.ForeignKey("supplier_bills.id"), nullable=False, index=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.CheckConstraint("amount_cents > 0", name="allocation_positive"),
    )
    _grant(op.get_bind())


def downgrade() -> None:
    op.drop_table("supplier_payment_allocations")
    op.drop_table("supplier_payments")
    op.drop_table("supplier_bill_lines")
    op.drop_table("supplier_bills")
    op.drop_column("suppliers", "trn")
    op.drop_column("suppliers", "payment_terms_days")
    quoted = ", ".join(f"'{item}'" for item in NEW_PERMISSIONS)
    op.execute(f"DELETE FROM role_permissions WHERE permission IN ({quoted})")
