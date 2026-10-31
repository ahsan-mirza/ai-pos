"""One open dine-in order per table.

Revision ID: 20261031_0093
Revises: 20261031_0092
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261031_0093"
down_revision: str | None = "20261031_0092"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WHERE = sa.text("status = 'OPEN' AND service_type = 'DINE_IN'")


def upgrade() -> None:
    op.create_index(
        "uq_open_orders_active_dine_in",
        "open_orders",
        ["table_id"],
        unique=True,
        sqlite_where=_WHERE,
        postgresql_where=_WHERE,
    )


def downgrade() -> None:
    op.drop_index("uq_open_orders_active_dine_in", table_name="open_orders")
