"""Wholesale + retail: customers and their ledger, tiered product prices, pack units, split tenders,
on-account balances, and proforma quotes.

Revision ID: 20261019_0008
Revises: 20261019_0007
Create Date: 2026-10-19
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0008"
down_revision: str | None = "20261019_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUPER_ADMIN_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
STORE_MANAGER_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a2")
CASHIER_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a3")
NEW_PERMISSIONS = ("pos:price_override", "pos:credit_sale", "customers:manage", "portal:pricing_manage")
GRANTS = {
    SUPER_ADMIN_ROLE_ID: NEW_PERMISSIONS,
    STORE_MANAGER_ROLE_ID: NEW_PERMISSIONS,
    CASHIER_ROLE_ID: ("pos:credit_sale",),
}


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("customer_type", sa.String(length=16), nullable=False),
        sa.Column("company_name", sa.String(length=160), nullable=True),
        sa.Column("trn_vat_number", sa.String(length=32), nullable=True),
        sa.Column("price_tier", sa.String(length=16), nullable=False),
        sa.Column("credit_limit_cents", sa.Integer(), nullable=False),
        sa.Column("current_balance_cents", sa.Integer(), nullable=False),
        sa.Column("payment_terms", sa.String(length=16), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.UniqueConstraint("code", name="uq_customers_code"),
        sa.CheckConstraint("credit_limit_cents >= 0", name="ck_customers_credit_limit_nonnegative"),
    )
    for column in ("name", "phone", "customer_type"):
        op.create_index(f"ix_customers_{column}", "customers", [column])

    op.create_table(
        "product_prices",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("price_tier", sa.String(length=16), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("min_order_quantity", sa.Integer(), nullable=False),
        sa.Column("volume_discounts", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name="fk_product_prices_product_id_products", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("product_id", "price_tier", name="uq_product_prices_product_tier"),
        sa.CheckConstraint("price_cents >= 0", name="ck_product_prices_price_nonnegative"),
        sa.CheckConstraint("min_order_quantity >= 1", name="ck_product_prices_moq_positive"),
    )
    op.create_index("ix_product_prices_product_id", "product_prices", ["product_id"])

    op.add_column("products", sa.Column("min_order_quantity", sa.Integer(), nullable=False, server_default="1"))
    op.add_column(
        "products", sa.Column("sellable_units", sa.JSON(), nullable=False, server_default=sa.text("'[\"PIECE\"]'"))
    )
    op.create_check_constraint("ck_products_moq_positive", "products", "min_order_quantity >= 1")

    op.add_column("sales", sa.Column("sale_type", sa.String(length=16), nullable=False, server_default="RETAIL"))
    op.add_column("sales", sa.Column("customer_id", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column("sales", sa.Column("is_quote_proforma", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("sales", sa.Column("quote_expiry_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sales", sa.Column("quote_status", sa.String(length=16), nullable=True))
    op.add_column("sales", sa.Column("converted_sale_id", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column("sales", sa.Column("payment_status", sa.String(length=24), nullable=False, server_default="PAID"))
    op.add_column("sales", sa.Column("amount_paid_cents", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("sales", sa.Column("due_balance_cents", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("sales", sa.Column("due_date", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE sales SET amount_paid_cents = total_cents, due_balance_cents = 0")
    op.create_foreign_key("fk_sales_customer_id_customers", "sales", "customers", ["customer_id"], ["id"])
    for column in ("sale_type", "customer_id", "is_quote_proforma", "quote_status", "payment_status"):
        op.create_index(f"ix_sales_{column}", "sales", [column])
    op.create_check_constraint("ck_sales_amount_paid_nonnegative", "sales", "amount_paid_cents >= 0")
    op.create_check_constraint("ck_sales_due_balance_nonnegative", "sales", "due_balance_cents >= 0")
    op.create_check_constraint(
        "ck_sales_paid_plus_due_is_total", "sales", "amount_paid_cents + due_balance_cents = total_cents"
    )

    op.add_column("sale_items", sa.Column("unit_type", sa.String(length=16), nullable=False, server_default="PIECE"))
    op.add_column("sale_items", sa.Column("unit_factor", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("sale_items", sa.Column("list_price_cents", sa.Integer(), nullable=True))
    op.add_column("sale_items", sa.Column("price_override_by_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_sale_items_price_override_by_id_users", "sale_items", "users", ["price_override_by_id"], ["id"]
    )

    op.create_table(
        "sale_tenders",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("sale_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], name="fk_sale_tenders_sale_id_sales", ondelete="CASCADE"),
        sa.CheckConstraint("amount_cents >= 1", name="ck_sale_tenders_amount_positive"),
    )
    op.create_index("ix_sale_tenders_sale_id", "sale_tenders", ["sale_id"])

    op.create_table(
        "customer_ledger_entries",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("customer_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("entry_type", sa.String(length=16), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("balance_after_cents", sa.Integer(), nullable=False),
        sa.Column("sale_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("method", sa.String(length=32), nullable=True),
        sa.Column("reference", sa.String(length=120), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], name="fk_customer_ledger_entries_customer_id_customers"
        ),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], name="fk_customer_ledger_entries_sale_id_sales"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_customer_ledger_entries_user_id_users"),
        sa.CheckConstraint("amount_cents <> 0", name="ck_customer_ledger_entries_amount_nonzero"),
    )
    for column in ("customer_id", "entry_type", "sale_id", "created_at"):
        op.create_index(f"ix_customer_ledger_entries_{column}", "customer_ledger_entries", [column])
    op.create_index(
        "ix_customer_ledger_entries_customer_created", "customer_ledger_entries", ["customer_id", "created_at"]
    )

    bind = op.get_bind()
    roles = sa.table("roles", sa.column("id", sa.Uuid(as_uuid=True)))
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Uuid(as_uuid=True)),
        sa.column("permission", sa.String(length=64)),
    )
    for role_id, permissions in GRANTS.items():
        if bind.execute(sa.select(roles.c.id).where(roles.c.id == role_id)).first() is None:
            continue
        held = {
            row[0]
            for row in bind.execute(
                sa.select(role_permissions.c.permission).where(role_permissions.c.role_id == role_id)
            )
        }
        missing = [{"role_id": role_id, "permission": item} for item in permissions if item not in held]
        if missing:
            op.bulk_insert(role_permissions, missing)


def downgrade() -> None:
    quoted = ", ".join(f"'{item}'" for item in NEW_PERMISSIONS)
    op.execute(f"DELETE FROM role_permissions WHERE permission IN ({quoted})")
    op.execute("DELETE FROM sale_items WHERE sale_id IN (SELECT id FROM sales WHERE is_quote_proforma)")
    op.execute("DELETE FROM sales WHERE is_quote_proforma")
    op.drop_table("customer_ledger_entries")
    op.drop_table("sale_tenders")
    op.drop_constraint("fk_sale_items_price_override_by_id_users", "sale_items", type_="foreignkey")
    for column in ("price_override_by_id", "list_price_cents", "unit_factor", "unit_type"):
        op.drop_column("sale_items", column)
    for name in ("paid_plus_due_is_total", "due_balance_nonnegative", "amount_paid_nonnegative"):
        op.drop_constraint(f"ck_sales_{name}", "sales", type_="check")
    for column in ("payment_status", "quote_status", "is_quote_proforma", "customer_id", "sale_type"):
        op.drop_index(f"ix_sales_{column}", table_name="sales")
    op.drop_constraint("fk_sales_customer_id_customers", "sales", type_="foreignkey")
    for column in (
        "due_date",
        "due_balance_cents",
        "amount_paid_cents",
        "payment_status",
        "converted_sale_id",
        "quote_status",
        "quote_expiry_date",
        "is_quote_proforma",
        "customer_id",
        "sale_type",
    ):
        op.drop_column("sales", column)
    op.drop_constraint("ck_products_moq_positive", "products", type_="check")
    op.drop_column("products", "sellable_units")
    op.drop_column("products", "min_order_quantity")
    op.drop_table("product_prices")
    op.drop_table("customers")
