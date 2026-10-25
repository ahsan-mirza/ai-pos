"""Public sales email for the marketing-site footer.

Revision ID: control_0012
Revises: control_0011
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0012"
down_revision: str | None = "control_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("site_settings", sa.Column("email", sa.String(254), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("site_settings", "email")
