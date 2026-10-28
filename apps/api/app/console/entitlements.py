"""Module overrides. The control database is the record of what IT support forced on or off; each change is then
applied to the tenant's own business settings, which every request (and every register sync) reads."""

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.console.security import OperatorPrincipal, audit_operator
from app.core import capabilities as catalog
from app.core.config import Settings
from app.core.errors import ApiError
from app.schemas.console import ModuleState
from app.services import audit
from app.services.settings_service import load_settings, managed_of
from app.tenancy import registry
from app.tenancy.context import use_tenant
from app.tenancy.models import Tenant, TenantModuleOverride

log = logging.getLogger("ai_pos.entitlements")


@contextmanager
def tenant_session(tenant: Tenant, settings: Settings) -> Iterator[Session]:
    ref = registry.ref_for(tenant, settings)
    with registry.session_factory_for(ref)() as db, use_tenant(ref):
        db.info["request_session"] = True
        yield db


def get_tenant(control: Session, tenant_id: uuid.UUID) -> Tenant:
    tenant = control.get(Tenant, tenant_id)
    if tenant is None:
        raise ApiError(404, "not_found", "Tenant was not found.")
    return tenant


def overrides_of(control: Session, tenant_id: uuid.UUID) -> dict[str, TenantModuleOverride]:
    rows = control.scalars(select(TenantModuleOverride).where(TenantModuleOverride.tenant_id == tenant_id)).all()
    return {row.module_key: row for row in rows}


def module_states(
    profile: str,
    selection: list | None,
    managed: dict[str, str],
    purchased: list[str] | None = None,
) -> list[ModuleState]:
    chosen = set(catalog.resolve(profile, selection, purchased=purchased).enabled) | set(
        catalog.resolve(profile, selection, purchased=purchased).planned
    )
    effective = set(catalog.resolve(profile, selection, managed, purchased).enabled)
    fits = set(catalog.compatible(profile))
    return [
        ModuleState(
            key=capability.value,
            label=catalog.SPECS[capability].label,
            available=catalog.SPECS[capability].available,
            enabled=capability in effective,
            selected=capability in chosen,
            fits_type=capability in fits,
            override=managed.get(capability.value),  # type: ignore[arg-type]
        )
        for capability in catalog.ORDER
    ]


def tenant_modules(tenant: Tenant, settings: Settings) -> list[ModuleState]:
    from app.services.settings_service import effective_purchased_keys

    with tenant_session(tenant, settings) as db:
        row = load_settings(db)
        return module_states(row.business_profile, row.capabilities, managed_of(row), effective_purchased_keys(row))


def apply_managed(
    tenant: Tenant,
    settings: Settings,
    managed: dict[str, str],
    *,
    operator: OperatorPrincipal | None,
    reason: str,
    profile: str | None = None,
    reset_selection: bool = False,
) -> tuple[dict[str, str], list[ModuleState]]:
    """Writes the overrides (and, for a migration, the new business type) into the tenant's settings."""
    with tenant_session(tenant, settings) as db:
        row = load_settings(db, lock=True)
        before = {"business_profile": row.business_profile, "managed": managed_of(row)}
        if profile is not None:
            row.business_profile = profile
        if reset_selection:
            row.capabilities = None
        row.managed_capabilities = managed or None
        from app.core.capabilities import Capability, resolve
        from app.services.reorder_service import has_open_plans
        from app.services.settings_service import effective_purchased_keys

        resolved = resolve(row.business_profile, row.capabilities, managed_of(row), effective_purchased_keys(row))
        if Capability.CUSTOMER_REORDERS not in resolved.enabled and has_open_plans(db):
            raise ApiError(
                409,
                "module_in_use",
                "Customer reorder plans still exist. Archive them before changing the business type.",
            )
        audit.record(
            db,
            action_type="UPDATE",
            action="settings.override" if profile is None else "settings.migrate_business_type",
            target_entity="Settings",
            target_entity_id=row.id,
            client_device="console",
            old_values=before,
            new_values={"business_profile": row.business_profile, "managed": managed},
            reason_notes=reason,
            details={"operator": operator.email if operator else None},
        )
        db.commit()
        return before["managed"], module_states(row.business_profile, row.capabilities, managed)


