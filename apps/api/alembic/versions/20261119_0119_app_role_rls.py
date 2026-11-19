"""Application role cannot widen tenant visibility with app.bypass_rls.

Revision ID: 20261119_0119
Revises: 20261118_0118
Create Date: 2026-11-19

Migrations still set app.bypass_rls. That setting now applies only when the
session user owns the table. The non-owner application role keeps the tenant
predicate even if it sets the same setting. Quantities are not changed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261119_0119"
down_revision: str | None = "20261118_0118"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "batch_items",
    "batch_item_events",
    "pharmacist_authorizations",
    "pharmacy_governance_officers",
    "pharmacy_recalls",
    "pharmacy_recall_lots",
    "pharmacy_supplier_returns",
    "pharmacy_supplier_return_lines",
)

OLD_POLICY = (
    "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on') "
    "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on')"
)


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _postgres():
        return
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION app_owner_may_bypass(target regclass)
            RETURNS boolean
            LANGUAGE sql
            STABLE
            AS $$
              SELECT current_setting('app.bypass_rls', true) = 'on'
                 AND session_user = pg_get_userbyid(
                      (SELECT c.relowner FROM pg_class c WHERE c.oid = target)
                    )
            $$
            """
        )
    )
    for table in TABLES:
        op.execute(sa.text(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"'))
        op.execute(
            sa.text(
                f"""
                CREATE POLICY tenant_isolation ON "{table}"
                USING (
                  tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
                  OR app_owner_may_bypass('{table}'::regclass)
                )
                WITH CHECK (
                  tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
                  OR app_owner_may_bypass('{table}'::regclass)
                )
                """
            )
        )


def downgrade() -> None:
    if not _postgres():
        return
    for table in TABLES:
        op.execute(sa.text(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"'))
        op.execute(sa.text(f'CREATE POLICY tenant_isolation ON "{table}" {OLD_POLICY}'))
    op.execute(sa.text("DROP FUNCTION IF EXISTS app_owner_may_bypass(regclass)"))
