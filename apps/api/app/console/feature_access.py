"""Which published plan or add-on a capability needs.

The console plan rows and add-on rows are the commercial record. This module does not keep a second
matrix. Role checks stay on the route. A missing permission is not reported as an upgrade.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.console.billing import NEW_PLAN_CODES, monthly_fils_for
from app.core import capabilities as catalog
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.errors import ApiError
from app.schemas.billing import FeatureAccess
from app.tenancy.models import BillingAddon, BillingPlan, BillingPlanPrice, Subscription, Tenant

# Pages that were open on Lite, Standard, and Pro before plan rows named them. New plans use the rows.
_GRANDFATHERED = frozenset({"ai_insights", "sales_insights"})
_OPEN = frozenset({"INCLUDED", "TRIAL_INCLUDED"})
class FeatureDenied(Exception):
    """The assistant asked for a tool the published plan does not include."""

    def __init__(self, decision: FeatureAccess) -> None:
        self.decision = decision
        super().__init__(decision.feature_key)


# Assistant tools that read a premium capability. Everyday sales and stock tools stay off this map.
TOOL_FEATURES = {
    "anomalies": "ai_insights",
    "price_suggestions": "ai_insights",
    "shrink_report": "ai_insights",
}


@dataclass(frozen=True)
class _Offer:
    plan: BillingPlan | None
    addon: BillingAddon | None
    country_closed: bool
    price_fils: int | None
    currency: str | None
    price_published: bool
    custom_pricing: bool
    benefits: tuple[str, ...]


def explain(
    db: Session,
    tenant: Tenant | None,
    *,
    profile: str,
    purchased: list[str],
    promotional: list[str],
    managed: dict[str, str],
    country: str | None,
) -> list[FeatureAccess]:
    """Every catalogue capability for this store. Callers keep the rows the tenant is allowed to see."""
    plans = list(db.scalars(select(BillingPlan).where(BillingPlan.active.is_(True))))
    addons = list(db.scalars(select(BillingAddon).where(BillingAddon.active.is_(True))))
    subscription = None
    plan = None
    if tenant is not None:
        subscription = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id))
        if subscription is not None:
            plan = db.get(BillingPlan, subscription.plan_id)
    code = plan.code if plan is not None else None
    preset = {item.value for item in catalog.PROFILES.get(profile, ())}
    allowed = set(catalog.compatible(profile))
    purchased_keys = set(purchased)
    trial_keys = set(promotional)
    claimed: set[str] = set()
    for row in plans:
        if row.code in NEW_PLAN_CODES:
            claimed.update(row.included_modules or [])
    preset_anywhere = {item.value for items in catalog.PROFILES.values() for item in items}
    plugins: dict[str, BillingAddon] = {}
    for addon in addons:
        for key in addon.module_keys or []:
            if key in claimed or key in preset_anywhere or key in plugins:
                continue
            plugins[key] = addon
    blocked = _subscription_restricted(db, tenant.id) if tenant is not None else False
    trial_open = _trial_available(db, tenant) if tenant is not None else False
    rows: list[FeatureAccess] = []
    for capability in catalog.ORDER:
        rows.append(
            _one(
                db,
                capability,
                plans=plans,
                plan=plan,
                code=code,
                profile_allowed=allowed,
                preset=preset,
                purchased=purchased_keys,
                promotional=trial_keys,
                managed=managed,
                claimed=claimed,
                plugins=plugins,
                country=country,
                restricted=blocked,
                trial_open=trial_open,
            )
        )
    return rows


def decide(
    db: Session,
    tenant: Tenant | None,
    feature_key: str,
    *,
    profile: str,
    purchased: list[str],
    promotional: list[str],
    managed: dict[str, str],
    country: str | None,
) -> FeatureAccess:
    found = None
    for row in explain(
        db,
        tenant,
        profile=profile,
        purchased=purchased,
        promotional=promotional,
        managed=managed,
        country=country,
    ):
        if row.feature_key == feature_key:
            found = row
            break
    if found is None:
        raise ApiError(404, "unknown_feature", "That feature is not in the catalogue.")
    return found


def allowed(decision: FeatureAccess) -> bool:
    return decision.state in _OPEN


def require_feature(feature_key: str):
    """Rejects a route the store's published plan does not include. Tenancy off keeps local tests open.

    The dependency names stay in this module. A nested import leaves them as required query fields.
    """

    def dependency(
        db: Annotated[Session, Depends(get_db)],
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> None:
        if not settings.tenancy_enabled:
            return
        decision = _for_request(db, settings, feature_key)
        if allowed(decision):
            return
        raise ApiError(
            403,
            decision.state,
            _message(decision),
            details={
                "feature_key": decision.feature_key,
                "current_plan": decision.current_plan,
                "required_plan": decision.required_plan,
                "message_key": _message_key(decision.state),
                "price_fils": decision.price_fils,
                "currency": decision.currency,
                "price_published": decision.price_published,
                "custom_pricing": decision.custom_pricing,
                "plugin_code": decision.plugin_code,
            },
        )

    return dependency


def block_tool(db: Session, feature_key: str) -> FeatureAccess | None:
    """None when the tool may run. The assistant uses this so the model is not the entitlement check."""
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.tenancy_enabled:
        return None
    decision = _for_request(db, settings, feature_key)
    if allowed(decision):
        return None
    return decision


def _for_request(db: Session, settings, feature_key: str) -> FeatureAccess:
    from app.services.settings_service import (
        cached_settings,
        effective_promotional_keys,
        effective_purchased_keys,
        load_settings,
        managed_of,
    )
    from app.tenancy import registry
    from app.tenancy.context import current_tenant

    ref = current_tenant()
    if ref is None:
        raise ApiError(400, "tenant_required", "Send X-Tenant-Domain or use your store's subdomain.")
    snapshot = cached_settings(db)
    row = load_settings(db)
    with registry.control_session(settings) as control:
        tenant = control.get(Tenant, uuid.UUID(str(ref.id)))
        return decide(
            control,
            tenant,
            feature_key,
            profile=snapshot.business_profile,
            purchased=effective_purchased_keys(row),
            promotional=effective_promotional_keys(row),
            managed=managed_of(row),
            country=(snapshot.country or "").strip().upper() or None,
        )


def _one(
    db: Session,
    capability: catalog.Capability,
    *,
    plans: list[BillingPlan],
    plan: BillingPlan | None,
    code: str | None,
    profile_allowed: set[str],
    preset: set[str],
    purchased: set[str],
    promotional: set[str],
    managed: dict[str, str],
    claimed: set[str],
    plugins: dict[str, BillingAddon],
    country: str | None,
    restricted: bool,
    trial_open: bool,
) -> FeatureAccess:
    key = capability.value
    spec = catalog.SPECS[capability]
    fits = key in profile_allowed
    current = plan.included_modules or [] if plan is not None else []
    offer = _offer(db, key, plans, plugins, country, current)
    state = _state(
        key,
        code=code,
        fits=fits,
        available=spec.available,
        preset=preset,
        purchased=purchased,
        promotional=promotional,
        managed=managed,
        current=set(current),
        claimed=claimed,
        plugin=plugins.get(key),
        restricted=restricted,
        country_closed=offer.country_closed,
    )
    required = offer.plan if state in {"UPGRADE_REQUIRED", "COUNTRY_UNAVAILABLE"} else None
    plugin = plugins.get(key) if state == "PLUGIN_REQUIRED" else None
    plugin_priced = plugin is not None and plugin.monthly_fils > 0
    baseline = key in preset and key not in claimed and plugins.get(key) is None and key in profile_allowed
    grandfathered = code not in NEW_PLAN_CODES and key in _GRANDFATHERED
    show_price = state == "UPGRADE_REQUIRED" and not offer.custom_pricing
    return FeatureAccess(
        feature_key=key,
        label=spec.label,
        description=_description(key, spec.label),
        state=state,  # type: ignore[arg-type]
        current_plan=code,
        current_plan_name=plan.name if plan is not None else None,
        required_plan=required.code if required is not None else None,
        required_plan_name=required.name if required is not None else None,
        price_fils=offer.price_fils if show_price else (plugin.monthly_fils if plugin_priced else None),
        currency=offer.currency if show_price else ("AED" if plugin_priced else None),
        price_published=offer.price_published if show_price else plugin_priced,
        custom_pricing=state == "UPGRADE_REQUIRED" and offer.custom_pricing,
        trial_available=(
            state == "UPGRADE_REQUIRED" and required is not None and required.code == "PRO_AI" and trial_open
        ),
        plugin_code=plugin.code if plugin is not None else None,
        plugin_name=plugin.name if plugin is not None else None,
        benefits=list(offer.benefits) if state == "UPGRADE_REQUIRED" else [],
        baseline=baseline,
        grandfathered=grandfathered,
    )


def _state(
    key: str,
    *,
    code: str | None,
    fits: bool,
    available: bool,
    preset: set[str],
    purchased: set[str],
    promotional: set[str],
    managed: dict[str, str],
    current: set[str],
    claimed: set[str],
    plugin: BillingAddon | None,
    restricted: bool,
    country_closed: bool,
) -> str:
    override = managed.get(key)
    if override == "off" or not available:
        return "FEATURE_DISABLED"
    if code not in NEW_PLAN_CODES:
        if key in _GRANDFATHERED or key in current or key in purchased or override == "on" or key in preset:
            return "INCLUDED"
        return "SWITCHED_OFF"
    if not fits and override != "on":
        return "BUSINESS_TYPE_UNAVAILABLE"
    if code == "ENTERPRISE" and not current:
        if plugin is not None and key not in purchased and override != "on":
            return "PLUGIN_REQUIRED"
        return "INCLUDED"
    granted = (
        override == "on"
        or key in purchased
        or key in current
        or (key in preset and key not in claimed and plugin is None)
    )
    if granted:
        if restricted and code != "FREE":
            return "SUBSCRIPTION_RESTRICTED"
        return "INCLUDED"
    if key in promotional:
        return "TRIAL_INCLUDED"
    if plugin is not None and key not in claimed:
        return "PLUGIN_REQUIRED"
    if key in claimed:
        if country_closed:
            return "COUNTRY_UNAVAILABLE"
        return "UPGRADE_REQUIRED"
    return "SWITCHED_OFF"


def _offer(
    db: Session,
    key: str,
    plans: list[BillingPlan],
    plugins: dict[str, BillingAddon],
    country: str | None,
    current_modules: list,
) -> _Offer:
    candidates = [
        row
        for row in plans
        if row.code in NEW_PLAN_CODES and row.code != "ENTERPRISE" and key in (row.included_modules or [])
    ]
    candidates.sort(key=lambda row: (row.sort_order, row.monthly_fils))
    plan = candidates[0] if candidates else None
    if plan is None and any(row.code == "ENTERPRISE" and key in (row.included_modules or []) for row in plans):
        plan = next(row for row in plans if row.code == "ENTERPRISE")
    addon = plugins.get(key)
    closed = False
    fils: int | None = None
    currency: str | None = None
    published = False
    custom = plan is not None and plan.code == "ENTERPRISE"
    if plan is not None and country:
        disabled = db.scalar(
            select(BillingPlanPrice.id).where(
                BillingPlanPrice.plan_id == plan.id,
                BillingPlanPrice.country == country,
                BillingPlanPrice.enabled.is_(False),
            )
        )
        enabled = db.scalar(
            select(BillingPlanPrice.id).where(
                BillingPlanPrice.plan_id == plan.id,
                BillingPlanPrice.country == country,
                BillingPlanPrice.enabled.is_(True),
            )
        )
        closed = disabled is not None and enabled is None
    if plan is not None and not custom and not closed:
        try:
            fils, currency = monthly_fils_for(db, plan, country)
            published = True
        except ApiError:
            published = False
    have = set(current_modules or [])
    benefits: list[str] = []
    if plan is not None:
        for item in catalog.parse(plan.included_modules or []):
            if item.value in have or item.value == key:
                continue
            benefits.append(catalog.SPECS[item].label)
            if len(benefits) == 4:
                break
    return _Offer(plan, addon, closed, fils, currency, published, custom, tuple(benefits))


def _subscription_restricted(db: Session, tenant_id: uuid.UUID) -> bool:
    from app.console.transfers import operational_block

    return operational_block(db, tenant_id) is not None


def _trial_available(db: Session, tenant: Tenant) -> bool:
    from datetime import UTC, datetime

    from app.console.promotional_trial import _block_reason, _row, effective_status

    now = datetime.now(UTC)
    if _block_reason(db, tenant, now) is not None:
        return False
    return effective_status(_row(db, tenant.id), now) != "active"


def _description(key: str, label: str) -> str:
    from app.console.billing import _MODULE_DESCRIPTIONS

    text = _MODULE_DESCRIPTIONS.get(key)
    return text if isinstance(text, str) else label


def _message(decision: FeatureAccess) -> str:
    if decision.state == "PLUGIN_REQUIRED":
        return f"{decision.label} is a separate plugin. It is not included with the base plan."
    if decision.state == "COUNTRY_UNAVAILABLE":
        name = decision.required_plan_name or "That plan"
        return f"{name} is not sold in this store's country."
    if decision.state == "FEATURE_DISABLED":
        return f"{decision.label} is turned off."
    if decision.state == "BUSINESS_TYPE_UNAVAILABLE":
        return f"{decision.label} is not available for this business type."
    if decision.state == "SUBSCRIPTION_RESTRICTED":
        return "Paid features stay locked until the subscription is active."
    if decision.state == "UPGRADE_REQUIRED":
        current = decision.current_plan_name or "your current plan"
        required = decision.required_plan_name or "a higher plan"
        return f"{decision.label} is not included in {current}. It requires {required}."
    return f"{decision.label} is not included for this store."


def _message_key(state: str) -> str:
    return {
        "UPGRADE_REQUIRED": "subscription.feature_requires_upgrade",
        "PLUGIN_REQUIRED": "subscription.feature_requires_plugin",
        "COUNTRY_UNAVAILABLE": "subscription.feature_country_unavailable",
        "FEATURE_DISABLED": "subscription.feature_disabled",
        "BUSINESS_TYPE_UNAVAILABLE": "subscription.feature_business_type",
        "SUBSCRIPTION_RESTRICTED": "subscription.restricted",
    }.get(state, "subscription.feature_unavailable")
