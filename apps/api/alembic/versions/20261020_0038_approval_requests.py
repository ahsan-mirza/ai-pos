"""Remote manager approval requests.

Revision ID: 20261020_0038
Revises: 20261020_0037
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261020_0038"
down_revision: str | None = "20261020_0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False, index=True),
        sa.Column("permission", sa.String(64), nullable=False),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=True, index=True),
        sa.Column("device_id", sa.Uuid(as_uuid=True), sa.ForeignKey("devices.id"), nullable=True),
        sa.Column("requested_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="PENDING", index=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(250), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("approval_requests")
