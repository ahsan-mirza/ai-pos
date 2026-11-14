"""EC machine fields and Pay by Card on unchanged package seeds.

Revision ID: control_0030
Revises: control_0029
Create Date: 2026-11-14

Existing hardware stays untyped. Free and Enterprise package lists are not rewritten.
A package an administrator already edited is left alone.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from app.tenancy.context import CONTROL_SESSION

revision: str = "control_0030"
down_revision: str | None = "control_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("hardware_items", sa.Column("device_type", sa.String(length=16), nullable=False, server_default=""))
    op.add_column("hardware_items", sa.Column("warranty_months", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("hardware_items", sa.Column("specifications", sa.JSON(), nullable=True))
    op.add_column("hardware_items", sa.Column("installation_fils", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(
        "hardware_order_lines", sa.Column("device_type", sa.String(length=16), nullable=False, server_default="")
    )
    op.add_column(
        "hardware_order_lines", sa.Column("warranty_months", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "hardware_order_lines", sa.Column("installation_fils", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "hardware_assignments", sa.Column("device_type", sa.String(length=16), nullable=False, server_default="")
    )
    op.add_column(
        "hardware_assignments",
        sa.Column("registration_status", sa.String(length=24), nullable=False, server_default="pending"),
    )
    op.add_column("hardware_assignments", sa.Column("warranty_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("hardware_assignments", sa.Column("warranty_end", sa.DateTime(timezone=True), nullable=True))
    from app.console.billing import grant_card_terminals_where_seed_unchanged

    session = Session(bind=op.get_bind(), info={CONTROL_SESSION: True})
    grant_card_terminals_where_seed_unchanged(session)
    session.flush()


def downgrade() -> None:
    op.drop_column("hardware_assignments", "warranty_end")
    op.drop_column("hardware_assignments", "warranty_start")
    op.drop_column("hardware_assignments", "registration_status")
    op.drop_column("hardware_assignments", "device_type")
    op.drop_column("hardware_order_lines", "installation_fils")
    op.drop_column("hardware_order_lines", "warranty_months")
    op.drop_column("hardware_order_lines", "device_type")
    op.drop_column("hardware_items", "installation_fils")
    op.drop_column("hardware_items", "specifications")
    op.drop_column("hardware_items", "warranty_months")
    op.drop_column("hardware_items", "device_type")
