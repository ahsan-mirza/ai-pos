"""Hide a deleted till without removing its sales or invoice series.

Revision ID: 20261127_0142
Revises: 20261126_0141
Create Date: 2026-11-27

A deleted till keeps the device row so invoices, cash, and sequences still
point at it. The list and the package seat ignore that row, and its code is
renamed so the branch can register that code again.
Not applied to a protected database.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261127_0142"
down_revision: str | None = "20261126_0141"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("devices", "deleted_at")
