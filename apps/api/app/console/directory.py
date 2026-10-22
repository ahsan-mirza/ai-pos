"""The console's tenant directory, tenant detail, status changes, break-glass customer view, and the change-request
queue. The directory reads only the control database; tenant databases are opened for detail and customers."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.console import stats as tenant_stats
from app.console.entitlements import get_tenant, module_states, tenant_modules, tenant_session
from app.console.security import OperatorPrincipal, audit_operator
from app.core import capabilities as catalog
from app.core.config import Settings
from app.core.errors import ApiError
from app.core.pagination import count_rows
from app.models.customer import Customer
from app.schemas.console import (
    ConsoleChangeRequest,
    CustomerRow,
    OperatorAuditOut,
    TenantDetail,
    TenantRow,
    TenantUpdate,
)
from app.tenancy import change_requests, registry
from app.tenancy.models import Operator, OperatorAuditLog, Tenant, TenantChangeRequest, TenantStats


def _domain(slug: str, settings: Settings) -> str:
    base = settings.tenant_domain_list[0] if settings.tenant_domain_list else "qios.ae"
    return f"{slug}.{base}"


def tenant_row(tenant: Tenant, stats: TenantStats | None, pending: int, settings: Settings) -> TenantRow:
    return TenantRow(
        id=tenant.id,
        slug=tenant.slug,
        name=tenant.name,
        domain=_domain(tenant.slug, settings),
        status=tenant.status,  # type: ignore[arg-type]
        business_profile=tenant.profile,
        profile_label=catalog.PROFILE_LABELS.get(tenant.profile, tenant.profile),
        plan=tenant.plan or "standard",
        owner_email=tenant.owner_email,
        created_at=tenant.created_at,
        stats=tenant_stats.stats_out(stats),
        pending_requests=pending,
    )


def _pending_counts(control: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ids:
        return {}
    rows = control.execute(
        select(TenantChangeRequest.tenant_id, func.count(TenantChangeRequest.id))
        .where(TenantChangeRequest.tenant_id.in_(ids), TenantChangeRequest.status == "PENDING")
        .group_by(TenantChangeRequest.tenant_id)
    ).all()
    return {row[0]: int(row[1]) for row in rows}


def list_tenants(
    settings: Settings,
    *,
    query: str | None,
    status: str | None,
    profile: str | None,
    plan: str | None,
    offset: int,
    limit: int,
) -> tuple[list[TenantRow], int]:
    with registry.control_session(settings) as control:
        statement = select(Tenant, TenantStats).outerjoin(TenantStats, TenantStats.tenant_id == Tenant.id)
        if query:
            needle = f"%{query.strip().lower()}%"
            statement = statement.where(
                or_(
                    func.lower(Tenant.name).like(needle),
                    func.lower(Tenant.slug).like(needle),
                    func.lower(func.coalesce(Tenant.owner_email, "")).like(needle),
                )
            )
        if status:
            statement = statement.where(Tenant.status == status)
        if profile:
            statement = statement.where(Tenant.profile == profile)
        if plan:
            statement = statement.where(Tenant.plan == plan)
        total = count_rows(control, statement)
        rows = control.execute(statement.order_by(Tenant.created_at.desc()).offset(offset).limit(limit)).all()
        pending = _pending_counts(control, [tenant.id for tenant, _ in rows])
        return [tenant_row(tenant, stats, pending.get(tenant.id, 0), settings) for tenant, stats in rows], total


def _audit_rows(control: Session, tenant_id: uuid.UUID) -> list[OperatorAuditOut]:
    rows = control.execute(
        select(OperatorAuditLog, Operator.email)
        .outerjoin(Operator, Operator.id == OperatorAuditLog.operator_id)
        .where(OperatorAuditLog.tenant_id == tenant_id)
        .order_by(OperatorAuditLog.created_at.desc())
        .limit(50)
    ).all()
    return [
        OperatorAuditOut(
            id=row.id,
            operator_email=email,
            action=row.action,
            before=row.before,
            after=row.after,
            reason=row.reason,
            created_at=row.created_at,
        )
        for row, email in rows
    ]


def details(settings: Settings, tenant_id: uuid.UUID) -> TenantDetail:
    with registry.control_session(settings) as control:
        tenant = get_tenant(control, tenant_id)
        unreachable = None
        try:
            modules = tenant_modules(tenant, settings)
        except Exception as error:  # the store's database is down: show the last snapshot instead
            snapshot = control.get(TenantStats, tenant.id)
            enabled = list(snapshot.enabled_modules) if snapshot else []
            modules = module_states(tenant.profile, enabled, {})
            unreachable = type(error).__name__
        requests = control.scalars(
            select(TenantChangeRequest)
            .where(TenantChangeRequest.tenant_id == tenant.id)
            .order_by(TenantChangeRequest.created_at.desc())
            .limit(20)
        ).all()
        pending = sum(1 for request in requests if request.status == "PENDING")
        return TenantDetail(
            tenant=tenant_row(tenant, control.get(TenantStats, tenant.id), pending, settings),
            modules=modules,
            change_requests=[change_requests.out(request) for request in requests],
            audit=_audit_rows(control, tenant.id),
            unreachable=unreachable,
        )


def update_tenant(
    settings: Settings, operator: OperatorPrincipal, tenant_id: uuid.UUID, data: TenantUpdate
) -> TenantRow:
    with registry.control_session(settings) as control:
        tenant = get_tenant(control, tenant_id)
        before = {"status": tenant.status, "plan": tenant.plan, "owner_email": tenant.owner_email}
        if data.status is not None:
            tenant.status = data.status
        if data.plan is not None:
            tenant.plan = data.plan.strip()
        if "owner_email" in data.model_fields_set:
            tenant.owner_email = (data.owner_email or "").strip().lower() or None
        after = {"status": tenant.status, "plan": tenant.plan, "owner_email": tenant.owner_email}
        audit_operator(
            control, operator, "tenant.update", tenant_id=tenant.id, before=before, after=after, reason=data.reason
        )
        control.commit()
        registry.invalidate(tenant.slug)
        pending = _pending_counts(control, [tenant.id]).get(tenant.id, 0)
        return tenant_row(tenant, control.get(TenantStats, tenant.id), pending, settings)


def _mask_phone(value: str | None) -> str | None:
    if not value:
        return value
    return f"{value[:4]}•••{value[-3:]}" if len(value) > 7 else "•••"


def _mask_email(value: str | None) -> str | None:
    if not value or "@" not in value:
        return value
    name, _, domain = value.partition("@")
    return f"{name[:2]}•••@{domain}"


def customers(
    settings: Settings,
    operator: OperatorPrincipal,
    tenant_id: uuid.UUID,
    *,
    reason: str,
    reveal: bool,
    query: str | None,
    offset: int,
    limit: int,
) -> tuple[list[CustomerRow], int]:
    """Break-glass: a store's customer records are personal data, so every look is audited with its reason and
    contacts stay masked unless a console admin reveals them."""
    if len(reason.strip()) < 3:
        raise ApiError(422, "reason_required", "Say why you need to see this store's customers.")
    if reveal and not operator.is_admin:
        raise ApiError(403, "forbidden", "Only a console admin can reveal customer contacts.")
    with registry.control_session(settings) as control:
        tenant = get_tenant(control, tenant_id)
        with tenant_session(tenant, settings) as db:
            statement = select(Customer).where(Customer.is_sample.is_(False))
            if query:
                needle = f"%{query.strip().lower()}%"
                statement = statement.where(
                    or_(func.lower(Customer.name).like(needle), func.lower(Customer.code).like(needle))
                )
            total = count_rows(db, statement)
            found = db.scalars(statement.order_by(Customer.name).offset(offset).limit(limit)).all()
            rows = [
                CustomerRow(
                    id=customer.id,
                    name=customer.name,
                    phone=customer.phone if reveal else _mask_phone(customer.phone),
                    email=customer.email if reveal else _mask_email(customer.email),
                    customer_type=customer.customer_type,
                    balance_cents=customer.current_balance_cents,
                    created_at=customer.created_at,
                )
                for customer in found
            ]
        audit_operator(
            control,
            operator,
            "tenant.customers_viewed",
            tenant_id=tenant.id,
            after={"reveal": reveal, "query": query, "offset": offset, "rows": len(rows)},
            reason=reason.strip(),
        )
        control.commit()
        return rows, total


# --- Change-request queue -------------------------------------------------------------------------------------


def _queue_row(request: TenantChangeRequest, tenant: Tenant) -> ConsoleChangeRequest:
    return ConsoleChangeRequest(
        **change_requests.out(request).model_dump(), tenant_slug=tenant.slug, tenant_name=tenant.name
    )


def list_requests(settings: Settings, status: str | None) -> list[ConsoleChangeRequest]:
    with registry.control_session(settings) as control:
        statement = select(TenantChangeRequest, Tenant).join(Tenant, Tenant.id == TenantChangeRequest.tenant_id)
        if status:
            statement = statement.where(TenantChangeRequest.status == status)
        rows = control.execute(statement.order_by(TenantChangeRequest.created_at.desc()).limit(200)).all()
        return [_queue_row(request, tenant) for request, tenant in rows]


def close_request(
    settings: Settings, operator: OperatorPrincipal, request_id: uuid.UUID, *, status: str, notes: str
) -> ConsoleChangeRequest:
    with registry.control_session(settings) as control:
        request = control.get(TenantChangeRequest, request_id)
        if request is None:
            raise ApiError(404, "not_found", "Change request was not found.")
        if request.status != "PENDING":
            raise ApiError(409, "already_closed", "This request is already closed.")
        request.status = status
        request.resolution_notes = notes.strip()
        request.resolved_by_operator_id = operator.id
        request.resolved_at = datetime.now(UTC)
        audit_operator(
            control,
            operator,
            f"change_request.{status.lower()}",
            tenant_id=request.tenant_id,
            after={"request": str(request.id), "kind": request.kind, "value": request.requested_value},
            reason=notes.strip(),
        )
        control.commit()
        tenant = control.get(Tenant, request.tenant_id)
        assert tenant is not None
        return _queue_row(request, tenant)
