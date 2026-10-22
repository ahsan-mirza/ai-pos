"""Recipes and ingredients: dish recipes, modifier ingredient deltas, per-sale ingredient usage, and the ingredient
flag on products.

Revision ID: 20261021_0053
Revises: 20261021_0052
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261021_0053"
down_revision: str | None = "20261021_0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("is_ingredient", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "recipes",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "product_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("yield_quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("yield_quantity >= 1", name="ck_recipes_yield_positive"),
    )
    op.create_table(
        "recipe_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("recipe_id", sa.Uuid(as_uuid=True), sa.ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ingredient_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("recipe_id", "ingredient_id", name="uq_recipe_lines_recipe_ingredient"),
        sa.CheckConstraint("quantity >= 1", name="ck_recipe_lines_quantity_positive"),
    )
    op.create_index("ix_recipe_lines_recipe_id", "recipe_lines", ["recipe_id"])
    op.create_index("ix_recipe_lines_ingredient_id", "recipe_lines", ["ingredient_id"])
    op.create_table(
        "modifier_ingredients",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "option_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("modifier_options.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ingredient_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.UniqueConstraint("option_id", "ingredient_id", name="uq_modifier_ingredients_option_ingredient"),
        sa.CheckConstraint("quantity <> 0", name="ck_modifier_ingredients_quantity_nonzero"),
    )
    op.create_index("ix_modifier_ingredients_option_id", "modifier_ingredients", ["option_id"])
    op.create_table(
        "recipe_usages",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("sale_id", sa.Uuid(as_uuid=True), sa.ForeignKey("sales.id", ondelete="CASCADE"), nullable=False),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("ingredient_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity_needed", sa.Integer(), nullable=False),
        sa.Column("quantity_drawn", sa.Integer(), nullable=False),
        sa.Column("cost_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_recipe_usages_sale_id", "recipe_usages", ["sale_id"])
    op.create_index(
        "ix_recipe_usages_store_ingredient_created", "recipe_usages", ["store_id", "ingredient_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("recipe_usages")
    op.drop_table("modifier_ingredients")
    op.drop_table("recipe_lines")
    op.drop_table("recipes")
    op.drop_column("products", "is_ingredient")
