"""Units of measure: a business's own packs (CASE_24, PACK_6, ...) beside the built-in PIECE, BOX_10 and
CARTON_100. Existing products and sale lines only use built-in codes, so no rows need rewriting.

Revision ID: 20261021_0052
Revises: 20261021_0051
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261021_0052"
down_revision: str | None = "20261021_0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "units_of_measure",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(16), nullable=False, unique=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("short_name", sa.String(16), nullable=False),
        sa.Column("factor", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("factor >= 2", name="ck_units_of_measure_uom_factor_at_least_two"),
    )


def downgrade() -> None:
    op.drop_table("units_of_measure")
