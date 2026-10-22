"""Business profile, module (capability) selection and onboarding state on business settings.

Revision ID: 20261020_0040
Revises: 20261020_0039
Create Date: 2026-10-20
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "20261020_0040"
down_revision: str | None = "20261020_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

settings = sa.table(
    "business_settings",
    sa.column("business_profile", sa.String),
    sa.column("onboarded_at", sa.DateTime(timezone=True)),
)
TRADING = ("users", "stores")


def upgrade() -> None:
    op.add_column(
        "business_settings",
        sa.Column("business_profile", sa.String(length=32), nullable=False, server_default="electronics_wholesale"),
    )
    op.add_column("business_settings", sa.Column("capabilities", sa.JSON(), nullable=True))
    op.add_column("business_settings", sa.Column("onboarded_at", sa.DateTime(timezone=True), nullable=True))
    # Businesses already trading keep every module they use today and skip the onboarding wizard. A database that is
    # being provisioned right now (no users or stores yet) is left un-onboarded so its first admin sees the wizard.
    bind = op.get_bind()
    trading = any(
        bind.execute(sa.select(sa.literal(1)).select_from(sa.table(name)).limit(1)).first() for name in TRADING
    )
    if trading:
        op.execute(settings.update().values(business_profile="electronics_wholesale", onboarded_at=datetime.now(UTC)))


def downgrade() -> None:
    for column in ("onboarded_at", "capabilities", "business_profile"):
        op.drop_column("business_settings", column)
