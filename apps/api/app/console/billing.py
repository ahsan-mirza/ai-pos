"""Packages, billing cycles and add-ons the POS company edits, and the quote a store pays to go live.

Prices live in the control database. A checkout stores the fils it charged, so a later price edit does not
rewrite an old invoice. The cycle discount applies to recurring amounts only. Deposits and the onboarding fee
stay at their face value.
"""

import calendar
import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.console.entitlements import get_tenant, tenant_session
from app.console.security import OperatorPrincipal, audit_operator
from app.core import capabilities as capability_catalog
from app.core.config import Settings
from app.core.deps import Principal
from app.core.errors import ApiError
from app.models.user import User
from app.schemas.billing import (
    AddonIn,
    AddonOut,
    AddonQty,
    CatalogOut,
    CheckoutIn,
    CheckoutOut,
    CheckoutStatus,
    CycleIn,
    CycleOut,
    FeeIn,
    FeeOut,
    OverviewOut,
    PlanIn,
    PlanOut,
    PlanRevenue,
    QuoteLine,
    QuoteOut,
    StatusCount,
    SubscriptionAssign,
    SubscriptionOut,
)
from app.schemas.onboarding import GoLiveRequest
from app.services.onboarding_service import go_live
from app.tenancy import registry
from app.tenancy.context import use_tenant
from app.tenancy.models import (
    BillingAddon,
    BillingCycle,
    BillingFee,
    BillingInvoice,
    BillingInvoiceLine,
    BillingPlan,
    Subscription,
    SubscriptionItem,
    Tenant,
    TenantChangeRequest,
    TenantStats,
)

_PLANS = (
    ("LITE", "Lite", 1, ["promotions", "loyalty"], 14_900, 14, 1),
    ("STANDARD", "Standard", 3, ["promotions", "loyalty", "card_terminals", "quotes_layaway"], 29_900, 14, 2),
    (
        "PRO",
        "Pro",
        8,
        ["promotions", "loyalty", "card_terminals", "bnpl", "gift_cards", "kds", "tables"],
        49_900,
        30,
        3,
    ),
)
_CYCLES = (
    ("MONTHLY", "Monthly", 1, 0, 1),
    ("QUARTERLY", "Quarterly", 3, 500, 2),
    ("HALF_YEARLY", "Half-Yearly", 6, 1_200, 3),
    ("ANNUAL", "Annual", 12, 2_500, 4),
)
_ADDONS = (
    (
        "hardware_lease",
        "Hardware lease",
        "Register hardware, rented. The one-time amount is a refundable deposit.",
        15_000,
        50_000,
        True,
        1,
    ),
    ("equipment_protection", "Equipment protection", "Covers leased hardware.", 3_900, 0, False, 2),
    (
        "extra_register",
        "Extra register",
        "A register beyond the ones included in the package.",
        4_900,
        0,
        False,
        3,
    ),
)


def require_module_keys(keys: list[str], *, with_dependencies: bool) -> list[str]:
    """Keeps stored module ids inside the registered capability catalogue."""
    known = {capability.value for capability in capability_catalog.Capability}
    cleaned: list[str] = []
    for key in keys:
        if key not in known:
            raise ApiError(422, "unknown_module", f"{key} is not a registered module.")
        if key not in cleaned:
            cleaned.append(key)
    if with_dependencies:
        chosen = capability_catalog.parse(cleaned)
        missing = capability_catalog.missing_dependencies(chosen)
        if missing:
            parts = [
                f"{capability.value} needs {', '.join(need.value for need in needs)}"
                for capability, needs in missing.items()
            ]
            detail = "; ".join(parts)
            raise ApiError(422, "capability_dependencies", f"Include the modules these depend on: {detail}.")
    return [capability.value for capability in capability_catalog.parse(cleaned)]


def cycle_amount(monthly_fils: int, months: int, discount_bps: int) -> int:
    """Recurring price for one quantity over the whole cycle, after the company's discount."""
    if months < 1 or not 0 <= discount_bps <= 10_000 or monthly_fils < 0:
        raise ApiError(422, "invalid_price", "A price, a cycle length, or a discount is out of range.")
    return monthly_fils * months * (10_000 - discount_bps) // 10_000


# Descriptions match the capability catalogue. The monthly price stays 0 until the console sets it.
_MODULE_DESCRIPTIONS: dict[str, str] = {
    "wholesale_pricing": "Retail/wholesale toggle at the register, price tiers and volume breaks.",
    "quotes_layaway": "Proforma quotes, items held for a customer with a deposit, and layaway pickups.",
    "multi_currency": "Accept cash in other currencies at live exchange rates.",
    "serial_tracking": "Scan and trace individual units by IMEI or serial number.",
    "variants_matrix": "Create and sell product grids by size, colour and style.",
    "consignment": "Sell supplier-owned stock and settle what sold.",
    "fefo": "Sell the batch that expires soonest first, with expiry alerts.",
    "b2b_credit": "On-account sales, credit limits, statements and collections.",
    "cheques": "Take cheques and post-dated cheques and track their clearing.",
    "repairs": "Repair tickets, technician workflow and parts.",
    "tables": "Seat guests, track table status and move or merge tables.",
    "split_bills": "Split a bill by item, seat or amount.",
    "tips_service_charge": "Add tips and an automatic service charge to bills.",
    "delivery_channels": "Orders from delivery apps alongside walk-in sales.",
    "sales_orders": "Wholesale orders picked, delivered in parts with proof of delivery, and invoiced per delivery.",
    "card_terminals": (
        "Send the amount to the card machine and confirm the payment automatically; refunds go back to the card."
    ),
    "bnpl": "Instalment checkout at the till on the customer's phone, captured and refunded through the provider.",
    "gift_cards": "Sell gift cards at the till and accept them as payment at every branch.",
    "tax_free": "Issue tax-free forms to tourists and report the refunds in VAT box 2.",
    "alterations": "Alteration tickets with measurements, due dates and a ready-for-collection message.",
    "online_store": "Web-store orders (Shopify or any shop) reserve stock and are shipped or collected in store.",
    "deep_analytics": "Sales, margin, inventory, and the reports for this business type.",
    "axiz_reach": (
        "Marketing campaigns across WhatsApp, SMS, and email. Provider setup and receipts stay in the starter kit."
    ),
    "uae_einvoicing": "UAE e-invoicing for in-scope business and government sales. The price is set in the console.",
    "fashion_rental": "Rent catalogue items for a period, with deposits, returns and a booking calendar.",
}


