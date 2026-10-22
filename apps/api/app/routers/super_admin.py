"""POS-company console API (no tenant): operator sign-in, tenant directory, module overrides and business-type
migrations. Every route needs an operator token except sign-in."""

import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.console import auth, directory, entitlements, migration, stats
from app.console.security import ConsoleAdmin, CurrentOperator
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.pagination import Offset, set_total
from app.schemas.console import (
    ConsoleChangeRequest,
    ConsoleLogin,
    ConsoleSession,
    CustomerRow,
    MigrationIn,
    MigrationPreflight,
    ModuleOverridesIn,
    ModuleState,
    OperatorOut,
    PreflightIn,
    ResolveIn,
    TenantDetail,
    TenantRow,
    TenantStatsOut,
    TenantUpdate,
)
from app.tenancy import registry
from app.tenancy.models import Operator

logger = logging.getLogger("ai_pos.console")
router = APIRouter()
Config = Annotated[Settings, Depends(get_settings)]

WINDOW_SECONDS = 600
MAX_ATTEMPTS = 20
_attempts: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def _throttle(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _lock:
        recent = _attempts[client]
        while recent and recent[0] < now - WINDOW_SECONDS:
            recent.popleft()
        if len(recent) >= MAX_ATTEMPTS:
            raise ApiError(429, "too_many_attempts", "Too many sign-in attempts. Wait a few minutes.")
        recent.append(now)


@router.post("/auth/login", response_model=ConsoleSession)
def login(payload: ConsoleLogin, request: Request, settings: Config) -> ConsoleSession:
    _throttle(request)
    return auth.login(settings, payload, request.client.host if request.client else None)


def _refresh(settings: Settings, tenant_id: uuid.UUID) -> None:
    """Best effort after a change: the directory shows the new modules without waiting for the daily collect."""
    try:
        stats.collect_one(settings, tenant_id)
    except Exception:
        logger.warning("Could not refresh stats for tenant %s", tenant_id, exc_info=True)


@router.get("/tenants", response_model=list[TenantRow])
def list_tenants(
    response: Response,
    operator: CurrentOperator,
    settings: Config,
    offset: Offset,
    q: Annotated[str | None, Query(max_length=80)] = None,
    status: Annotated[str | None, Query(pattern="^(active|suspended)$")] = None,
    profile: Annotated[str | None, Query(max_length=32)] = None,
    plan: Annotated[str | None, Query(max_length=32)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
) -> list[TenantRow]:
    rows, total = directory.list_tenants(
        settings, query=q, status=status, profile=profile, plan=plan, offset=offset, limit=limit
    )
    set_total(response, total)
    return rows


@router.get("/tenants/{tenant_id}/details", response_model=TenantDetail)
def tenant_details(tenant_id: uuid.UUID, operator: CurrentOperator, settings: Config) -> TenantDetail:
    return directory.details(settings, tenant_id)


@router.patch("/tenants/{tenant_id}", response_model=TenantRow)
def update_tenant(
    tenant_id: uuid.UUID, payload: TenantUpdate, operator: CurrentOperator, settings: Config
) -> TenantRow:
    """Suspends or reactivates a store, or changes its plan; suspension blocks the store's portal and registers."""
    return directory.update_tenant(settings, operator, tenant_id, payload)


@router.post("/tenants/{tenant_id}/refresh-stats", response_model=TenantStatsOut)
def refresh_stats(tenant_id: uuid.UUID, operator: CurrentOperator, settings: Config) -> TenantStatsOut:
    return stats.collect_one(settings, tenant_id)


@router.get("/tenants/{tenant_id}/customers", response_model=list[CustomerRow])
def tenant_customers(
    tenant_id: uuid.UUID,
    response: Response,
    operator: CurrentOperator,
    settings: Config,
    offset: Offset,
    reason: Annotated[str, Query(min_length=3, max_length=300)],
    reveal: bool = False,
    q: Annotated[str | None, Query(max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[CustomerRow]:
    """Break-glass view of a store's customers: needs a reason, is audited, and masks contacts unless revealed."""
    rows, total = directory.customers(
        settings, operator, tenant_id, reason=reason, reveal=reveal, query=q, offset=offset, limit=limit
    )
    set_total(response, total)
    return rows


@router.get("/change-requests", response_model=list[ConsoleChangeRequest])
def change_requests(
    operator: CurrentOperator,
    settings: Config,
    status: Annotated[str | None, Query(pattern="^(PENDING|RESOLVED|REJECTED)$")] = None,
) -> list[ConsoleChangeRequest]:
    return directory.list_requests(settings, status)


@router.post("/change-requests/{request_id}/resolve", response_model=ConsoleChangeRequest)
def resolve_request(
    request_id: uuid.UUID, payload: ResolveIn, operator: CurrentOperator, settings: Config
) -> ConsoleChangeRequest:
    return directory.close_request(settings, operator, request_id, status="RESOLVED", notes=payload.notes)


@router.post("/change-requests/{request_id}/reject", response_model=ConsoleChangeRequest)
def reject_request(
    request_id: uuid.UUID, payload: ResolveIn, operator: CurrentOperator, settings: Config
) -> ConsoleChangeRequest:
    return directory.close_request(settings, operator, request_id, status="REJECTED", notes=payload.notes)


@router.get("/tenants/{tenant_id}/modules", response_model=list[ModuleState])
def tenant_modules(tenant_id: uuid.UUID, operator: CurrentOperator, settings: Config) -> list[ModuleState]:
    with registry.control_session(settings) as control:
        tenant = entitlements.get_tenant(control, tenant_id)
    return entitlements.tenant_modules(tenant, settings)


@router.put("/tenants/{tenant_id}/modules", response_model=list[ModuleState])
def set_tenant_modules(
    tenant_id: uuid.UUID, payload: ModuleOverridesIn, operator: CurrentOperator, settings: Config
) -> list[ModuleState]:
    """Forces modules on or off for one tenant (null hands a module back to its business type); takes effect at
    once for the store's portal and API, and for registers on their next sync."""
    states = entitlements.set_overrides(settings, operator, tenant_id, payload.overrides, payload.reason.strip())
    _refresh(settings, tenant_id)
    return states


@router.post("/tenants/{tenant_id}/migrate-business-type/preflight", response_model=MigrationPreflight)
def migration_preflight(
    tenant_id: uuid.UUID, payload: PreflightIn, operator: CurrentOperator, settings: Config
) -> MigrationPreflight:
    """Dry run: modules gained and lost, what blocks the switch, what only becomes hidden, and a signed token."""
    return migration.preflight(settings, operator, tenant_id, payload.target_profile)


@router.post("/tenants/{tenant_id}/migrate-business-type", response_model=list[ModuleState])
def migrate_business_type(
    tenant_id: uuid.UUID, payload: MigrationIn, operator: ConsoleAdmin, settings: Config
) -> list[ModuleState]:
    """Switches the store's business type after a fresh preflight with no blockers (console admins only)."""
    states = migration.migrate(settings, operator, tenant_id, payload)
    _refresh(settings, tenant_id)
    return states


@router.get("/me", response_model=OperatorOut)
def me(operator: CurrentOperator, settings: Config) -> OperatorOut:
    with registry.control_session(settings) as db:
        row = db.get(Operator, operator.id)
        assert row is not None
        return auth.operator_out(row)
