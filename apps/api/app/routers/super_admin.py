"""POS-company console API (no tenant): operator sign-in, tenant directory, module overrides and business-type
migrations. Every route needs an operator token except sign-in."""

import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.console import (
    auth,
    billing,
    directory,
    entitlements,
    hardware,
    mail,
    migration,
    modules,
    site,
    stats,
    transfers,
)
from app.console.security import ConsoleAdmin, CurrentOperator
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.pagination import Offset, set_total
from app.schemas.addon_access import ConsoleAddonAccessOut
from app.schemas.billing import (
    AddonIn,
    AddonOut,
    BankAccountIn,
    BankAccountOut,
    BusinessTypeModules,
    CatalogOut,
    CycleIn,
    CycleOut,
    EntitlementLine,
    FeeIn,
    FeeOut,
    GraceIn,
    ModuleCatalogueItem,
    ModuleSummary,
    OverviewOut,
    PaymentOut,
    PlanIn,
    PlanOut,
    RejectIn,
    SubscriptionAssign,
    SubscriptionOut,
    TransferOut,
)
from app.schemas.console import (
    ConsoleChangeRequest,
    ConsoleLogin,
    ConsoleSession,
    CustomerRow,
    MigrationIn,
    MigrationPreflight,
    ModuleOverridesIn,
    ModuleState,
    OperatorCreate,
    OperatorOut,
    OperatorUpdate,
    PreflightIn,
    ResolveIn,
    TenantDetail,
    TenantRow,
    TenantStatsOut,
    TenantUpdate,
)
from app.schemas.hardware import DepositDecisionIn, FulfillmentIn, HardwareCategoryIn, HardwareItemIn
from app.schemas.mail import MailSettingsIn, MailSettingsOut, MailTestIn, MailTestOut
from app.schemas.site import SiteContactIn, SiteContactOut
from app.services import addon_access
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


@router.get("/modules", response_model=list[ModuleCatalogueItem])
def module_catalogue(_: CurrentOperator, settings: Config) -> list[ModuleCatalogueItem]:
    with registry.control_session(settings) as db:
        billing.ensure_catalog(db)
        found = modules.catalogue(db)
        db.commit()
        return found


@router.get("/modules/summary", response_model=ModuleSummary)
def module_summary(_: CurrentOperator, settings: Config) -> ModuleSummary:
    with registry.control_session(settings) as db:
        billing.ensure_catalog(db)
        found = modules.summary(db)
        db.commit()
        return found


@router.get("/modules/business-types", response_model=list[BusinessTypeModules])
def module_business_types(_: CurrentOperator) -> list[BusinessTypeModules]:
    return modules.business_types()


@router.get("/tenants/{tenant_id}/addon-access", response_model=ConsoleAddonAccessOut)
def tenant_addon_access(tenant_id: uuid.UUID, _: CurrentOperator, settings: Config) -> ConsoleAddonAccessOut:
    """Who the store has granted each paid add-on to. Read only. It does not activate a subscription."""
    with registry.control_session(settings) as control:
        tenant = entitlements.get_tenant(control, tenant_id)
    with entitlements.tenant_session(tenant, settings) as db:
        return addon_access.console_snapshot(db)


@router.get("/tenants/{tenant_id}/entitlements", response_model=list[EntitlementLine])
def tenant_entitlements(tenant_id: uuid.UUID, _: CurrentOperator, settings: Config) -> list[EntitlementLine]:
    with registry.control_session(settings) as db:
        billing.ensure_catalog(db)
        tenant = entitlements.get_tenant(db, tenant_id)
        mapped: dict[str, list[str]] = {}
        for addon in billing._addons(db):
            for key in addon.module_keys or []:
                mapped.setdefault(key, []).append(addon.code)
        db.commit()
    return modules.explain(entitlements.tenant_modules(tenant, settings), mapped)


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


@router.get("/site/contact", response_model=SiteContactOut)
def site_contact(_: CurrentOperator, settings: Config) -> SiteContactOut:
    with registry.control_session(settings) as db:
        found = site.read_contact(db)
        db.commit()
        return found


