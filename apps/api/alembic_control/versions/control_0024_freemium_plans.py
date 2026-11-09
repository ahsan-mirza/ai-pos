"""Free, Growth, Pro AI, and Enterprise beside the existing plans, plus UAE prices.

Revision ID: control_0024
Revises: control_0023
Create Date: 2026-11-09

Lite, Standard, and Pro are not renamed or deleted. Issued invoices are not updated.
The new rows are inserted by ensure_freemium_catalog, which does nothing when they already exist.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from app.tenancy.context import CONTROL_SESSION

revision: str = "control_0024"
down_revision: str | None = "control_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_CODES = ("FREE", "GROWTH", "PRO_AI", "ENTERPRISE")


def upgrade() -> None:
    op.add_column("billing_plans", sa.Column("resource_limits", sa.JSON(), nullable=True))
    op.create_table(
        "billing_plan_prices",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("plan_id", sa.Uuid(as_uuid=True), sa.ForeignKey("billing_plans.id"), nullable=False),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("monthly_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("plan_id", "country", name="uq_billing_plan_prices_country"),
    )
    op.create_index("ix_billing_plan_prices_plan_id", "billing_plan_prices", ["plan_id"])
    from app.console.billing import ensure_freemium_catalog

    session = Session(bind=op.get_bind(), info={CONTROL_SESSION: True})
    ensure_freemium_catalog(session)
    session.flush()


def downgrade() -> None:
    op.drop_index("ix_billing_plan_prices_plan_id", table_name="billing_plan_prices")
    op.drop_table("billing_plan_prices")
    bind = op.get_bind()
    plans = sa.table("billing_plans", sa.column("id", sa.Uuid()), sa.column("code", sa.String()))
    subscriptions = sa.table("subscriptions", sa.column("plan_id", sa.Uuid()))
    kept = sa.select(subscriptions.c.plan_id)
    bind.execute(sa.delete(plans).where(plans.c.code.in_(_NEW_CODES), plans.c.id.not_in(kept)))
    op.drop_column("billing_plans", "resource_limits")
