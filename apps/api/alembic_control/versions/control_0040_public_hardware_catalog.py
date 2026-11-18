"""Public marketing hardware catalogue on the registry connection.

Revision ID: control_0040
Revises: control_0039
Create Date: 2026-11-18

These tables are platform records. They do not add tenant_id. Downgrade drops only these tables.
Existing hardware_items, orders, assignments, and billing plans stay in place.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0040"
down_revision: str | None = "control_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "public_hardware_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("image_key", sa.String(length=80), nullable=True),
        sa.Column("thumb_key", sa.String(length=80), nullable=True),
        sa.Column("image_alt", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_public_hardware_categories"),
        sa.UniqueConstraint("slug", name="uq_public_hardware_categories_slug"),
    )
    op.create_table(
        "public_hardware_products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("sku", sa.String(length=32), nullable=False),
        sa.Column("short_description", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("full_description", sa.Text(), nullable=False, server_default=""),
        sa.Column("brand", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("model_number", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("manufacturer", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("specifications", sa.JSON(), nullable=False),
        sa.Column("purchase_price_fils", sa.Integer(), nullable=True),
        sa.Column("display_price_fils", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="AED"),
        sa.Column("warranty_months", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stock_status", sa.String(length=16), nullable=False, server_default="on_request"),
        sa.Column("compatibility", sa.Text(), nullable=False, server_default=""),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "stock_status IN ('in_stock', 'limited', 'out_of_stock', 'on_request')",
            name="ck_public_hardware_products_stock_status",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["public_hardware_categories.id"],
            name="fk_public_hardware_products_category_id_public_hardware_categories",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_public_hardware_products"),
        sa.UniqueConstraint("sku", name="uq_public_hardware_products_sku"),
        sa.UniqueConstraint("slug", name="uq_public_hardware_products_slug"),
    )
    op.create_index("ix_public_hardware_products_category_id", "public_hardware_products", ["category_id"])
    op.create_index("ix_public_hardware_products_is_published", "public_hardware_products", ["is_published"])
    op.create_index("ix_public_hardware_products_archived", "public_hardware_products", ["archived"])
    op.create_table(
        "public_hardware_packages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("short_description", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("full_description", sa.Text(), nullable=False, server_default=""),
        sa.Column("display_price_fils", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="AED"),
        sa.Column("billing_plan_id", sa.Uuid(), nullable=True),
        sa.Column("package_type", sa.String(length=24), nullable=False, server_default="hardware_only"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "package_type IN ('hardware_only', 'hardware_software', 'all_in_one', 'custom')",
            name="ck_public_hardware_packages_package_type",
        ),
        sa.ForeignKeyConstraint(
            ["billing_plan_id"],
            ["billing_plans.id"],
            name="fk_public_hardware_packages_billing_plan_id_billing_plans",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_public_hardware_packages"),
        sa.UniqueConstraint("slug", name="uq_public_hardware_packages_slug"),
    )
    op.create_index("ix_public_hardware_packages_billing_plan_id", "public_hardware_packages", ["billing_plan_id"])
    op.create_index("ix_public_hardware_packages_is_featured", "public_hardware_packages", ["is_featured"])
    op.create_index("ix_public_hardware_packages_is_published", "public_hardware_packages", ["is_published"])
    op.create_table(
        "public_hardware_package_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("package_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_optional", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("quantity >= 1 AND quantity <= 99", name="ck_public_hardware_package_items_quantity"),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["public_hardware_packages.id"],
            name="fk_public_hardware_package_items_package_id_public_hardware_packages",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["public_hardware_products.id"],
            name="fk_public_hardware_package_items_product_id_public_hardware_products",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_public_hardware_package_items"),
        sa.UniqueConstraint("package_id", "product_id", name="uq_public_hardware_package_items_product"),
    )
    op.create_index("ix_public_hardware_package_items_package_id", "public_hardware_package_items", ["package_id"])
    op.create_index("ix_public_hardware_package_items_product_id", "public_hardware_package_items", ["product_id"])
    op.create_table(
        "public_hardware_product_images",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("package_id", sa.Uuid(), nullable=True),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("thumb_key", sa.String(length=80), nullable=False),
        sa.Column("alt", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("width", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("height", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["public_hardware_packages.id"],
            name="fk_public_hardware_product_images_package_id_public_hardware_packages",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["public_hardware_products.id"],
            name="fk_public_hardware_product_images_product_id_public_hardware_products",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_public_hardware_product_images"),
    )
    op.create_index("ix_public_hardware_product_images_package_id", "public_hardware_product_images", ["package_id"])
    op.create_index("ix_public_hardware_product_images_product_id", "public_hardware_product_images", ["product_id"])
    op.create_table(
        "public_hardware_enquiries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("enquiry_reference", sa.String(length=24), nullable=False),
        sa.Column("customer_name", sa.String(length=120), nullable=False),
        sa.Column("business_name", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("country", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("business_type", sa.String(length=32), nullable=False),
        sa.Column("enquiry_type", sa.String(length=16), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("package_id", sa.Uuid(), nullable=True),
        sa.Column("product_label", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("package_label", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="new"),
        sa.Column("source", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('new', 'contacted', 'quoted', 'converted', 'closed')",
            name="ck_public_hardware_enquiries_status",
        ),
        sa.CheckConstraint(
            "enquiry_type IN ('product', 'package', 'custom', 'installation')",
            name="ck_public_hardware_enquiries_enquiry_type",
        ),
        sa.CheckConstraint("quantity >= 1 AND quantity <= 999", name="ck_public_hardware_enquiries_quantity"),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["public_hardware_packages.id"],
            name="fk_public_hardware_enquiries_package_id_public_hardware_packages",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["public_hardware_products.id"],
            name="fk_public_hardware_enquiries_product_id_public_hardware_products",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_public_hardware_enquiries"),
        sa.UniqueConstraint("enquiry_reference", name="uq_public_hardware_enquiries_reference"),
    )
    op.create_index("ix_public_hardware_enquiries_email", "public_hardware_enquiries", ["email"])
    op.create_index("ix_public_hardware_enquiries_package_id", "public_hardware_enquiries", ["package_id"])
    op.create_index("ix_public_hardware_enquiries_product_id", "public_hardware_enquiries", ["product_id"])
    op.create_index("ix_public_hardware_enquiries_status", "public_hardware_enquiries", ["status"])
    op.create_index("ix_public_hardware_enquiries_created_at", "public_hardware_enquiries", ["created_at"])
    op.create_table(
        "public_hardware_enquiry_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("enquiry_id", sa.Uuid(), nullable=False),
        sa.Column("operator_id", sa.Uuid(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["enquiry_id"],
            ["public_hardware_enquiries.id"],
            name="fk_public_hardware_enquiry_notes_enquiry_id_public_hardware_enquiries",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            ["operators.id"],
            name="fk_public_hardware_enquiry_notes_operator_id_operators",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_public_hardware_enquiry_notes"),
    )
    op.create_index("ix_public_hardware_enquiry_notes_enquiry_id", "public_hardware_enquiry_notes", ["enquiry_id"])


def downgrade() -> None:
    op.drop_table("public_hardware_enquiry_notes")
    op.drop_table("public_hardware_enquiries")
    op.drop_table("public_hardware_product_images")
    op.drop_table("public_hardware_package_items")
    op.drop_table("public_hardware_packages")
    op.drop_table("public_hardware_products")
    op.drop_table("public_hardware_categories")
