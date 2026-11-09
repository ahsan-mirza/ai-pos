"""Resource caps stored on the plan. Legacy plans have none. A null value is not a cap."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.tenancy.context import current_tenant

_LABELS = {
    "branches": "branches",
    "registers": "registers",
    "staff": "staff accounts",
    "products": "products",
    "customers": "customers",
}


def limit_value(resource: str) -> int | None:
    """The cap for the tenant bound to this call. None means the plan does not enforce it."""
    tenant = current_tenant()
    settings = get_settings()
    if tenant is None or not settings.tenancy_enabled:
        return None
    from app.tenancy import registry

    with registry.control_session(settings) as control:
        from app.console.promotional_trial import effective_limits

        limits = effective_limits(control, uuid.UUID(str(tenant.id)))
        if not limits or resource not in limits or limits.get(resource) is None:
            return None
        return int(limits[resource])


def assert_room(used: int, resource: str) -> None:
    """Blocks another row once `used` has reached the plan cap. Existing rows stay."""
    cap = limit_value(resource)
    if cap is None or used < cap:
        return
    label = _LABELS.get(resource, resource)
    raise ApiError(
        409,
        "plan_limit",
        f"This plan includes {cap} {label}. Existing records stay available.",
    )


def history_cutoff() -> datetime | None:
    """Sales older than this stay stored. List views for a capped plan start here."""
    days = limit_value("sales_history_days")
    if days is None:
        return None
    return datetime.now(UTC) - timedelta(days=days)


def count_of(db: Session, model: type) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)
