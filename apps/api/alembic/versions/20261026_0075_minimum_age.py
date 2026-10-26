"""Optional minimum age on a product. Null means the till does not ask.

Revision ID: 20261026_0075
Revises: 20261026_0074
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261026_0075"
down_revision: str | None = "20261026_0074"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("minimum_age", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_products_minimum_age",
        "products",
        "minimum_age IS NULL OR (minimum_age >= 1 AND minimum_age <= 120)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_products_minimum_age", "products", type_="check")
    op.drop_column("products", "minimum_age")
