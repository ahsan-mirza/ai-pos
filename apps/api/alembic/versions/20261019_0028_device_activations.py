"""One-time register activation keys (subdomain + key -> device token).

Revision ID: 20261019_0028
Revises: 20261019_0027
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0028"
down_revision: str | None = "20261019_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "device_activations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("device_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_by_machine", sa.String(length=120), nullable=True),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"], name="fk_device_activations_device_id_devices", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_device_activations_created_by_id_users"),
        sa.UniqueConstraint("code_hash", name="uq_device_activations_code_hash"),
    )
    op.create_index("ix_device_activations_device_id", "device_activations", ["device_id"])


def downgrade() -> None:
    op.drop_index("ix_device_activations_device_id", table_name="device_activations")
    op.drop_table("device_activations")
