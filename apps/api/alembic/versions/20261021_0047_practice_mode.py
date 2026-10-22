"""Practice mode for self-service stores: sample products and customers, and when the business went live.

Existing businesses are live already, so live_at is backfilled; only signup provisioning clears it.

Revision ID: 20261021_0047
Revises: 20261021_0046
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261021_0047"
down_revision: str | None = "20261021_0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("is_sample", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("customers", sa.Column("is_sample", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("business_settings", sa.Column("live_at", sa.DateTime(timezone=True), nullable=True))
    settings = sa.table("business_settings", sa.column("live_at", sa.DateTime(timezone=True)))
    op.execute(settings.update().values(live_at=sa.func.now()))


def downgrade() -> None:
    op.drop_column("business_settings", "live_at")
    op.drop_column("customers", "is_sample")
    op.drop_column("products", "is_sample")
