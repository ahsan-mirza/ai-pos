"""First published modules for Growth and Pro AI.

An empty list is the untouched seed. A list the console already saved, including a deliberate empty list
applied after this revision, is not rewritten. Downgrade removes only that same seed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0028"
down_revision: str | None = "control_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEED = {
    "GROWTH": '["sales_insights"]',
    "PRO_AI": '["sales_insights", "ai_insights", "deep_analytics"]',
}


def upgrade() -> None:
    for code, modules in _SEED.items():
        op.execute(
            sa.text(
                "UPDATE billing_plans SET included_modules = CAST(:modules AS JSON) "
                "WHERE code = :code AND (included_modules IS NULL OR included_modules::text IN ('[]', 'null'))"
            ).bindparams(modules=modules, code=code)
        )


def downgrade() -> None:
    for code, modules in _SEED.items():
        op.execute(
            sa.text(
                "UPDATE billing_plans SET included_modules = CAST('[]' AS JSON) "
                "WHERE code = :code AND included_modules::text = :modules"
            ).bindparams(code=code, modules=modules)
        )