def set_overrides(
    settings: Settings,
    operator: OperatorPrincipal,
    tenant_id: uuid.UUID,
    changes: dict[str, str | None],
    reason: str,
) -> list[ModuleState]:
    known = {capability.value for capability in catalog.Capability}
    unknown = sorted(set(changes) - known)
    if unknown:
        raise ApiError(422, "invalid_request", f"Unknown modules: {', '.join(unknown)}.")
    with registry.control_session(settings) as control:
        tenant = get_tenant(control, tenant_id)
        rows = overrides_of(control, tenant.id)
        now = datetime.now(UTC)
        for key, state in changes.items():
            row = rows.get(key)
            if state is None:
                if row is not None:
                    control.delete(row)
                    rows.pop(key)
                continue
            if row is None:
                row = TenantModuleOverride(id=uuid.uuid4(), tenant_id=tenant.id, module_key=key)
                control.add(row)
                rows[key] = row
            row.state, row.reason, row.operator_id, row.updated_at = state, reason, operator.id, now
        managed = {key: row.state for key, row in rows.items()}
        with tenant_session(tenant, settings) as db:
            current = load_settings(db)
            profile, selection = current.business_profile, current.capabilities
        resolved = catalog.resolve(profile, selection, managed)
        missing = catalog.missing_dependencies(
            [catalog.Capability(key) for key, state in managed.items() if state == "on"] + list(resolved.enabled)
        )
        forced = [capability for capability in missing if managed.get(capability.value) == "on"]
        if forced:
            detail = "; ".join(
                f"{capability.value} needs {', '.join(need.value for need in missing[capability])}"
                for capability in forced
            )
            raise ApiError(422, "capability_dependencies", f"Turn on what these modules need first: {detail}.")
        control.flush()
        before, states = apply_managed(tenant, settings, managed, operator=operator, reason=reason)
        audit_operator(
            control,
            operator,
            "tenant.modules",
            tenant_id=tenant.id,
            before={"managed": before},
            after={"managed": managed},
            reason=reason,
        )
        control.commit()
        return states


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def subscription_module_keys(control: Session, tenant_id: uuid.UUID) -> tuple[list[str], datetime | None]:
    """Module ids a verified subscription currently pays for, and the moment that grant runs out.

    Pending receipts and canceled subscriptions grant nothing. Active, trial, and grace keep the
    mapped modules. The end is always set, so an offline register cannot treat a paid module as permanent.
    """
    from app.console.transfers import access_state, grace_days
    from app.tenancy.models import BillingAddon, Subscription, SubscriptionItem

    if access_state(control, tenant_id) not in {"active", "trial", "grace"}:
        return [], None
    subscription = control.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
    if subscription is None:
        return [], None
    items = list(control.scalars(select(SubscriptionItem).where(SubscriptionItem.subscription_id == subscription.id)))
    codes = {item.addon_code for item in items}
    keys: list[str] = []
    if codes:
        addons = control.scalars(
            select(BillingAddon).where(BillingAddon.code.in_(codes), BillingAddon.active.is_(True))
        )
        for addon in addons:
            keys.extend(addon.module_keys or [])
    grace = timedelta(days=grace_days(control))
    end = subscription.current_period_end or subscription.trial_ends_at
    until = _aware(end) + grace if end is not None else datetime.now(UTC) + grace
    return keys, until


def publish_purchased(settings: Settings, tenant_id: uuid.UUID) -> None:
    """Copies verified add-on modules onto the store. Repeating it with the same grant does nothing."""
    from app.services import audit
    from app.services.settings_service import load_settings

    with registry.control_session(settings) as control:
        tenant = get_tenant(control, tenant_id)
        raw_keys, until = subscription_module_keys(control, tenant.id)
        with tenant_session(tenant, settings) as db:
            row = load_settings(db, lock=True)
            allowed = set(catalog.compatible(row.business_profile))
            keys = [capability.value for capability in catalog.parse(raw_keys) if capability in allowed]
            current = list(row.purchased_capabilities or [])
            same_until = row.entitlement_until == until or (
                row.entitlement_until is not None
                and until is not None
                and _aware(row.entitlement_until) == _aware(until)
            )
            if current == keys and same_until:
                return
            before = current
            row.purchased_capabilities = keys or None
            row.entitlement_until = until
            audit.record(
                db,
                action_type="UPDATE",
                action="settings.purchased",
                target_entity="Settings",
                target_entity_id=row.id,
                client_device="billing",
                old_values={"purchased_capabilities": before},
                new_values={"purchased_capabilities": keys},
                reason_notes="Verified add-on subscription",
            )
            db.commit()
            from app.services.addon_access import invalidate_access_cache

            invalidate_access_cache(tenant.id)
            log.info(
                "entitlement published tenant=%s revision=%s modules=%s",
                tenant.id,
                row.cache_generation,
                len(keys),
            )
