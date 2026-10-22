"""Separate prepared dishes from tracked ingredients and packaged goods.

Revision ID: 20261022_0066
Revises: 20261021_0065
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261022_0066"
down_revision: str | None = "20261021_0065"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PACKAGED = (
    "SAMPLE-SOFT-DRINK",
    "SAMPLE-WATER",
    "SAMPLE-CAFE-WATER",
    "SAMPLE-QSR-COLA",
    "SAMPLE-QSR-ORANGE-SODA",
    "SAMPLE-QSR-WATER",
    "SAMPLE-QSR-APPLE-JUICE",
)


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("item_type", sa.String(length=20), nullable=False, server_default="PRE_PACKAGED"),
    )
    op.add_column(
        "products",
        sa.Column("is_stock_tracked", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_check_constraint(
        "ck_products_item_type",
        "products",
        "item_type IN ('MADE_TO_ORDER', 'RAW_INGREDIENT', 'PRE_PACKAGED')",
    )
    op.execute(
        "UPDATE products SET item_type = 'RAW_INGREDIENT', is_stock_tracked = true WHERE is_ingredient = true"
    )
    op.execute(
        """
        UPDATE products
        SET item_type = 'MADE_TO_ORDER', is_stock_tracked = false, is_ingredient = false, is_service = false
        WHERE id IN (SELECT product_id FROM recipes)
        """
    )
    op.execute(
        """
        UPDATE products
        SET item_type = 'MADE_TO_ORDER', is_stock_tracked = false
        WHERE is_service = true
          AND is_ingredient = false
          AND sku <> 'SRV-GIFT-CARD'
          AND id NOT IN (SELECT product_id FROM warranty_plans)
          AND category NOT IN ('Services', 'Gift cards')
        """
    )
    quoted = ", ".join(f"'{sku}'" for sku in PACKAGED)
    op.execute(
        f"""
        UPDATE products
        SET item_type = 'PRE_PACKAGED', is_stock_tracked = true, is_ingredient = false, is_service = false
        WHERE sku IN ({quoted})
        """
    )
    op.execute(
        """
        UPDATE products
        SET is_service = false
        WHERE item_type = 'MADE_TO_ORDER'
          AND id NOT IN (SELECT product_id FROM combo_slots)
        """
    )


def downgrade() -> None:
    op.drop_constraint("ck_products_item_type", "products", type_="check")
    op.drop_column("products", "is_stock_tracked")
    op.drop_column("products", "item_type")
