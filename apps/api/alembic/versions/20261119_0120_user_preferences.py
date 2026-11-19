"""Per-cashier product catalogue view.

Revision ID: 20261119_0120
Revises: 20261119_0119
Create Date: 2026-11-19

One row per tenant, user, and preference key. The only key is the catalogue
view. Tenant isolation matches the policy introduced in 20261119_0119.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261119_0120"
down_revision: str | None = "20261119_0119"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLICY = """
USING (
  tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  OR app_owner_may_bypass('user_preferences'::regclass)
)
WITH CHECK (
  tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  OR app_owner_may_bypass('user_preferences'::regclass)
)
"""


def _rls(table: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))  # noqa: TID251
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))  # noqa: TID251
    op.execute(sa.text(f'CREATE POLICY tenant_isolation ON "{table}" {POLICY}'))  # noqa: TID251


def _drop_rls(table: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"'))  # noqa: TID251
    op.execute(sa.text(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY'))  # noqa: TID251
    op.execute(sa.text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))  # noqa: TID251


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("preference_key", sa.String(length=64), nullable=False),
        sa.Column("preference_value", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "preference_key = 'product_catalogue_view'",
            name="ck_user_preferences_catalogue_key",
        ),
        sa.CheckConstraint(
            "preference_value IN ('grid', 'list', 'compact')",
            name="ck_user_preferences_catalogue_value",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_preferences_user_id_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_preferences"),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "preference_key",
            name="uq_user_preferences_user_key",
        ),
    )
    op.create_index("ix_user_preferences_tenant_id", "user_preferences", ["tenant_id"])
    op.create_index("ix_user_preferences_user_id", "user_preferences", ["user_id"])
    _rls("user_preferences")


def downgrade() -> None:
    _drop_rls("user_preferences")
    op.drop_index("ix_user_preferences_user_id", table_name="user_preferences")
    op.drop_index("ix_user_preferences_tenant_id", table_name="user_preferences")
    op.drop_table("user_preferences")
