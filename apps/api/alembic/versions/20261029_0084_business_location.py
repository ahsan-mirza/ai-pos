"""Where the business is, apart from each branch address.

Revision ID: 20261029_0084
Revises: 20261028_0083
Create Date: 2026-10-29

The column is empty until someone records a city or area in store settings.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261029_0084"
down_revision: str | None = "20261028_0083"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("business_settings", sa.Column("location", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("business_settings", "location")
