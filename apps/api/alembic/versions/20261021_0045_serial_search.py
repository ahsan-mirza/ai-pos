"""Serial search: a plain-text suffix for "ends with" lookups and a composite index for picker queries.

Existing rows get their suffix filled in by the API on first search (it needs the encryption key).

Revision ID: 20261021_0045
Revises: 20261020_0044
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261021_0045"
down_revision: str | None = "20261020_0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("serial_numbers", sa.Column("value_suffix", sa.String(8), nullable=True))
    op.create_index("ix_serial_numbers_value_suffix", "serial_numbers", ["value_suffix"])
    op.create_index("ix_serial_numbers_product_store_status", "serial_numbers", ["product_id", "store_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_serial_numbers_product_store_status", table_name="serial_numbers")
    op.drop_index("ix_serial_numbers_value_suffix", table_name="serial_numbers")
    op.drop_column("serial_numbers", "value_suffix")