def optional_module_capabilities() -> list[capability_catalog.Capability]:
    """Capabilities that at least one business type may buy. Starter modules are not in this list for that type."""
    seen: set[capability_catalog.Capability] = set()
    for profile in capability_catalog.PROFILES:
        seen.update(capability_catalog.catalogue(profile).optional)
    return [capability for capability in capability_catalog.ORDER if capability in seen]


def addon_module_keys(capability: capability_catalog.Capability) -> list[str]:
    """The module this add-on sells, plus the modules it requires."""
    keys = [capability.value]
    for required in capability_catalog.SPECS[capability].requires:
        if required.value not in keys:
            keys.append(required.value)
    return keys


def ensure_module_addons(db: Session) -> None:
    """Inserts a catalog add-on for each optional module. A row the console already edited is left as it is."""
    existing = {row.code for row in _addons(db)}
    now = datetime.now(UTC)
    order = 100
    for capability in optional_module_capabilities():
        code = capability.value
        if code not in existing:
            spec = capability_catalog.SPECS[capability]
            db.add(
                BillingAddon(
                    code=code,
                    name=spec.label[:80],
                    description=_MODULE_DESCRIPTIONS.get(code, spec.label),
                    monthly_fils=0,
                    one_time_fils=0,
                    refundable=False,
                    active=True,
                    module_keys=addon_module_keys(capability),
                    sort_order=order,
                    updated_at=now,
                )
            )
        order += 1
    db.flush()


def ensure_catalog(db: Session) -> bool:
    """Inserts the starting catalog once. Later edits in the console are left alone."""
    if db.scalar(select(BillingPlan.id).limit(1)) is not None:
        return False
    now = datetime.now(UTC)
    for code, name, registers, modules, monthly, trial, order in _PLANS:
        db.add(
            BillingPlan(
                code=code,
                name=name,
                included_registers=registers,
                included_modules=modules,
                monthly_fils=monthly,
                trial_days=trial,
                sort_order=order,
                updated_at=now,
            )
        )
    for code, name, months, discount, order in _CYCLES:
        db.add(
            BillingCycle(
                code=code, name=name, months=months, discount_bps=discount, sort_order=order, updated_at=now
            )
        )
    for code, name, description, monthly, once, refundable, order in _ADDONS:
        db.add(
            BillingAddon(
                code=code,
                name=name,
                description=description,
                monthly_fils=monthly,
                one_time_fils=once,
                refundable=refundable,
                sort_order=order,
                updated_at=now,
            )
        )
    db.add(BillingFee(code="onboarding", name="Onboarding", amount_fils=25_000, updated_at=now))
    db.flush()
    return True


def start_trial(db: Session, tenant: Tenant) -> None:
    """Gives a new store the Standard monthly trial. No-op when a subscription already exists."""
    ensure_catalog(db)
    if db.scalar(select(Subscription.id).where(Subscription.tenant_id == tenant.id)) is not None:
        return
    plan = db.scalar(select(BillingPlan).where(BillingPlan.code == "STANDARD"))
    cycle = db.scalar(select(BillingCycle).where(BillingCycle.code == "MONTHLY"))
    if plan is None or cycle is None:
        return
    db.add(
        Subscription(
            tenant_id=tenant.id,
            plan_id=plan.id,
            cycle_id=cycle.id,
            status="trialing",
            trial_ends_at=datetime.now(UTC) + timedelta(days=plan.trial_days),
        )
    )
    tenant.plan = plan.code
    tenant.practice_mode = True
    db.flush()


def _plans(db: Session) -> list[BillingPlan]:
    return list(db.scalars(select(BillingPlan).order_by(BillingPlan.sort_order, BillingPlan.code)))


def _cycles(db: Session) -> list[BillingCycle]:
    return list(db.scalars(select(BillingCycle).order_by(BillingCycle.sort_order, BillingCycle.code)))


def _addons(db: Session) -> list[BillingAddon]:
    return list(db.scalars(select(BillingAddon).order_by(BillingAddon.sort_order, BillingAddon.code)))


def _fees(db: Session) -> list[BillingFee]:
    return list(db.scalars(select(BillingFee).order_by(BillingFee.code)))


def plan_out(row: BillingPlan) -> PlanOut:
    return PlanOut(
        id=row.id,
        code=row.code,
        name=row.name,
        included_registers=row.included_registers,
        included_modules=list(row.included_modules or []),
        monthly_fils=row.monthly_fils,
        trial_days=row.trial_days,
        active=row.active,
        sort_order=row.sort_order,
    )


def cycle_out(row: BillingCycle) -> CycleOut:
    return CycleOut(
        id=row.id,
        code=row.code,
        name=row.name,
        months=row.months,
        discount_bps=row.discount_bps,
        active=row.active,
        sort_order=row.sort_order,
    )


def addon_out(row: BillingAddon) -> AddonOut:
    from app.console.addon_listing import listing_out
    from app.schemas.billing import AddonPricePoint

    history = []
    for point in row.price_history or []:
        if isinstance(point, dict):
            history.append(
                AddonPricePoint(
                    monthly_fils=int(point.get("monthly_fils") or 0),
                    one_time_fils=int(point.get("one_time_fils") or 0),
                    refundable=bool(point.get("refundable")),
                    effective_at=str(point.get("effective_at") or ""),
                    reason=str(point.get("reason") or ""),
                )
            )
    return AddonOut(
        id=row.id,
        code=row.code,
        name=row.name,
        description=row.description,
        monthly_fils=row.monthly_fils,
        one_time_fils=row.one_time_fils,
        refundable=row.refundable,
        active=row.active,
        module_keys=list(row.module_keys or []),
        sort_order=row.sort_order,
        listing=listing_out(row.listing),
        price_history=history,
        updated_at=row.updated_at,
    )


