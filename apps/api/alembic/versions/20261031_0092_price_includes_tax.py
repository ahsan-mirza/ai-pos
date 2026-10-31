"""A product price can already include tax. Sales snapshot that choice.

Revision ID: 20261031_0092
Revises: 20261031_0091
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261031_0092"
down_revision: str | None = "20261031_0091"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("price_includes_tax", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Null on rows sold before this column. New sales write the product's setting at the time.
    op.add_column("sale_items", sa.Column("price_includes_tax", sa.Boolean(), nullable=True))
    # Copy the old business-wide switch onto products that were already priced that way.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            UPDATE products AS product
            SET price_includes_tax = true
            FROM business_settings AS settings
            WHERE settings.tenant_id = product.tenant_id
              AND settings.prices_include_vat = true
            """
        )
    else:
        op.execute(
            """
            UPDATE products
            SET price_includes_tax = 1
            WHERE tenant_id IN (
                SELECT tenant_id FROM business_settings WHERE prices_include_vat = 1
            )
            """
        )


def downgrade() -> None:
    op.drop_column("sale_items", "price_includes_tax")
    op.drop_column("products", "price_includes_tax")
