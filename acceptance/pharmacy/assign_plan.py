"""Point the disposable pharmacy tenant at the existing Pro AI plan.

Free allows 2 staff and 1 branch. Pro AI is an existing catalog plan with room for
the acceptance users and a second store. This does not change plan prices or caps.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

API = Path(__file__).resolve().parents[2] / "apps" / "api"
sys.path.insert(0, str(API))
os.environ["APP_ENV"] = "acceptance"

from sqlalchemy import select

from app.console.billing import ensure_catalog
from app.core.config import get_settings
from app.tenancy import registry
from app.tenancy.models import BillingPlan, Subscription, Tenant


def main() -> None:
    for key in ("DATABASE_URL", "CONTROL_DATABASE_URL"):
        if os.environ.get(key):
            raise SystemExit(f"{key} is set in the process. Refusing to assign a plan.")
    settings = get_settings()
    if settings.app_env != "acceptance":
        raise SystemExit("Refusing to assign a plan outside the acceptance environment.")
    with registry.control_session(settings) as db:
        ensure_catalog(db)
        plan = db.scalar(select(BillingPlan).where(BillingPlan.code == "PRO_AI", BillingPlan.active.is_(True)))
        if plan is None:
            raise SystemExit("The Pro AI plan is missing.")
        assigned = []
        for slug in ("pharmacy-accept", "pharmacy-accept-b"):
            tenant = db.scalar(select(Tenant).where(Tenant.slug == slug))
            if tenant is None:
                raise SystemExit(f"The acceptance tenant {slug} is missing.")
            subscription = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id))
            if subscription is None:
                raise SystemExit(f"{slug} has no subscription.")
            subscription.plan_id = plan.id
            subscription.status = "active"
            subscription.current_period_end = datetime.now(UTC) + timedelta(days=30)
            tenant.plan = plan.code
            assigned.append(slug)
        db.commit()
    print("acceptance plan=PRO_AI tenants=" + ",".join(assigned))


if __name__ == "__main__":
    main()
