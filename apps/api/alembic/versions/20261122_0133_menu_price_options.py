"""Priced serving options for one menu item. Not a modifier and not a second product.

Revision ID: 20261122_0133
Revises: 20261122_0132
Create Date: 2026-11-22

Additive. Not applied to a protected database.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261122_0133"
down_revision: str | None = "20261122_0132"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLICY = (
    "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on') "
    "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on')"
)


def upgrade() -> None:
    op.create_table(
        "menu_price_options",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("price_cents >= 0", name="ck_menu_price_options_price_nonnegative"),
        sa.UniqueConstraint("tenant_id", "product_id", "name", name="uq_menu_price_options_product_name"),
    )
    op.create_index("ix_menu_price_options_tenant_id", "menu_price_options", ["tenant_id"])
    op.create_index("ix_menu_price_options_product_id", "menu_price_options", ["product_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text('ALTER TABLE "menu_price_options" ENABLE ROW LEVEL SECURITY'))  # noqa: TID251
        op.execute(sa.text('ALTER TABLE "menu_price_options" FORCE ROW LEVEL SECURITY'))  # noqa: TID251
        op.execute(sa.text(f'CREATE POLICY tenant_isolation ON "menu_price_options" {POLICY}'))  # noqa: TID251
    for table in ("sale_items", "open_order_items"):
        op.add_column(table, sa.Column("price_option_id", sa.Uuid(), nullable=True))
        op.add_column(table, sa.Column("price_option_name", sa.String(length=80), nullable=True))
        op.add_column(table, sa.Column("price_option_cents", sa.Integer(), nullable=True))


def downgrade() -> None:
    for table in ("open_order_items", "sale_items"):
        op.drop_column(table, "price_option_cents")
        op.drop_column(table, "price_option_name")
        op.drop_column(table, "price_option_id")
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text('DROP POLICY IF EXISTS tenant_isolation ON "menu_price_options"'))  # noqa: TID251
        op.execute(sa.text('ALTER TABLE "menu_price_options" NO FORCE ROW LEVEL SECURITY'))  # noqa: TID251
        op.execute(sa.text('ALTER TABLE "menu_price_options" DISABLE ROW LEVEL SECURITY'))  # noqa: TID251
    op.drop_index("ix_menu_price_options_product_id", table_name="menu_price_options")
    op.drop_index("ix_menu_price_options_tenant_id", table_name="menu_price_options")
    op.drop_table("menu_price_options")
