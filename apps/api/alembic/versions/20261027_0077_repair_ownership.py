"""Customer repairs and shop-owned equipment repairs share one ticket table.

Revision ID: 20261027_0077
Revises: 20261026_0076
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261027_0077"
down_revision: str | None = "20261026_0076"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "repair_tickets",
        sa.Column("ownership", sa.String(12), nullable=False, server_default="customer"),
    )
    op.add_column("repair_tickets", sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_index("ix_repair_tickets_product_id", "repair_tickets", ["product_id"])
    op.create_foreign_key(
        "fk_repair_tickets_product_id_products",
        "repair_tickets",
        "products",
        ["product_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_repair_tickets_product_id_products", "repair_tickets", type_="foreignkey")
    op.drop_index("ix_repair_tickets_product_id", table_name="repair_tickets")
    op.drop_column("repair_tickets", "product_id")
    op.drop_column("repair_tickets", "ownership")
