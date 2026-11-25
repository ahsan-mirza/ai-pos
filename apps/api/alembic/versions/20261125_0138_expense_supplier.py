"""Link a paid expense to an existing supplier.

Revision ID: 20261125_0138
Revises: 20261125_0137
Create Date: 2026-11-25

The supplier is optional. Existing expenses stay unlinked. Removing a
supplier clears the link and leaves the expense and its payee text.
Not applied to a protected database.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261125_0138"
down_revision: str | None = "20261125_0137"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "expenses",
        sa.Column("supplier_id", sa.Uuid(), sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_expenses_supplier_id", "expenses", ["supplier_id"])


def downgrade() -> None:
    op.drop_index("ix_expenses_supplier_id", table_name="expenses")
    op.drop_column("expenses", "supplier_id")
