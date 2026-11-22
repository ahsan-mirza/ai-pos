"""Device public-key thumbprint for permanent offline entitlements.

Revision ID: 20261122_0124
Revises: 20261121_0123
Create Date: 2026-11-22

Additive. Existing device rows stay valid with a null thumbprint. This revision does not
change inventory tables and was not applied to the developer or inventory acceptance databases.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261122_0124"
down_revision: str | None = "20261121_0123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("device_public_key_thumbprint", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("devices", "device_public_key_thumbprint")
