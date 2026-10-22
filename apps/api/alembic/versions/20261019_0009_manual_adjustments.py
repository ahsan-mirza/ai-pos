"""Manual stock adjustments: inventory:adjust_stock permission and reason codes on the ledger.

Revision ID: 20261019_0009
Revises: 20261019_0008
Create Date: 2026-10-19
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0009"
down_revision: str | None = "20261019_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION = "inventory:adjust_stock"
GRANTED_ROLES = (
    uuid.UUID("00000000-0000-4000-8000-0000000000a1"),  # Super Admin
    uuid.UUID("00000000-0000-4000-8000-0000000000a2"),  # Store Manager
)


def upgrade() -> None:
    op.add_column("stock_movements", sa.Column("reason_code", sa.String(length=40), nullable=True))
    op.alter_column(
        "stock_movements",
        "note",
        type_=sa.String(length=1000),
        existing_type=sa.String(length=255),
        existing_nullable=False,
    )
    op.create_index("ix_stock_movements_reason_code", "stock_movements", ["reason_code"])
    bind = op.get_bind()
    for role_id in GRANTED_ROLES:
        exists = bind.execute(
            sa.text("SELECT 1 FROM roles WHERE id = :id"),
            {"id": role_id},
        ).first()
        held = bind.execute(
            sa.text("SELECT 1 FROM role_permissions WHERE role_id = :id AND permission = :permission"),
            {"id": role_id, "permission": PERMISSION},
        ).first()
        if exists and not held:
            bind.execute(
                sa.text("INSERT INTO role_permissions (role_id, permission) VALUES (:id, :permission)"),
                {"id": role_id, "permission": PERMISSION},
            )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM role_permissions WHERE permission = :permission").bindparams(permission=PERMISSION))
    op.drop_index("ix_stock_movements_reason_code", table_name="stock_movements")
    op.drop_column("stock_movements", "reason_code")
    op.execute("UPDATE stock_movements SET note = left(note, 255)")
    op.alter_column(
        "stock_movements",
        "note",
        type_=sa.String(length=255),
        existing_type=sa.String(length=1000),
        existing_nullable=False,
    )
