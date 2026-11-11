"""Manager approval on a short COD handover.

Revision ID: 20261111_0103
Revises: 20261109_0102
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261111_0103"
down_revision: str | None = "20261109_0102"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("cod_handovers", sa.Column("approved_by_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_cod_handovers_approved_by_id_users", "cod_handovers", "users", ["approved_by_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_cod_handovers_approved_by_id_users", "cod_handovers", type_="foreignkey")
    op.drop_column("cod_handovers", "approved_by_id")