def fee_out(row: BillingFee) -> FeeOut:
    return FeeOut(id=row.id, code=row.code, name=row.name, amount_fils=row.amount_fils, active=row.active)


def catalog(db: Session) -> CatalogOut:
    ensure_catalog(db)
    ensure_module_addons(db)
    from app.console.addon_listing import fill_listings

    fill_listings(db)
    from app.console import hardware

    return CatalogOut(
        plans=[plan_out(row) for row in _plans(db)],
        cycles=[cycle_out(row) for row in _cycles(db)],
        addons=[addon_out(row) for row in _addons(db)],
        fees=[fee_out(row) for row in _fees(db)],
        hardware=hardware.list_items(db, sellable_only=True),
    )


def plan_names(db: Session) -> dict[str, str]:
    if ensure_catalog(db):
        db.commit()
    return {row.code.lower(): row.name for row in _plans(db)}


def _touch(row: BillingPlan | BillingCycle | BillingAddon | BillingFee) -> None:
    row.updated_at = datetime.now(UTC)


def _audit_price(
    db: Session, operator: OperatorPrincipal, action: str, before: dict, after: dict, reason: str | None
) -> None:
    audit_operator(db, operator, action, before=before, after=after, reason=reason)


def update_plan(db: Session, operator: OperatorPrincipal, plan_id: uuid.UUID, data: PlanIn) -> PlanOut:
    ensure_catalog(db)
    row = db.get(BillingPlan, plan_id)
    if row is None:
        raise ApiError(404, "not_found", "Package was not found.")
    before = plan_out(row).model_dump(mode="json")
    row.name = data.name.strip()
    row.included_registers = data.included_registers
    row.included_modules = require_module_keys(data.included_modules, with_dependencies=False)
    row.monthly_fils = data.monthly_fils
    row.trial_days = data.trial_days
    row.active = data.active
    row.sort_order = data.sort_order
    _touch(row)
    _audit_price(db, operator, "billing.plan", before, plan_out(row).model_dump(mode="json"), data.reason)
    db.commit()
    return plan_out(row)


def update_cycle(db: Session, operator: OperatorPrincipal, cycle_id: uuid.UUID, data: CycleIn) -> CycleOut:
    ensure_catalog(db)
    row = db.get(BillingCycle, cycle_id)
    if row is None:
        raise ApiError(404, "not_found", "Billing cycle was not found.")
    before = cycle_out(row).model_dump(mode="json")
    row.name = data.name.strip()
    row.months = data.months
    row.discount_bps = data.discount_bps
    row.active = data.active
    row.sort_order = data.sort_order
    _touch(row)
    _audit_price(db, operator, "billing.cycle", before, cycle_out(row).model_dump(mode="json"), data.reason)
    db.commit()
    return cycle_out(row)


def update_addon(db: Session, operator: OperatorPrincipal, addon_id: uuid.UUID, data: AddonIn) -> AddonOut:
    ensure_catalog(db)
    row = db.get(BillingAddon, addon_id)
    if row is None:
        raise ApiError(404, "not_found", "Add-on was not found.")
    before = addon_out(row).model_dump(mode="json")
    price_changed = row.monthly_fils != data.monthly_fils or row.one_time_fils != data.one_time_fils
    price_changed = price_changed or row.refundable != data.refundable
    if price_changed:
        history = list(row.price_history or [])
        history.append(
            {
                "monthly_fils": row.monthly_fils,
                "one_time_fils": row.one_time_fils,
                "refundable": row.refundable,
                "effective_at": datetime.now(UTC).isoformat(),
                "reason": data.reason.strip(),
            }
        )
        row.price_history = history[-20:]
    row.name = data.name.strip()
    row.description = data.description.strip()
    row.monthly_fils = data.monthly_fils
    row.one_time_fils = data.one_time_fils
    row.refundable = data.refundable
    row.active = data.active
    row.module_keys = require_module_keys(data.module_keys, with_dependencies=True)
    row.sort_order = data.sort_order
    if data.listing is not None:
        from app.console.addon_listing import normalize_listing

        stored = normalize_listing(data.listing.model_dump(), customized=True)
        if stored["publication"] == "published":
            row.active = True
        elif stored["publication"] in {"draft", "archived"}:
            row.active = False
        row.listing = stored
    _touch(row)
    _audit_price(db, operator, "billing.addon", before, addon_out(row).model_dump(mode="json"), data.reason)
    db.commit()
    return addon_out(row)


def update_fee(db: Session, operator: OperatorPrincipal, fee_id: uuid.UUID, data: FeeIn) -> FeeOut:
    ensure_catalog(db)
    row = db.get(BillingFee, fee_id)
    if row is None:
        raise ApiError(404, "not_found", "Fee was not found.")
    before = fee_out(row).model_dump(mode="json")
    row.name = data.name.strip()
    row.amount_fils = data.amount_fils
    row.active = data.active
    _touch(row)
    _audit_price(db, operator, "billing.fee", before, fee_out(row).model_dump(mode="json"), data.reason)
    db.commit()
    return fee_out(row)


def _active_plan(db: Session, code: str) -> BillingPlan:
    row = db.scalar(select(BillingPlan).where(BillingPlan.code == code.strip().upper(), BillingPlan.active.is_(True)))
    if row is None:
        raise ApiError(422, "unknown_plan", "Choose an active package.")
    return row


