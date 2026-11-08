"""Remember the street address chosen during signup.

Revision ID: control_0023
Revises: control_0022
Create Date: 2026-11-08

The branch row already has stores.address. This column only holds the address
until provisioning copies it onto that branch. Apply on the control database only.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0023"
down_revision: str | None = "control_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("signup_requests", sa.Column("address", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("signup_requests", "address")