@router.patch("/site/contact", response_model=SiteContactOut)
def set_site_contact(payload: SiteContactIn, operator: ConsoleAdmin, settings: Config) -> SiteContactOut:
    with registry.control_session(settings) as db:
        return site.set_contact(db, operator, payload)


@router.get("/mail", response_model=MailSettingsOut)
def mail_settings(_: CurrentOperator, settings: Config) -> MailSettingsOut:
    with registry.control_session(settings) as db:
        found = mail.read_settings(db)
        db.commit()
        return found


@router.patch("/mail", response_model=MailSettingsOut)
def set_mail_settings(payload: MailSettingsIn, operator: ConsoleAdmin, settings: Config) -> MailSettingsOut:
    with registry.control_session(settings) as db:
        return mail.save_settings(db, settings, operator, payload)


@router.post("/mail/test", response_model=MailTestOut)
def mail_test(payload: MailTestIn, _: ConsoleAdmin, settings: Config) -> MailTestOut:
    mail.send_test(settings, payload.to)
    return MailTestOut()


@router.get("/billing/catalog", response_model=CatalogOut)
def billing_catalog(_: CurrentOperator, settings: Config) -> CatalogOut:
    with registry.control_session(settings) as db:
        found = billing.catalog(db)
        db.commit()
        return found


@router.patch("/billing/plans/{plan_id}", response_model=PlanOut)
def billing_plan(plan_id: uuid.UUID, payload: PlanIn, operator: ConsoleAdmin, settings: Config) -> PlanOut:
    with registry.control_session(settings) as db:
        return billing.update_plan(db, operator, plan_id, payload)


@router.patch("/billing/cycles/{cycle_id}", response_model=CycleOut)
def billing_cycle(cycle_id: uuid.UUID, payload: CycleIn, operator: ConsoleAdmin, settings: Config) -> CycleOut:
    with registry.control_session(settings) as db:
        return billing.update_cycle(db, operator, cycle_id, payload)


@router.patch("/billing/addons/{addon_id}", response_model=AddonOut)
def billing_addon(addon_id: uuid.UUID, payload: AddonIn, operator: ConsoleAdmin, settings: Config) -> AddonOut:
    with registry.control_session(settings) as db:
        return billing.update_addon(db, operator, addon_id, payload)


@router.patch("/billing/fees/{fee_id}", response_model=FeeOut)
def billing_fee(fee_id: uuid.UUID, payload: FeeIn, operator: ConsoleAdmin, settings: Config) -> FeeOut:
    with registry.control_session(settings) as db:
        return billing.update_fee(db, operator, fee_id, payload)


@router.get("/hardware/categories")
def hardware_categories(_: CurrentOperator, settings: Config):
    with registry.control_session(settings) as db:
        found = hardware.list_categories(db)
        db.commit()
        return found


@router.post("/hardware/categories", status_code=201)
def hardware_category_create(payload: HardwareCategoryIn, operator: ConsoleAdmin, settings: Config):
    with registry.control_session(settings) as db:
        return hardware.create_category(db, operator, payload)


@router.patch("/hardware/categories/{category_id}")
def hardware_category_update(
    category_id: uuid.UUID, payload: HardwareCategoryIn, operator: ConsoleAdmin, settings: Config
):
    with registry.control_session(settings) as db:
        return hardware.update_category(db, operator, category_id, payload)


@router.get("/hardware/items")
def hardware_items(_: CurrentOperator, settings: Config):
    with registry.control_session(settings) as db:
        found = hardware.list_items(db, include_notes=True)
        db.commit()
        return found


@router.post("/hardware/items", status_code=201)
def hardware_item_create(payload: HardwareItemIn, operator: ConsoleAdmin, settings: Config):
    with registry.control_session(settings) as db:
        return hardware.create_item(db, operator, payload)


@router.patch("/hardware/items/{item_id}")
def hardware_item_update(item_id: uuid.UUID, payload: HardwareItemIn, operator: ConsoleAdmin, settings: Config):
    with registry.control_session(settings) as db:
        return hardware.update_item(db, operator, item_id, payload)