def _active_cycle(db: Session, code: str) -> BillingCycle:
    row = db.scalar(
        select(BillingCycle).where(BillingCycle.code == code.strip().upper(), BillingCycle.active.is_(True))
    )
    if row is None:
        raise ApiError(422, "unknown_cycle", "Choose an active billing cycle.")
    return row


def quote_for(
    db: Session,
    plan_code: str,
    cycle_code: str,
    addons: list[AddonQty],
    hardware: list | None = None,
    stores: dict | None = None,
) -> QuoteOut:
    ensure_catalog(db)
    plan = _active_plan(db, plan_code)
    cycle = _active_cycle(db, cycle_code)
    by_code = {row.code: row for row in _addons(db) if row.active}
    lines: list[QuoteLine] = []
    plan_unit = cycle_amount(plan.monthly_fils, cycle.months, cycle.discount_bps)
    lines.append(
        QuoteLine(
            code=plan.code,
            label=f"{plan.name} · {cycle.name}",
            quantity=1,
            unit_fils=plan_unit,
            amount_fils=plan_unit,
            recurring=True,
            refundable=False,
        )
    )
    seen: set[str] = set()
    for item in addons:
        if item.quantity <= 0:
            continue
        if item.code in seen:
            raise ApiError(422, "duplicate_addon", "Each add-on can be chosen once.")
        seen.add(item.code)
        addon = by_code.get(item.code)
        if addon is None:
            raise ApiError(422, "unknown_addon", f"{item.code} is not an active add-on.")
        if addon.monthly_fils:
            unit = cycle_amount(addon.monthly_fils, cycle.months, cycle.discount_bps)
            lines.append(
                QuoteLine(
                    code=addon.code,
                    label=addon.name,
                    quantity=item.quantity,
                    unit_fils=unit,
                    amount_fils=unit * item.quantity,
                    recurring=True,
                    refundable=False,
                )
            )
        if addon.one_time_fils:
            lines.append(
                QuoteLine(
                    code=f"{addon.code}_once",
                    label=f"{addon.name} deposit" if addon.refundable else addon.name,
                    quantity=item.quantity,
                    unit_fils=addon.one_time_fils,
                    amount_fils=addon.one_time_fils * item.quantity,
                    recurring=False,
                    refundable=addon.refundable,
                )
            )
    for fee in _fees(db):
        if fee.active and fee.amount_fils:
            lines.append(
                QuoteLine(
                    code=fee.code,
                    label=fee.name,
                    quantity=1,
                    unit_fils=fee.amount_fils,
                    amount_fils=fee.amount_fils,
                    recurring=False,
                    refundable=False,
                )
            )
    from app.console import hardware as hardware_catalog

    hardware_lines, hardware_monthly, deposit = hardware_catalog.price_selection(
        db,
        list(hardware or []),
        months=cycle.months,
        discount_bps=cycle.discount_bps,
        included_registers=plan.included_registers,
        stores=stores,
    )
    lines.extend(hardware_lines)
    recurring = sum(line.amount_fils for line in lines if line.recurring)
    once = sum(line.amount_fils for line in lines if not line.recurring)
    return QuoteOut(
        plan_code=plan.code,
        plan_name=plan.name,
        cycle_code=cycle.code,
        cycle_name=cycle.name,
        months=cycle.months,
        discount_bps=cycle.discount_bps,
        included_registers=plan.included_registers,
        lines=lines,
        recurring_fils=recurring,
        one_time_fils=once,
        total_fils=recurring + once,
        hardware_monthly_fils=hardware_monthly,
        deposit_fils=deposit,
    )


def subscription_out(db: Session, tenant: Tenant) -> SubscriptionOut | None:
    ensure_catalog(db)
    row = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id))
    if row is None:
        return None
    plan = db.get(BillingPlan, row.plan_id)
    cycle = db.get(BillingCycle, row.cycle_id)
    if plan is None or cycle is None:
        return None
    items = list(db.scalars(select(SubscriptionItem).where(SubscriptionItem.subscription_id == row.id)))
    chosen = [AddonQty(code=item.addon_code, quantity=item.quantity) for item in items]
    try:
        priced = quote_for(db, plan.code, cycle.code, chosen)
        nxt = priced.recurring_fils
    except ApiError:
        nxt = 0
    return SubscriptionOut(
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        tenant_slug=tenant.slug,
        plan_code=plan.code,
        plan_name=plan.name,
        cycle_code=cycle.code,
        cycle_name=cycle.name,
        status=row.status,  # type: ignore[arg-type]
        trial_ends_at=row.trial_ends_at,
        current_period_end=row.current_period_end,
        practice_mode=tenant.practice_mode,
        next_recurring_fils=nxt,
        addons=chosen,
    )


def add_calendar_months(start: datetime, months: int) -> datetime:
    """Moves a timestamp forward by calendar months. 31 January plus one month is 28 or 29 February."""
    if months < 1:
        return start
    index = start.month - 1 + months
    year = start.year + index // 12
    month = index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return start.replace(year=year, month=month, day=day)


def _monthly_equivalent(monthly_fils: int, months: int, discount_bps: int) -> int:
    """The billed cycle, spread across its months. Same integer rule as `cycle_amount`."""
    if months < 1:
        return 0
    return cycle_amount(monthly_fils, months, discount_bps) // months


