"""Pricing engine: customer groups, price lists (customer, group, store, business-wide) with items, scheduled
price changes; the customer's VAT treatment and certificate; price source and VAT relief on sale lines.

Revision ID: 20261021_0060
Revises: 20261021_0059
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261021_0060"
down_revision: str | None = "20261021_0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "customer_groups",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("default_tier", sa.String(16), nullable=True),
        sa.Column("default_discount_bps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payment_terms", sa.String(16), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
    )
    op.add_column(
        "customers",
        sa.Column("group_id", sa.Uuid(as_uuid=True), sa.ForeignKey("customer_groups.id"), nullable=True),
    )
    op.create_index("ix_customers_group_id", "customers", ["group_id"])
    op.add_column("customers", sa.Column("tax_treatment", sa.String(16), nullable=False, server_default="STANDARD"))
    op.add_column("customers", sa.Column("tax_certificate_ref", sa.String(64), nullable=True))
    op.add_column("customers", sa.Column("tax_certificate_expiry", sa.Date(), nullable=True))

    op.create_table(
        "price_lists",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("scope", sa.String(10), nullable=False),
        sa.Column("scope_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
    )
    op.create_index("ix_price_lists_scope", "price_lists", ["scope"])
    op.create_index("ix_price_lists_scope_id", "price_lists", ["scope_id"])
    op.create_table(
        "price_list_items",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "price_list_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("price_lists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=True),
        sa.Column("discount_bps", sa.Integer(), nullable=True),
        sa.Column("min_qty", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("volume_breaks", sa.JSON(), nullable=True),
        sa.UniqueConstraint("price_list_id", "product_id", name="uq_price_list_items_list_product"),
        sa.CheckConstraint(
            "(price_cents IS NULL) <> (discount_bps IS NULL)", name="ck_price_list_items_price_or_discount"
        ),
        sa.CheckConstraint("min_qty >= 1", name="ck_price_list_items_min_qty_positive"),
    )
    op.create_index("ix_price_list_items_price_list_id", "price_list_items", ["price_list_id"])
    op.create_index("ix_price_list_items_product_id", "price_list_items", ["product_id"])

    op.create_table(
        "scheduled_price_changes",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="SCHEDULED"),
        sa.Column("note", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_scheduled_price_changes_run_at", "scheduled_price_changes", ["run_at"])
    op.create_index("ix_scheduled_price_changes_status", "scheduled_price_changes", ["status"])
    op.create_table(
        "scheduled_price_change_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "change_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("scheduled_price_changes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("retail_price_cents", sa.Integer(), nullable=True),
        sa.Column("tier_prices", sa.JSON(), nullable=True),
        sa.Column("previous_retail_cents", sa.Integer(), nullable=True),
        sa.Column("previous_tier_prices", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_scheduled_price_change_lines_change_id", "scheduled_price_change_lines", ["change_id"])

    op.add_column("sale_items", sa.Column("price_source", sa.String(16), nullable=True))
    op.add_column("sale_items", sa.Column("price_list_id", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column("sale_items", sa.Column("tax_treatment", sa.String(16), nullable=True))


def downgrade() -> None:
    for column in ("tax_treatment", "price_list_id", "price_source"):
        op.drop_column("sale_items", column)
    op.drop_table("scheduled_price_change_lines")
    op.drop_table("scheduled_price_changes")
    op.drop_table("price_list_items")
    op.drop_table("price_lists")
    for column in ("tax_certificate_expiry", "tax_certificate_ref", "tax_treatment"):
        op.drop_column("customers", column)
    op.drop_index("ix_customers_group_id", table_name="customers")
    op.drop_column("customers", "group_id")
    op.drop_table("customer_groups")
