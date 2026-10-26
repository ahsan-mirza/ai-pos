"""Sold-line snapshots, a customer history index, and per-customer vouchers.

Revision ID: 20261026_0074
Revises: 20261026_0073
Create Date: 2026-10-26

Buying history reads the name, SKU, and variant stored on the sale line. A voucher
points at a promotion; it does not calculate its own discount.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261026_0074"
down_revision: str | None = "20261026_0073"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLICY = (
    "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on') "
    "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on')"
)


def _rls(table: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'CREATE POLICY tenant_isolation ON "{table}" {POLICY}'))


def upgrade() -> None:
    op.add_column("sale_items", sa.Column("product_name", sa.String(160), nullable=True))
    op.add_column("sale_items", sa.Column("sku", sa.String(64), nullable=True))
    op.add_column("sale_items", sa.Column("variant_attributes", sa.JSON(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE sale_items SET "
            "product_name = (SELECT name FROM products WHERE products.id = sale_items.product_id), "
            "sku = (SELECT sku FROM products WHERE products.id = sale_items.product_id), "
            "variant_attributes = (SELECT variant_attributes FROM products WHERE products.id = sale_items.product_id) "
            "WHERE product_name IS NULL"
        )
    )
    op.create_index("ix_sales_customer_created", "sales", ["customer_id", "created_at"])

    op.create_table(
        "customer_coupons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("promotion_id", sa.Uuid(), sa.ForeignKey("promotions.id"), nullable=False),
        sa.Column("customer_id", sa.Uuid(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="issued"),
        sa.Column("reason", sa.String(255), nullable=False, server_default=""),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(80), nullable=False),
        sa.Column("sale_id", sa.Uuid(), sa.ForeignKey("sales.id"), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_customer_coupons"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_customer_coupons_code"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_customer_coupons_period"),
    )
    op.create_index("ix_customer_coupons_tenant_id", "customer_coupons", ["tenant_id"])
    op.create_index("ix_customer_coupons_promotion_id", "customer_coupons", ["promotion_id"])
    op.create_index("ix_customer_coupons_customer_id", "customer_coupons", ["customer_id"])
    op.create_index("ix_customer_coupons_status", "customer_coupons", ["status"])
    op.create_index("ix_customer_coupons_sale_id", "customer_coupons", ["sale_id"])
    _rls("customer_coupons")

    op.add_column("promotion_redemptions", sa.Column("customer_coupon_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_promotion_redemptions_customer_coupon_id",
        "promotion_redemptions",
        "customer_coupons",
        ["customer_coupon_id"],
        ["id"],
    )
    op.create_index(
        "ix_promotion_redemptions_customer_coupon_id",
        "promotion_redemptions",
        ["customer_coupon_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_promotion_redemptions_customer_coupon_id", table_name="promotion_redemptions")
    op.drop_constraint("fk_promotion_redemptions_customer_coupon_id", "promotion_redemptions", type_="foreignkey")
    op.drop_column("promotion_redemptions", "customer_coupon_id")
    op.drop_table("customer_coupons")
    op.drop_index("ix_sales_customer_created", table_name="sales")
    op.drop_column("sale_items", "variant_attributes")
    op.drop_column("sale_items", "sku")
    op.drop_column("sale_items", "product_name")
