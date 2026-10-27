"""Indexes for repair job search and overdue filters.

Revision ID: 20261027_0078
Revises: 20261027_0077
Create Date: 2026-10-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261027_0078"
down_revision: str | None = "20261027_0077"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_repair_tickets_identifier_hash", "repair_tickets", ["identifier_hash"])
    op.create_index("ix_repair_tickets_promised_at", "repair_tickets", ["promised_at"])


def downgrade() -> None:
    op.drop_index("ix_repair_tickets_promised_at", table_name="repair_tickets")
    op.drop_index("ix_repair_tickets_identifier_hash", table_name="repair_tickets")
