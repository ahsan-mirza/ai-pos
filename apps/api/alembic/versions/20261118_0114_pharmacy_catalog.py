"""Pharmacy catalogue: category ordering, medicine master, ingredients, and documents.

Revision ID: 20261118_0114
Revises: 20261118_0113
Create Date: 2026-11-18

Existing categories stay active. Existing products gain nullable generic-name and GTIN
copies used only by search. Grocery batch behaviour is unchanged.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261118_0114"
down_revision: str | None = "20261118_0113"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _compact(column: str) -> str:
    return f"replace(replace({column}, '-', ''), ' ', '')"


def _haystack(pharmacy: bool) -> str:
    parts = [
        "name",
        "coalesce(model_number, '')",
        "barcode",
        "sku",
        "category",
        "coalesce(brand, '')",
        "coalesce(season, '')",
        "coalesce(collection, '')",
        _compact("coalesce(model_number, '')"),
        _compact("sku"),
        _compact("barcode"),
    ]
    if pharmacy:
        parts.extend(
            [
                "coalesce(generic_name, '')",
                "coalesce(gtin, '')",
                _compact("coalesce(gtin, '')"),
            ]
        )
    return "lower(" + " || ' ' || ".join(parts) + ")"


def _rebuild_search(pharmacy: bool) -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    if postgres:
        op.drop_index("ix_products_search_trgm", table_name="products")
    op.drop_column("products", "search_text")
    op.add_column(
        "products",
        sa.Column("search_text", sa.Text(), sa.Computed(_haystack(pharmacy), persisted=postgres or None)),
    )
    if postgres:
        op.create_index(
            "ix_products_search_trgm",
            "products",
            ["search_text"],
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        )


def upgrade() -> None:
    op.add_column("categories", sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("categories", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("categories", sa.Column("image_key", sa.String(length=160), nullable=True))
    op.add_column("categories", sa.Column("product_kinds", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("categories", sa.Column("form_policy", sa.String(length=16), nullable=False, server_default=""))
    op.add_column("sub_categories", sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("sub_categories", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("products", sa.Column("generic_name", sa.String(length=200), nullable=True))
    op.add_column("products", sa.Column("gtin", sa.String(length=14), nullable=True))
    op.create_unique_constraint("uq_products_gtin", "products", ["tenant_id", "gtin"])
    _rebuild_search(True)
    op.create_table(
        "substitution_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_substitution_groups"),
    )
    op.create_index("ix_substitution_groups_tenant_id", "substitution_groups", ["tenant_id"])
    op.create_table(
        "product_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("reference", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("storage_key", sa.String(length=160), nullable=True),
        sa.Column("uploaded_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('leaflet', 'registration', 'supplier', 'other')",
            name="ck_product_documents_kind",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_product_documents"),
    )
    op.create_index("ix_product_documents_tenant_id", "product_documents", ["tenant_id"])
    op.create_index("ix_product_documents_product_id", "product_documents", ["product_id"])
    op.create_table(
        "pharmacy_product_details",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("product_kind", sa.String(length=20), nullable=False),
        sa.Column("generic_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("manufacturer", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("marketing_authorization_holder", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("country_of_origin", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("gtin", sa.String(length=14), nullable=False, server_default=""),
        sa.Column("manufacturer_product_ref", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("dosage_form", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("route", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("strength_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("strength_unit", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("strength_display", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("concentration", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("pack_size_label", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("units_per_pack", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("base_unit_code", sa.String(length=16), nullable=False, server_default="PIECE"),
        sa.Column("purchase_unit_code", sa.String(length=16), nullable=False, server_default="PIECE"),
        sa.Column("selling_unit_code", sa.String(length=16), nullable=False, server_default="PIECE"),
        sa.Column("dispense_unit_code", sa.String(length=16), nullable=False, server_default="PIECE"),
        sa.Column("fractional_dispensing_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("dispensing_class", sa.String(length=20), nullable=False),
        sa.Column("classification_source", sa.String(length=24), nullable=False, server_default="TENANT_DECLARED"),
        sa.Column("pharmaceutical_class", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("registration_number", sa.String(length=80), nullable=True),
        sa.Column("registration_authority", sa.String(length=80), nullable=True),
        sa.Column("marketing_authorization_ref", sa.String(length=80), nullable=True),
        sa.Column("storage_condition", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("temp_min_c", sa.Numeric(5, 2), nullable=True),
        sa.Column("temp_max_c", sa.Numeric(5, 2), nullable=True),
        sa.Column("cold_chain", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("handling_instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("warnings_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("leaflet_document_id", sa.Uuid(), nullable=True),
        sa.Column("price_control", sa.String(length=16), nullable=False, server_default="NONE"),
        sa.Column("min_price_cents", sa.Integer(), nullable=True),
        sa.Column("max_price_cents", sa.Integer(), nullable=True),
        sa.Column("discount_eligible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("promotion_eligible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("offline_policy", sa.String(length=8), nullable=False, server_default="BLOCK"),
        sa.Column("substitution_group_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "product_kind IN ('MEDICINE', 'DEVICE', 'SUPPLY', 'SUPPLEMENT', 'PERSONAL_CARE', "
            "'COSMETIC', 'NUTRITION', 'VETERINARY', 'ACCESSORY')",
            name="ck_pharmacy_product_details_kind",
        ),
        sa.CheckConstraint(
            "dispensing_class IN ('OTC', 'PRESCRIPTION', 'CONTROLLED', 'SEMI_CONTROLLED', "
            "'RESTRICTED', 'SPECIAL_HANDLING')",
            name="ck_pharmacy_product_details_class",
        ),
        sa.CheckConstraint(
            "price_control IN ('NONE', 'MINIMUM', 'MAXIMUM', 'FIXED')",
            name="ck_pharmacy_product_details_price_control",
        ),
        sa.CheckConstraint(
            "offline_policy IN ('ALLOW', 'BLOCK')",
            name="ck_pharmacy_product_details_offline",
        ),
        sa.CheckConstraint(
            "classification_source IN ('TENANT_DECLARED', 'AUTHORITY_CONFIRMED')",
            name="ck_pharmacy_product_details_source",
        ),
        sa.CheckConstraint("units_per_pack >= 1", name="ck_pharmacy_product_details_pack"),
        sa.CheckConstraint(
            "min_price_cents IS NULL OR min_price_cents >= 0",
            name="ck_pharmacy_product_details_min_price",
        ),
        sa.CheckConstraint(
            "max_price_cents IS NULL OR max_price_cents >= 0",
            name="ck_pharmacy_product_details_max_price",
        ),
        sa.ForeignKeyConstraint(["leaflet_document_id"], ["product_documents.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["substitution_group_id"], ["substitution_groups.id"]),
        sa.PrimaryKeyConstraint("product_id", name="pk_pharmacy_product_details"),
    )
    op.create_index("ix_pharmacy_product_details_tenant_id", "pharmacy_product_details", ["tenant_id"])
    op.create_table(
        "product_ingredients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("strength_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("strength_unit", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("is_active_ingredient", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_product_ingredients_position"),
        sa.CheckConstraint(
            "strength_amount IS NULL OR strength_amount >= 0",
            name="ck_product_ingredients_strength",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["pharmacy_product_details.product_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_product_ingredients"),
    )
    op.create_index("ix_product_ingredients_tenant_id", "product_ingredients", ["tenant_id"])
    op.create_index("ix_product_ingredients_product_id", "product_ingredients", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_product_ingredients_product_id", table_name="product_ingredients")
    op.drop_index("ix_product_ingredients_tenant_id", table_name="product_ingredients")
    op.drop_table("product_ingredients")
    op.drop_index("ix_pharmacy_product_details_tenant_id", table_name="pharmacy_product_details")
    op.drop_table("pharmacy_product_details")
    op.drop_index("ix_product_documents_product_id", table_name="product_documents")
    op.drop_index("ix_product_documents_tenant_id", table_name="product_documents")
    op.drop_table("product_documents")
    op.drop_index("ix_substitution_groups_tenant_id", table_name="substitution_groups")
    op.drop_table("substitution_groups")
    _rebuild_search(False)
    op.drop_constraint("uq_products_gtin", "products", type_="unique")
    op.drop_column("products", "gtin")
    op.drop_column("products", "generic_name")
    op.drop_column("sub_categories", "is_active")
    op.drop_column("sub_categories", "display_order")
    op.drop_column("categories", "form_policy")
    op.drop_column("categories", "product_kinds")
    op.drop_column("categories", "image_key")
    op.drop_column("categories", "is_active")
    op.drop_column("categories", "display_order")