def overview(db: Session) -> OverviewOut:
    """Control-plane health. Trialing subscriptions are counted, and they are not included in MRR."""
    now = datetime.now(UTC)
    soon = now + timedelta(days=14)
    tenants = db.scalar(select(func.count()).select_from(Tenant)) or 0
    active_tenants = db.scalar(select(func.count()).select_from(Tenant).where(Tenant.status == "active")) or 0
    suspended = db.scalar(select(func.count()).select_from(Tenant).where(Tenant.status == "suspended")) or 0
    practice = db.scalar(select(func.count()).select_from(Tenant).where(Tenant.practice_mode.is_(True))) or 0
    cutoff = now - timedelta(days=30)
    recent = db.scalar(select(func.count()).select_from(Tenant).where(Tenant.created_at >= cutoff)) or 0
    stores = db.scalar(select(func.coalesce(func.sum(TenantStats.stores), 0))) or 0
    registers = db.scalar(select(func.coalesce(func.sum(TenantStats.registers), 0))) or 0
    unpaid = db.scalar(
        select(func.coalesce(func.sum(BillingInvoice.total_fils), 0)).where(BillingInvoice.status == "pending")
    ) or 0
    unpaid_count = db.scalar(
        select(func.count()).select_from(BillingInvoice).where(BillingInvoice.status == "pending")
    ) or 0
    open_requests = db.scalar(
        select(func.count()).select_from(TenantChangeRequest).where(TenantChangeRequest.status == "PENDING")
    ) or 0

    rows = db.execute(
        select(Subscription, BillingPlan, BillingCycle).join(BillingPlan, BillingPlan.id == Subscription.plan_id).join(
            BillingCycle, BillingCycle.id == Subscription.cycle_id
        )
    ).all()
    item_rows = list(db.scalars(select(SubscriptionItem)))
    addons = {row.code: row for row in db.scalars(select(BillingAddon))}
    by_sub: dict[uuid.UUID, list[SubscriptionItem]] = {}
    for item in item_rows:
        by_sub.setdefault(item.subscription_id, []).append(item)

    counts: dict[str, int] = {status: 0 for status in ("trialing", "active", "past_due", "canceled")}
    plans: dict[str, PlanRevenue] = {}
    mrr = 0
    ending = 0
    for subscription, plan, cycle in rows:
        counts[subscription.status] = counts.get(subscription.status, 0) + 1
        if (
            subscription.status == "trialing"
            and subscription.trial_ends_at is not None
            and now <= subscription.trial_ends_at <= soon
        ):
            ending += 1
        if subscription.status not in ("active", "past_due"):
            continue
        monthly = plan.monthly_fils
        for item in by_sub.get(subscription.id, []):
            addon = addons.get(item.addon_code)
            if addon is not None:
                monthly += addon.monthly_fils * item.quantity
        share = _monthly_equivalent(monthly, cycle.months, cycle.discount_bps)
        mrr += share
        bucket = plans.get(plan.code)
        if bucket is None:
            plans[plan.code] = PlanRevenue(
                plan_code=plan.code, plan_name=plan.name, paying_tenants=1, mrr_fils=share
            )
        else:
            plans[plan.code] = bucket.model_copy(
                update={"paying_tenants": bucket.paying_tenants + 1, "mrr_fils": bucket.mrr_fils + share}
            )

    return OverviewOut(
        tenants=int(tenants),
        active_tenants=int(active_tenants),
        suspended_tenants=int(suspended),
        practice_tenants=int(practice),
        new_tenants_30d=int(recent),
        stores=int(stores),
        registers=int(registers),
        paying_subscriptions=counts.get("active", 0),
        trialing=counts.get("trialing", 0),
        trials_ending_14d=ending,
        past_due=counts.get("past_due", 0),
        canceled=counts.get("canceled", 0),
        mrr_fils=mrr,
        arr_fils=mrr * 12,
        unpaid_checkouts_fils=int(unpaid),
        unpaid_checkouts=int(unpaid_count),
        open_change_requests=int(open_requests),
        by_status=[StatusCount(status=status, tenants=count) for status, count in counts.items()],
        by_plan=sorted(plans.values(), key=lambda row: row.plan_name.lower()),
        definitions=[
            "MRR is the monthly equivalent of active and past-due subscriptions, after the billing-cycle discount.",
            "Trials are excluded from MRR until they convert.",
            "One-time fees and refundable deposits are excluded from MRR.",
            "ARR is MRR times 12. It is not a separate contract value.",
            "Unpaid checkouts are pending go-live invoices, not a general receivables ledger.",
            "Store and register counts come from the last collected tenant stats.",
        ],
    )


def list_subscriptions(db: Session) -> list[SubscriptionOut]:
    if ensure_catalog(db):
        db.commit()
    rows = list(db.scalars(select(Subscription)))
    if not rows:
        return []
    ids = [item.tenant_id for item in rows]
    tenants = {row.id: row for row in db.scalars(select(Tenant).where(Tenant.id.in_(ids)))}
    found: list[SubscriptionOut] = []
    for row in rows:
        tenant = tenants.get(row.tenant_id)
        if tenant is None:
            continue
        item = subscription_out(db, tenant)
        if item is not None:
            found.append(item)
    return sorted(found, key=lambda item: item.tenant_name.lower())


def assign_subscription(
    db: Session, operator: OperatorPrincipal, tenant_id: uuid.UUID, data: SubscriptionAssign
) -> SubscriptionOut:
    ensure_catalog(db)
    tenant = get_tenant(db, tenant_id)
    plan = _active_plan(db, data.plan_code)
    cycle = _active_cycle(db, data.cycle_code)
    row = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id))
    before = {"plan": tenant.plan, "status": row.status if row else None}
    if row is None:
        row = Subscription(tenant_id=tenant.id, plan_id=plan.id, cycle_id=cycle.id, status="trialing")
        db.add(row)
        db.flush()
    else:
        row.plan_id = plan.id
        row.cycle_id = cycle.id
    if row.status == "trialing":
        row.trial_ends_at = datetime.now(UTC) + timedelta(days=plan.trial_days)
    tenant.plan = plan.code
    db.execute(delete(SubscriptionItem).where(SubscriptionItem.subscription_id == row.id))
    for item in data.addons:
        if item.quantity > 0:
            db.add(SubscriptionItem(subscription_id=row.id, addon_code=item.code, quantity=item.quantity))
    after = subscription_out(db, tenant)
    audit_operator(
        db,
        operator,
        "billing.assign",
        tenant_id=tenant.id,
        before=before,
        after=after.model_dump(mode="json") if after else None,
        reason=data.reason,
    )
    db.commit()
    if after is None:
        raise ApiError(500, "subscription_missing", "The subscription could not be saved.")
    return after


