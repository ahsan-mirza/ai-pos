"""The add-on catalogue is the registered capability list, priced through the existing billing add-ons.

Editing a mapping does not turn a module on for a store. Access still comes from the business type, the store's
own selection, a verified subscription for that add-on, and a console override. A commercial add-on records which
modules it is allowed to sell; payment verification is what grants them.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.console.billing import _addons, _plans
from app.console.payment_notices import pending_count
from app.core import capabilities as catalog
from app.schemas.billing import BusinessTypeModules, EntitlementLine, ModuleCatalogueItem, ModuleSummary
from app.schemas.console import ModuleState
from app.tenancy.models import Subscription, SubscriptionItem


def catalogue(db: Session) -> list[ModuleCatalogueItem]:
    from app.console.billing import ensure_module_addons

    ensure_module_addons(db)
    plans = _plans(db)
    addons = _addons(db)
    rows: list[ModuleCatalogueItem] = []
    for capability in catalog.ORDER:
        spec = catalog.SPECS[capability]
        key = capability.value
        rows.append(
            ModuleCatalogueItem(
                key=key,
                label=spec.label,
                available=spec.available,
                requires=[item.value for item in spec.requires],
                business_types=sorted(
                    profile for profile, allowed in catalog.COMPATIBLE.items() if capability in allowed
                ),
                preset_for=sorted(profile for profile, preset in catalog.PROFILES.items() if capability in preset),
                plan_codes=[plan.code for plan in plans if key in (plan.included_modules or [])],
                addon_codes=[addon.code for addon in addons if key in (addon.module_keys or [])],
            )
        )
    return rows


def business_types() -> list[BusinessTypeModules]:
    return [
        BusinessTypeModules(
            key=profile,
            label=catalog.PROFILE_LABELS.get(profile, profile),
            preset=[capability.value for capability in preset],
            eligible=[capability.value for capability in catalog.compatible(profile)],
        )
        for profile, preset in catalog.PROFILES.items()
    ]


def summary(db: Session) -> ModuleSummary:
    from app.console.billing import ensure_module_addons

    ensure_module_addons(db)
    addons = _addons(db)
    counts = dict(
        db.execute(select(Subscription.status, func.count()).group_by(Subscription.status)).all()
    )
    items = list(db.scalars(select(SubscriptionItem)))
    active_ids = {
        row.id
        for row in db.scalars(select(Subscription).where(Subscription.status == "active"))
    }
    by_code = {row.code: row for row in addons}
    addon_mrr = 0
    for item in items:
        addon = by_code.get(item.addon_code)
        if item.subscription_id in active_ids and addon is not None and addon.active:
            addon_mrr += addon.monthly_fils * item.quantity
    pending = pending_count(db)
    implemented = sum(1 for capability in catalog.ORDER if catalog.SPECS[capability].available)
    return ModuleSummary(
        catalogue_total=len(catalog.ORDER),
        implemented=implemented,
        not_implemented=len(catalog.ORDER) - implemented,
        active_addons=sum(1 for row in addons if row.active),
        mapped_addons=sum(1 for row in addons if row.module_keys),
        active_subscriptions=int(counts.get("active", 0)),
        trialing_subscriptions=int(counts.get("trialing", 0)),
        past_due_subscriptions=int(counts.get("past_due", 0)),
        canceled_subscriptions=int(counts.get("canceled", 0)),
        pending_payments=int(pending or 0),
        addon_mrr_fils=addon_mrr,
    )


def explain(states: list[ModuleState], addon_codes: dict[str, list[str]]) -> list[EntitlementLine]:
    lines: list[EntitlementLine] = []
    for state in states:
        if not state.available:
            reason = "Not implemented. The catalogue entry does not enable it."
        elif state.override == "off":
            reason = "Restricted by a console override."
        elif state.override == "on":
            reason = "Granted by a console override."
        elif not state.fits_type:
            reason = "Unsupported for this business type. The subscription record is left unchanged."
        elif state.enabled:
            reason = "Included in the business type or selected for this store."
        else:
            reason = "Not selected for this store."
        mapped = addon_codes.get(state.key, [])
        if mapped and state.override != "on":
            joined = ", ".join(mapped)
            reason = f"{reason} Commercial add-on {joined} maps this module and does not turn it on by itself."
        lines.append(
            EntitlementLine(
                key=state.key,
                label=state.label,
                enabled=state.enabled,
                available=state.available,
                fits_type=state.fits_type,
                reason=reason,
                override=state.override,
                addon_codes=mapped,
            )
        )
    return lines