@router.get("/hardware/orders")
def hardware_orders(
    response: Response,
    _: CurrentOperator,
    settings: Config,
    offset: Offset,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    q: str | None = None,
    payment: str | None = None,
    fulfillment: str | None = None,
):
    with registry.control_session(settings) as db:
        rows, total = hardware.list_orders(
            db, query=q, payment=payment, fulfillment=fulfillment, limit=limit, offset=offset
        )
        set_total(response, total)
        return rows


@router.get("/hardware/orders/{order_id}")
def hardware_order(order_id: uuid.UUID, _: CurrentOperator, settings: Config):
    with registry.control_session(settings) as db:
        return hardware.get_order(db, order_id)


@router.post("/hardware/orders/{order_id}/fulfill")
def hardware_fulfill(order_id: uuid.UUID, payload: FulfillmentIn, operator: ConsoleAdmin, settings: Config):
    with registry.control_session(settings) as db:
        return hardware.fulfill(db, operator, order_id, payload)


@router.post("/hardware/deposits")
def hardware_deposit(payload: DepositDecisionIn, operator: ConsoleAdmin, settings: Config) -> dict[str, str]:
    with registry.control_session(settings) as db:
        hardware.decide_deposit(db, operator, payload)
        return {"status": "saved"}


@router.get("/overview", response_model=OverviewOut)
def overview(_: CurrentOperator, settings: Config) -> OverviewOut:
    with registry.control_session(settings) as db:
        return billing.overview(db)


def _bank_out(row) -> BankAccountOut:
    return BankAccountOut(
        id=row.id,
        display_name=row.display_name,
        bank_name=row.bank_name,
        holder_name=row.holder_name,
        account_number=row.account_number,
        iban=row.iban,
        swift=row.swift,
        country=row.country,
        currency=row.currency,
        instructions=row.instructions,
        active=row.active,
    )


def _transfer_out(db, row) -> TransferOut:
    from app.tenancy.models import BillingInvoice, Tenant

    tenant = db.get(Tenant, row.tenant_id)
    invoice = db.get(BillingInvoice, row.invoice_id)
    return TransferOut(
        id=row.id,
        tenant_id=row.tenant_id,
        tenant_name=tenant.name if tenant else "",
        invoice_id=row.invoice_id,
        status=row.status,
        amount_fils=row.amount_fils,
        invoice_total_fils=invoice.total_fils if invoice else 0,
        currency=invoice.currency if invoice else "AED",
        transferred_on=row.transferred_on,
        bank_reference=row.bank_reference,
        sending_bank=row.sending_bank,
        plan_code=invoice.plan_code if invoice else "",
        cycle_code=invoice.cycle_code if invoice else "",
        tenant_slug=tenant.slug if tenant else "",
        created_at=row.created_at,
        decision_reason=row.decision_reason,
    )


@router.get("/billing/bank-accounts", response_model=list[BankAccountOut])
def bank_accounts(_: CurrentOperator, settings: Config) -> list[BankAccountOut]:
    with registry.control_session(settings) as db:
        return [_bank_out(row) for row in transfers.list_accounts(db)]


@router.post("/billing/bank-accounts", response_model=BankAccountOut, status_code=201)
def create_bank_account(payload: BankAccountIn, operator: ConsoleAdmin, settings: Config) -> BankAccountOut:
    with registry.control_session(settings) as db:
        return _bank_out(transfers.save_account(db, operator, payload.model_dump(), None))


@router.patch("/billing/bank-accounts/{account_id}", response_model=BankAccountOut)
def update_bank_account(
    account_id: uuid.UUID, payload: BankAccountIn, operator: ConsoleAdmin, settings: Config
) -> BankAccountOut:
    with registry.control_session(settings) as db:
        return _bank_out(transfers.save_account(db, operator, payload.model_dump(), account_id))


@router.get("/billing/grace")
def read_grace(_: CurrentOperator, settings: Config) -> dict[str, int]:
    with registry.control_session(settings) as db:
        return {"grace_days": transfers.grace_days(db)}


@router.put("/billing/grace")
def write_grace(payload: GraceIn, operator: ConsoleAdmin, settings: Config) -> dict[str, int]:
    with registry.control_session(settings) as db:
        return {"grace_days": transfers.set_grace_days(db, operator, payload.grace_days)}