def _snapshot_lines(db: Session, invoice_id: uuid.UUID, quote: QuoteOut) -> None:
    for line in quote.lines:
        db.add(
            BillingInvoiceLine(
                invoice_id=invoice_id,
                code=line.code,
                label=line.label,
                quantity=line.quantity,
                unit_fils=line.unit_fils,
                amount_fils=line.amount_fils,
                recurring=line.recurring,
                refundable=line.refundable,
            )
        )


def _stripe_configured(settings: Settings) -> bool:
    return bool((settings.stripe_secret_key or "").strip())


def _business_profile(settings: Settings, tenant: Tenant) -> str:
    from app.services.settings_service import load_settings

    with tenant_session(tenant, settings) as store:
        return load_settings(store).business_profile or tenant.profile


def quote_addon(db: Session, settings: Settings, tenant: Tenant, code: str) -> QuoteOut:
    """The current cycle's price for one module add-on. No package line and no onboarding fee."""
    ensure_catalog(db)
    ensure_module_addons(db)
    addon = db.scalar(select(BillingAddon).where(BillingAddon.code == code, BillingAddon.active.is_(True)))
    if addon is None or not (addon.module_keys or []):
        raise ApiError(422, "unknown_addon", "Choose a module add-on.")
    if int(addon.monthly_fils or 0) <= 0:
        raise ApiError(422, "price_not_set", "This add-on does not have a price yet.")
    subscription = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id))
    if subscription is None:
        raise ApiError(409, "no_subscription", "Choose a package before buying an add-on.")
    plan = db.get(BillingPlan, subscription.plan_id)
    cycle = db.get(BillingCycle, subscription.cycle_id)
    if plan is None or cycle is None:
        raise ApiError(422, "catalog_missing", "The current package is missing.")
    profile = _business_profile(settings, tenant)
    optional = {capability.value for capability in capability_catalog.catalogue(profile).optional}
    if code not in optional:
        raise ApiError(422, "module_not_optional", "This module is not an add-on for this business type.")
    unit = cycle_amount(addon.monthly_fils, cycle.months, cycle.discount_bps)
    if unit <= 0:
        raise ApiError(422, "price_not_set", "This add-on does not have a price yet.")
    return QuoteOut(
        currency="AED",
        plan_code=plan.code,
        plan_name=plan.name,
        cycle_code=cycle.code,
        cycle_name=cycle.name,
        months=cycle.months,
        discount_bps=cycle.discount_bps,
        included_registers=plan.included_registers,
        lines=[
            QuoteLine(
                code=addon.code,
                label=addon.name,
                quantity=1,
                unit_fils=unit,
                amount_fils=unit,
                recurring=True,
                refundable=False,
            )
        ],
        recurring_fils=unit,
        one_time_fils=0,
        total_fils=unit,
    )


def _open_addon_invoice(db: Session, tenant_id: uuid.UUID, code: str) -> BillingInvoice | None:
    invoices = db.scalars(
        select(BillingInvoice).where(BillingInvoice.tenant_id == tenant_id, BillingInvoice.status == "pending")
    )
    for invoice in invoices:
        line = db.scalar(
            select(BillingInvoiceLine.id).where(
                BillingInvoiceLine.invoice_id == invoice.id, BillingInvoiceLine.code == code
            )
        )
        if line is not None:
            return invoice
    return None


def _checkout_from_invoice(db: Session, invoice: BillingInvoice) -> CheckoutOut:
    plan = db.scalar(select(BillingPlan).where(BillingPlan.code == invoice.plan_code))
    cycle = db.scalar(select(BillingCycle).where(BillingCycle.code == invoice.cycle_code))
    lines = list(db.scalars(select(BillingInvoiceLine).where(BillingInvoiceLine.invoice_id == invoice.id)))
    quote = QuoteOut(
        currency=invoice.currency,
        plan_code=invoice.plan_code,
        plan_name=plan.name if plan is not None else invoice.plan_code,
        cycle_code=invoice.cycle_code,
        cycle_name=cycle.name if cycle is not None else invoice.cycle_code,
        months=cycle.months if cycle is not None else 1,
        discount_bps=cycle.discount_bps if cycle is not None else 0,
        included_registers=plan.included_registers if plan is not None else 0,
        lines=[
            QuoteLine(
                code=line.code,
                label=line.label,
                quantity=line.quantity,
                unit_fils=line.unit_fils,
                amount_fils=line.amount_fils,
                recurring=line.recurring,
                refundable=line.refundable,
            )
            for line in lines
        ],
        recurring_fils=invoice.recurring_fils,
        one_time_fils=invoice.one_time_fils,
        total_fils=invoice.total_fils,
    )
    return CheckoutOut(checkout_id=invoice.id, mode="transfer", url=None, quote=quote, bank=invoice.bank_snapshot)


def create_addon_checkout(
    db: Session, settings: Settings, tenant: Tenant, actor_id: uuid.UUID, code: str
) -> CheckoutOut:
    """Issues an invoice for one module add-on. Payment uses the same bank-transfer review as a package."""
    existing = _open_addon_invoice(db, tenant.id, code)
    if existing is not None:
        return _checkout_from_invoice(db, existing)
    subscription = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id))
    if subscription is not None:
        held = db.scalar(
            select(SubscriptionItem.id).where(
                SubscriptionItem.subscription_id == subscription.id,
                SubscriptionItem.addon_code == code,
                SubscriptionItem.quantity > 0,
            )
        )
        if held is not None:
            raise ApiError(409, "already_subscribed", "This add-on is already on the subscription.")
    priced = quote_addon(db, settings, tenant, code)
    invoice = BillingInvoice(
        tenant_id=tenant.id,
        status="pending",
        currency=priced.currency,
        plan_code=priced.plan_code,
        cycle_code=priced.cycle_code,
        recurring_fils=priced.recurring_fils,
        one_time_fils=priced.one_time_fils,
        total_fils=priced.total_fils,
        purge="keep",
        actor_user_id=actor_id,
        confirm_name=(tenant.name or "Add-on")[:120],
    )
    db.add(invoice)
    db.flush()
    _snapshot_lines(db, invoice.id, priced)
    from app.console import transfers

    invoice.bank_snapshot = transfers.active_bank_snapshot(db)
    if invoice.bank_snapshot is None:
        raise ApiError(422, "bank_not_configured", "Bank transfer details have not been published yet.")
    db.commit()
    return CheckoutOut(checkout_id=invoice.id, mode="transfer", url=None, quote=priced, bank=invoice.bank_snapshot)


