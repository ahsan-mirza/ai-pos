"""Commercial add-ons may name the capability keys they unlock.

Revision ID: control_0016
Revises: control_0015
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0016"
down_revision: str | None = "control_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("billing_addons", sa.Column("module_keys", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("billing_addons", "module_keys")