@router.get("/billing/transfers", response_model=list[TransferOut])
def transfer_queue(_: CurrentOperator, settings: Config, status: str | None = None) -> list[TransferOut]:
    with registry.control_session(settings) as db:
        return [_transfer_out(db, row) for row in transfers.list_transfers(db, status)]


@router.get("/billing/transfers/{transfer_id}/receipt")
def transfer_receipt(transfer_id: uuid.UUID, _: CurrentOperator, settings: Config) -> Response:
    with registry.control_session(settings) as db:
        row = transfers.receipt_bytes(db, transfer_id, None)
        return Response(content=row.body, media_type=row.content_type)


@router.post("/billing/transfers/{transfer_id}/approve", response_model=PaymentOut)
def approve_transfer(transfer_id: uuid.UUID, operator: ConsoleAdmin, settings: Config) -> PaymentOut:
    with registry.control_session(settings) as db:
        payment = transfers.approve(db, operator, transfer_id, settings)
        return PaymentOut(
            id=payment.id,
            invoice_id=payment.invoice_id,
            amount_fils=payment.amount_fils,
            bank_reference=payment.bank_reference,
        )


@router.post("/billing/transfers/{transfer_id}/reject", response_model=TransferOut)
def reject_transfer(transfer_id: uuid.UUID, payload: RejectIn, operator: ConsoleAdmin, settings: Config) -> TransferOut:
    with registry.control_session(settings) as db:
        row = transfers.reject(db, operator, transfer_id, payload.reason)
        return _transfer_out(db, row)


@router.post("/billing/transfers/{transfer_id}/reopen", response_model=TransferOut)
def reopen_transfer(transfer_id: uuid.UUID, payload: RejectIn, operator: ConsoleAdmin, settings: Config) -> TransferOut:
    with registry.control_session(settings) as db:
        row = transfers.reopen(db, operator, transfer_id, payload.reason)
        return _transfer_out(db, row)


@router.post("/billing/transfers/{transfer_id}/revoke", response_model=PaymentOut)
def revoke_transfer(transfer_id: uuid.UUID, payload: RejectIn, operator: ConsoleAdmin, settings: Config) -> PaymentOut:
    with registry.control_session(settings) as db:
        payment = transfers.revoke(db, operator, settings, transfer_id, payload.reason)
        return PaymentOut(
            id=payment.id,
            invoice_id=payment.invoice_id,
            amount_fils=payment.amount_fils,
            bank_reference=payment.bank_reference,
        )


@router.get("/subscriptions", response_model=list[SubscriptionOut])
def subscriptions(_: CurrentOperator, settings: Config) -> list[SubscriptionOut]:
    with registry.control_session(settings) as db:
        return billing.list_subscriptions(db)


@router.put("/tenants/{tenant_id}/subscription", response_model=SubscriptionOut)
def assign_subscription(
    tenant_id: uuid.UUID, payload: SubscriptionAssign, operator: ConsoleAdmin, settings: Config
) -> SubscriptionOut:
    with registry.control_session(settings) as db:
        return billing.assign_subscription(db, operator, tenant_id, payload)


@router.get("/operators", response_model=list[OperatorOut])
def operators(_: ConsoleAdmin, settings: Config) -> list[OperatorOut]:
    return auth.list_operators(settings)


@router.post("/operators", response_model=OperatorOut, status_code=201)
def create_operator(payload: OperatorCreate, operator: ConsoleAdmin, settings: Config) -> OperatorOut:
    return auth.add_operator(settings, operator, payload)


@router.patch("/operators/{operator_id}", response_model=OperatorOut)
def update_operator(
    operator_id: uuid.UUID, payload: OperatorUpdate, operator: ConsoleAdmin, settings: Config
) -> OperatorOut:
    return auth.change_operator(settings, operator, operator_id, payload)


@router.get("/me", response_model=OperatorOut)
def me(operator: CurrentOperator, settings: Config) -> OperatorOut:
    with registry.control_session(settings) as db:
        row = db.get(Operator, operator.id)
        assert row is not None
        return auth.operator_out(row)