def create_checkout(
    db: Session,
    settings: Settings,
    tenant: Tenant,
    actor_id: uuid.UUID,
    data: CheckoutIn,
    stores: dict | None = None,
) -> CheckoutOut:
    if not data.tax_acknowledged:
        raise ApiError(422, "tax_not_acknowledged", "Confirm that practice tax stamps will be removed.")
    if data.mode == "keep" and data.opening_stock not in ("keep", "reset"):
        raise ApiError(422, "opening_stock_required", "Choose whether to keep opening stock or reset it to zero.")
    priced = quote_for(db, data.plan_code, data.cycle_code, data.addons, data.hardware, stores)
    if priced.recurring_fils <= 0:
        raise ApiError(422, "nothing_to_bill", "The package has no recurring price.")
    invoice = BillingInvoice(
        tenant_id=tenant.id,
        status="pending",
        currency=priced.currency,
        plan_code=priced.plan_code,
        cycle_code=priced.cycle_code,
        recurring_fils=priced.recurring_fils,
        one_time_fils=priced.one_time_fils,
        total_fils=priced.total_fils,
        purge=data.mode,
        opening_stock=data.opening_stock,
        actor_user_id=actor_id,
        confirm_name=data.confirm.strip(),
    )
    db.add(invoice)
    db.flush()
    _snapshot_lines(db, invoice.id, priced)
    from app.console import hardware as hardware_catalog

    hardware_catalog.open_order(
        db, tenant_id=tenant.id, invoice_id=invoice.id, picks=list(data.hardware), stores=stores
    )
    from app.console import transfers

    invoice.bank_snapshot = transfers.active_bank_snapshot(db)
    if data.payment == "transfer":
        if invoice.bank_snapshot is None:
            raise ApiError(422, "bank_not_configured", "Bank transfer details have not been published yet.")
        db.commit()
        return CheckoutOut(checkout_id=invoice.id, mode="transfer", url=None, quote=priced, bank=invoice.bank_snapshot)
    mode = "stripe" if _stripe_configured(settings) else "simulator"
    url = _stripe_session(settings, invoice, priced) if mode == "stripe" else None
    db.commit()
    return CheckoutOut(checkout_id=invoice.id, mode=mode, url=url, quote=priced)  # type: ignore[arg-type]


def _stripe_session(settings: Settings, invoice: BillingInvoice, quote: QuoteOut) -> str:
    base = settings.public_base_url.rstrip("/")
    form: list[tuple[str, str]] = [
        ("mode", "subscription"),
        ("success_url", f"{base}/api/v1/billing/checkout/return?checkout_id={invoice.id}"),
        ("cancel_url", f"{base}/api/v1/billing/checkout/return?checkout_id={invoice.id}&canceled=1"),
        ("client_reference_id", str(invoice.id)),
        ("metadata[checkout_id]", str(invoice.id)),
        ("line_items[0][quantity]", "1"),
        ("line_items[0][price_data][currency]", "aed"),
        ("line_items[0][price_data][unit_amount]", str(quote.recurring_fils)),
        ("line_items[0][price_data][recurring][interval]", "month"),
        ("line_items[0][price_data][recurring][interval_count]", str(quote.months)),
        ("line_items[0][price_data][product_data][name]", f"{quote.plan_name} ({quote.cycle_name})"),
    ]
    if quote.one_time_fils:
        form.extend(
            [
                ("line_items[1][quantity]", "1"),
                ("line_items[1][price_data][currency]", "aed"),
                ("line_items[1][price_data][unit_amount]", str(quote.one_time_fils)),
                ("line_items[1][price_data][product_data][name]", "Deposit and onboarding"),
            ]
        )
    try:
        response = httpx.post(
            "https://api.stripe.com/v1/checkout/sessions",
            data=form,
            auth=((settings.stripe_secret_key or "").strip(), ""),
            timeout=20,
        )
    except httpx.HTTPError as exc:
        raise ApiError(502, "stripe_unavailable", "The payment service could not be reached.") from exc
    payload = response.json()
    if response.status_code >= 400 or not payload.get("url"):
        raise ApiError(502, "stripe_rejected", "The payment service refused the checkout.")
    invoice.stripe_session_id = str(payload.get("id") or "") or None
    return str(payload["url"])


def checkout_status(db: Session, tenant_id: uuid.UUID, checkout_id: uuid.UUID) -> CheckoutStatus:
    row = db.get(BillingInvoice, checkout_id)
    if row is None or row.tenant_id != tenant_id:
        raise ApiError(404, "not_found", "Checkout was not found.")
    return CheckoutStatus(
        checkout_id=row.id,
        status=row.status,  # type: ignore[arg-type]
        error=row.error,
        result=row.result,
        total_fils=row.total_fils,
        currency=row.currency,
        bank=row.bank_snapshot,
    )


def simulate_checkout(db: Session, settings: Settings, tenant_id: uuid.UUID, checkout_id: uuid.UUID) -> CheckoutStatus:
    if _stripe_configured(settings):
        raise ApiError(409, "stripe_required", "This server takes payment through Stripe.")
    row = db.get(BillingInvoice, checkout_id)
    if row is None or row.tenant_id != tenant_id:
        raise ApiError(404, "not_found", "Checkout was not found.")
    _complete(db, settings, row)
    db.commit()
    from app.console.entitlements import publish_purchased

    publish_purchased(settings, tenant_id)
    return checkout_status(db, tenant_id, checkout_id)


