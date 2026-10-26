"""Job and identity details on an employee payroll profile.

Revision ID: 20261026_0076
Revises: 20261026_0075
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261026_0076"
down_revision: str | None = "20261026_0075"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("employee_profiles", sa.Column("job_title", sa.String(80), nullable=False, server_default=""))
    op.add_column("employee_profiles", sa.Column("nationality", sa.String(60), nullable=False, server_default=""))
    op.add_column("employee_profiles", sa.Column("phone", sa.String(20), nullable=False, server_default=""))
    op.add_column("employee_profiles", sa.Column("emirates_id", sa.String(15), nullable=False, server_default=""))
    op.add_column("employee_profiles", sa.Column("passport_number", sa.String(20), nullable=False, server_default=""))
    op.add_column("employee_profiles", sa.Column("joined_on", sa.Date(), nullable=True))
    op.add_column("employee_profiles", sa.Column("date_of_birth", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("employee_profiles", "date_of_birth")
    op.drop_column("employee_profiles", "joined_on")
    op.drop_column("employee_profiles", "passport_number")
    op.drop_column("employee_profiles", "emirates_id")
    op.drop_column("employee_profiles", "phone")
    op.drop_column("employee_profiles", "nationality")
    op.drop_column("employee_profiles", "job_title")
