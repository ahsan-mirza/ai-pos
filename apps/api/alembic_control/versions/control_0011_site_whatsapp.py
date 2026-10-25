"""Welcome message, label, and on/off switch for the public WhatsApp button.

Revision ID: control_0011
Revises: control_0010
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0011"
down_revision: str | None = "control_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MESSAGE = "Hello AxizPOS Sales Team! I would like to learn more about your POS solutions for my business."


def upgrade() -> None:
    op.add_column("site_settings", sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("site_settings", sa.Column("message", sa.String(500), nullable=False, server_default=_MESSAGE))
    op.add_column(
        "site_settings",
        sa.Column("tooltip", sa.String(40), nullable=False, server_default="Chat with Sales"),
    )


def downgrade() -> None:
    op.drop_column("site_settings", "tooltip")
    op.drop_column("site_settings", "message")
    op.drop_column("site_settings", "enabled")