def verify_stripe_signature(body: bytes, header: str, secret: str) -> bool:
    parts = {}
    signatures: list[str] = []
    for piece in header.split(","):
        key, _, value = piece.partition("=")
        if key == "t":
            parts["t"] = value
        elif key == "v1":
            signatures.append(value)
    timestamp = parts.get("t")
    if not timestamp or not signatures:
        return False
    signed = f"{timestamp}.".encode() + body
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, item) for item in signatures)


def complete_stripe_event(db: Session, settings: Settings, payload: dict) -> uuid.UUID | None:
    if payload.get("type") != "checkout.session.completed":
        return None
    session = payload.get("data", {}).get("object", {})
    checkout_id = (session.get("metadata") or {}).get("checkout_id") or session.get("client_reference_id")
    if not checkout_id:
        return None
    try:
        invoice_id = uuid.UUID(str(checkout_id))
    except ValueError:
        return None
    row = db.get(BillingInvoice, invoice_id)
    if row is None:
        return None
    customer = session.get("customer")
    subscription = session.get("subscription")
    if isinstance(customer, str):
        _remember_stripe(db, row, customer, subscription if isinstance(subscription, str) else None)
    _complete(db, settings, row)
    return row.tenant_id


def _remember_stripe(db: Session, invoice: BillingInvoice, customer: str, subscription: str | None) -> None:
    row = db.scalar(select(Subscription).where(Subscription.tenant_id == invoice.tenant_id))
    if row is None:
        return
    row.stripe_customer_id = customer
    if subscription:
        row.stripe_subscription_id = subscription


def _complete(db: Session, settings: Settings, invoice: BillingInvoice) -> None:
    if invoice.status == "paid":
        return
    tenant = db.get(Tenant, invoice.tenant_id)
    if tenant is None or invoice.actor_user_id is None:
        invoice.status = "failed"
        invoice.error = "The store or the owner who started checkout is missing."
        return
    payload = GoLiveRequest(
        confirm=invoice.confirm_name,
        mode=invoice.purge,  # type: ignore[arg-type]
        opening_stock=invoice.opening_stock,  # type: ignore[arg-type]
        tax_acknowledged=True,
    )
    try:
        ref = registry.ref_for(tenant, settings)
        with tenant_session(tenant, settings) as store, use_tenant(ref):
            user = store.get(User, invoice.actor_user_id)
            if user is None:
                raise ApiError(422, "owner_missing", "The owner who started checkout no longer exists.")
            principal = Principal(kind="user", scope="portal", user=user, permissions=frozenset(user.permissions))
            result = go_live(store, principal, payload, settings=settings, payment_verified=True)
    except ApiError as exc:
        if exc.code != "already_live":
            invoice.error = exc.message
            invoice.status = "failed"
            return
        result = None
    invoice.status = "paid"
    invoice.paid_at = datetime.now(UTC)
    invoice.error = None
    if result is not None:
        invoice.result = result.model_dump(mode="json")
    tenant.practice_mode = False
    tenant.plan = invoice.plan_code
    _activate(db, tenant, invoice)
    from app.console import hardware as hardware_catalog

    hardware_catalog.mark_paid(db, invoice.id)


def _addon_lines(lines: list[BillingInvoiceLine], plan_code: str, cycle_code: str) -> list[BillingInvoiceLine]:
    return [
        line
        for line in lines
        if line.recurring and line.code not in {plan_code, cycle_code} and line.quantity > 0
    ]


def _append_addon_items(db: Session, subscription_id: uuid.UUID, lines: list[BillingInvoiceLine]) -> None:
    existing = {
        item.addon_code: item
        for item in db.scalars(select(SubscriptionItem).where(SubscriptionItem.subscription_id == subscription_id))
    }
    for line in lines:
        current = existing.get(line.code)
        if current is None:
            db.add(SubscriptionItem(subscription_id=subscription_id, addon_code=line.code, quantity=line.quantity))
        else:
            current.quantity = line.quantity


def _activate(db: Session, tenant: Tenant, invoice: BillingInvoice) -> None:
    plan = db.scalar(select(BillingPlan).where(BillingPlan.code == invoice.plan_code))
    cycle = db.scalar(select(BillingCycle).where(BillingCycle.code == invoice.cycle_code))
    if plan is None or cycle is None:
        raise ApiError(422, "catalog_missing", f"Missing {invoice.plan_code}/{invoice.cycle_code}.")
    lines = list(db.scalars(select(BillingInvoiceLine).where(BillingInvoiceLine.invoice_id == invoice.id)))
    row = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id))
    # A module purchase has no package line. It is added to the subscription the store already has.
    if not any(line.code == plan.code for line in lines):
        if row is None:
            raise ApiError(409, "no_subscription", "Choose a package before buying an add-on.")
        invoice.subscription_id = row.id
        _append_addon_items(db, row.id, _addon_lines(lines, plan.code, cycle.code))
        return
    if row is None:
        row = Subscription(tenant_id=tenant.id, plan_id=plan.id, cycle_id=cycle.id)
        db.add(row)
        db.flush()
    row.plan_id = plan.id
    row.cycle_id = cycle.id
    row.status = "active"
    now = datetime.now(UTC)
    end = row.current_period_end
    if end is not None and end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    base = end if end is not None and end > now else now
    row.current_period_end = add_calendar_months(base, cycle.months)
    invoice.subscription_id = row.id
    db.execute(delete(SubscriptionItem).where(SubscriptionItem.subscription_id == row.id))
    for line in _addon_lines(lines, plan.code, cycle.code):
        db.add(SubscriptionItem(subscription_id=row.id, addon_code=line.code, quantity=line.quantity))
