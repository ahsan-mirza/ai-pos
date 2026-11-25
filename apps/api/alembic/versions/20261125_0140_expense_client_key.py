"""Stable client key so an offline expense posts once.

Revision ID: 20261125_0140
Revises: 20261125_0139
Create Date: 2026-11-25

Existing expenses have no client key. A repeated upload with the same key
returns the original expense and does not post petty cash again.
Not applied to a protected database.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261125_0140"
down_revision: str | None = "20261125_0139"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("expenses", sa.Column("client_key", sa.String(length=80), nullable=True))
    op.create_unique_constraint("uq_expenses_client_key", "expenses", ["tenant_id", "client_key"])


def downgrade() -> None:
    op.drop_constraint("uq_expenses_client_key", "expenses", type_="unique")
    op.drop_column("expenses", "client_key")
