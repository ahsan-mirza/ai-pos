"""Fashion customer profile: birthday, gender, preferred sizes, notes and tags.

Revision ID: 20261021_0065
Revises: 20261021_0064
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261021_0065"
down_revision: str | None = "20261021_0064"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("birthday", sa.Date(), nullable=True))
    op.add_column("customers", sa.Column("gender", sa.String(12), nullable=True))
    op.add_column("customers", sa.Column("preferred_sizes", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("customers", sa.Column("notes", sa.String(500), nullable=True))
    op.add_column("customers", sa.Column("tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))


def downgrade() -> None:
    op.drop_column("customers", "tags")
    op.drop_column("customers", "notes")
    op.drop_column("customers", "preferred_sizes")
    op.drop_column("customers", "gender")
    op.drop_column("customers", "birthday")
