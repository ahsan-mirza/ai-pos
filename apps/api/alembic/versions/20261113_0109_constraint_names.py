"""Rename doubled check constraints and index the fulfillment order list.

Revision ID: 20261113_0109
Revises: 20261112_0108
Create Date: 2026-11-13

Fleet-only deployment stays at 20261112_0107. This revision follows payroll.
Downgrade drops the new index and leaves canonical constraint names in place,
so a later downgrade of 20261112_0107 can find ck_sales_orders_scheduling_status.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.models.base import canonical_check_name

revision: str = "20261113_0109"
down_revision: str | None = "20261112_0108"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "ix_sales_orders_store_status_created"


def _rename_doubled_checks() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    for table in inspector.get_table_names():
        checks = inspector.get_check_constraints(table)
        present = {item.get("name") for item in checks}
        for check in checks:
            current = check.get("name") or ""
            target = canonical_check_name(current)
            if target is None or target in present or not current.replace("_", "").isalnum():
                continue
            op.execute(f'ALTER TABLE "{table}" RENAME CONSTRAINT "{current}" TO "{target}"')
            present.add(target)


def _order_list_index(*, present: bool) -> None:
    """The migration fixture's sales_orders stub predates store and status columns."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "sales_orders" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("sales_orders")}
    if not {"store_id", "status", "created_at", "id"}.issubset(columns):
        return
    indexes = {item["name"] for item in inspector.get_indexes("sales_orders")}
    if present and _INDEX not in indexes:
        op.create_index(_INDEX, "sales_orders", ["store_id", "status", "created_at", "id"])
    if not present and _INDEX in indexes:
        op.drop_index(_INDEX, table_name="sales_orders")


def upgrade() -> None:
    _rename_doubled_checks()
    _order_list_index(present=True)


def downgrade() -> None:
    _order_list_index(present=False)
