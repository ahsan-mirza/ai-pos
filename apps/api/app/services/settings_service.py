import copy
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import event, select, update
from sqlalchemy.orm import ORMExecuteState, Session

from app.core import capabilities as capability_catalog
from app.core.config import get_settings
from app.core.currency import BUSINESS_SETTINGS_ID, DEFAULT_CURRENCY, SUPPORTED_CURRENCIES
from app.core.errors import ApiError
from app.models.business_settings import BusinessSettings
from app.models.product import Product
from app.models.store import Store
from app.models.user import User
from app.schemas.governance import TenantModulesOut
from app.schemas.module_settings import ModuleSettings, resolve_module_settings
from app.schemas.pos_policy import PosPolicy, resolve_pos_policy
from app.schemas.receipt import ReceiptProfileOut, ReceiptSettings, ReceiptStore, resolve_receipt_settings
from app.schemas.settings import AppearanceUpdate, BusinessSettingsOut, ProfileUpdate, TaxSettingsUpdate
from app.services import audit, race
from app.tenancy.scoping import DEFAULT_TENANT_ID, active_tenant_id, include_all_tenants

CURRENCY_CHANGED = "settings.currency"
# Commits in this process invalidate at once; the TTL bounds staleness when another API worker changed the row.
CACHE_TTL_SECONDS = 30.0
_CHANGED = "business_settings_changed"


@dataclass(frozen=True)
class SettingsSnapshot:
    """Read-only copy of the business settings row, safe to share between requests."""

    id: Any
    currency: str
    vat_registered: bool
    trn: str | None
    legal_name: str | None
    legal_name_ar: str | None
    prices_include_vat: bool
    standard_rate_bps: int
    messaging: dict | None
    message_events: dict | None
    updated_at: datetime | None
    updated_by_name: str | None
    primary_color: str | None = None
    business_profile: str = capability_catalog.DEFAULT_PROFILE
    capabilities: tuple[capability_catalog.Capability, ...] = capability_catalog.ELECTRONICS_WHOLESALE
    planned_capabilities: tuple[capability_catalog.Capability, ...] = ()
    onboarded: bool = True
    tax_authority: str = "fta"
    module_settings: ModuleSettings = field(default_factory=ModuleSettings)
    receipt: ReceiptSettings = field(default_factory=ReceiptSettings)
    pos_policy: PosPolicy = field(default_factory=PosPolicy)
    practice_mode: bool = False
    live_at: datetime | None = None
    # Go live sets this. Sync uses it to refuse practice events; it is not part of the settings API.
    promoted_from_practice: bool = False
    # Live, and the tax authority issues e-invoices, but no production credential is on file.
    tax_portal_pending: bool = False
    # IT support's overrides from the console: module -> "on" | "off".
    managed_capabilities: dict[str, str] = field(default_factory=dict)
    entitlement_revision: int = 1
    purchased_capabilities: tuple[str, ...] = ()
    entitlement_until: datetime | None = None


class _SettingsCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[tuple[int, uuid.UUID], tuple[float, SettingsSnapshot, str | None]] = {}
        self._generation = 0

    def get(self, key: tuple[int, uuid.UUID]) -> tuple[SettingsSnapshot, str | None] | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry[0] <= time.monotonic():
                return None
            return entry[1], entry[2]

    def generation(self) -> int:
        with self._lock:
            return self._generation

    def put(
        self, key: tuple[int, uuid.UUID], snapshot: SettingsSnapshot, generation: int, token: str | None
    ) -> None:
        """Skips the write when settings changed while this snapshot was being read."""
        with self._lock:
            if generation == self._generation:
                self._entries[key] = (time.monotonic() + CACHE_TTL_SECONDS, snapshot, token)

    def clear(self) -> None:
        with self._lock:
            self._generation += 1
            self._entries.clear()


_cache = _SettingsCache()


def clear_settings_cache() -> None:
    _cache.clear()


@event.listens_for(Session, "before_flush")
def _bump_settings_generation(session: Session, _flush_context: object, _instances: object) -> None:
    if session.info.get("_bumping_settings"):
        return
    session.info["_bumping_settings"] = True
    try:
        for obj in list(session.dirty):
            if isinstance(obj, BusinessSettings):
                obj.cache_generation = int(obj.cache_generation or 1) + 1
    finally:
        session.info.pop("_bumping_settings", None)


@event.listens_for(Session, "after_flush")
def _track_settings_writes(session: Session, _flush_context: object) -> None:
    if any(isinstance(obj, BusinessSettings) for obj in (*session.new, *session.dirty, *session.deleted)):
        session.info[_CHANGED] = True


@event.listens_for(Session, "do_orm_execute")
def _track_bulk_settings_writes(state: ORMExecuteState) -> None:
    if (state.is_update or state.is_delete) and state.bind_mapper is not None:
        if state.bind_mapper.class_ is BusinessSettings:
            state.session.info[_CHANGED] = True


@event.listens_for(Session, "before_commit")
def _queue_settings_invalidation(session: Session) -> None:
    if not session.info.get(_CHANGED) or session.info.get("_outbox_written"):
        return
    if session.info.get("control_database"):
        return
    from app.models.cache import CacheInvalidation
    from app.tenancy.context import current_tenant

    tenant = current_tenant()
    if tenant is None:
        return
    session.info["_outbox_written"] = True
    session.add(CacheInvalidation(cache_key=f"tenant:{tenant.id}:settings:token"))
    session.flush()


@event.listens_for(Session, "after_commit")
def _invalidate_on_commit(session: Session) -> None:
    changed = session.info.pop(_CHANGED, False)
    session.info.pop("_outbox_written", None)
    if not changed:
        return
    _cache.clear()
    from app.core.cache import set_value
    from app.tenancy.context import current_tenant

    tenant = current_tenant()
    if tenant is not None:
        set_value(f"tenant:{tenant.id}:settings:token", str(uuid.uuid4()), 86_400)


@event.listens_for(Session, "after_rollback")
def _forget_on_rollback(session: Session) -> None:
    session.info.pop(_CHANGED, None)


def _load(db: Session, *, lock: bool) -> tuple[BusinessSettings, bool]:
    statement = select(BusinessSettings).limit(1)
    if lock and db.get_bind().dialect.name == "postgresql":
        # `updated_by` is eager-joined, and Postgres refuses to lock the nullable side of an outer join.
        statement = statement.with_for_update(of=BusinessSettings)
    row = db.scalar(statement)
    if row is not None:
        return row, False
    active = active_tenant_id()
    placeholder = db.scalar(
        select(BusinessSettings)
        .where(BusinessSettings.id == BUSINESS_SETTINGS_ID)
        .execution_options(include_all_tenants=True)
    )
    if (
        placeholder is not None
        and str(placeholder.tenant_id) == str(DEFAULT_TENANT_ID)
        and active != DEFAULT_TENANT_ID
    ):
        with include_all_tenants(db):
            placeholder.tenant_id = active
            db.flush()
        return placeholder, False
    first_store = db.scalar(select(Store).order_by(Store.created_at).limit(1))
    row = BusinessSettings(
        id=BUSINESS_SETTINGS_ID if placeholder is None else uuid.uuid5(active, "business-settings"),
        currency=first_store.currency if first_store is not None else DEFAULT_CURRENCY,
    )
    if not race.add_if_absent(db, [row]):
        existing = db.scalar(statement)
        assert existing is not None
        return existing, False
    return row, True


def load_settings(db: Session, *, lock: bool = False) -> BusinessSettings:
    """The live ORM row, always read from the database. Use it to change settings; reads use `cached_settings`."""
    return _load(db, lock=lock)[0]


def managed_of(row: BusinessSettings) -> dict[str, str]:
    known = {capability.value for capability in capability_catalog.Capability}
    return {
        key: value for key, value in (row.managed_capabilities or {}).items() if key in known and value in ("on", "off")
    }


def _tax_portal_pending(row: BusinessSettings) -> bool:
    """True once the store is live and its authority issues e-invoices without a production credential.

    Practice keys are deleted at Go live. A later invoice may create a new simulation key; that is still not a
    production connection, so the portal keeps asking for one.
    """
    if row.live_at is None:
        return False
    from sqlalchemy.orm import object_session

    from app.tax_authority import ADAPTERS

    adapter = ADAPTERS.get(row.tax_authority or "fta")
    if adapter is None or not adapter.issues_einvoices:
        return False
    session = object_session(row)
    if session is None:
        return True
    from app.models.einvoice import TaxAuthorityCredential

    credential = session.scalar(
        select(TaxAuthorityCredential).where(TaxAuthorityCredential.authority == adapter.code)
    )
    return credential is None or credential.environment != "production"


def effective_purchased_keys(row: BusinessSettings, now: datetime | None = None) -> list[str]:
    """Paid module keys that are still inside the subscription window. A missing end does not keep them forever."""
    parsed = [capability.value for capability in capability_catalog.parse(row.purchased_capabilities or [])]
    until = row.entitlement_until
    if until is None:
        return parsed
    stamp = until if until.tzinfo is not None else until.replace(tzinfo=UTC)
    if stamp <= (now or datetime.now(UTC)):
        return []
    return parsed


def snapshot_of(row: BusinessSettings) -> SettingsSnapshot:
    profile = row.business_profile or capability_catalog.DEFAULT_PROFILE
    managed = managed_of(row)
    purchased = effective_purchased_keys(row)
    resolved = capability_catalog.resolve(profile, row.capabilities, managed, purchased)
    return SettingsSnapshot(
        managed_capabilities=managed,
        entitlement_revision=int(row.cache_generation or 1),
        purchased_capabilities=tuple(purchased),
        entitlement_until=row.entitlement_until,
        business_profile=profile,
        capabilities=resolved.enabled,
        planned_capabilities=resolved.planned,
        onboarded=row.onboarded_at is not None,
        practice_mode=row.live_at is None,
        live_at=row.live_at,
        promoted_from_practice=bool(row.promoted_from_practice),
        tax_portal_pending=_tax_portal_pending(row),
        id=row.id,
        currency=row.currency,
        vat_registered=bool(row.vat_registered),
        trn=row.trn,
        legal_name=row.legal_name,
        legal_name_ar=row.legal_name_ar,
        prices_include_vat=bool(row.prices_include_vat),
        standard_rate_bps=int(row.standard_rate_bps),
        messaging=copy.deepcopy(row.messaging),
        message_events=copy.deepcopy(row.message_events),
        updated_at=row.updated_at,
        updated_by_name=row.updated_by.full_name if row.updated_by is not None else None,
        primary_color=row.primary_color,
        tax_authority=row.tax_authority or "fta",
        module_settings=resolve_module_settings(row.module_settings),
        receipt=resolve_receipt_settings(row.receipt),
        pos_policy=resolve_pos_policy(row.pos_policy, profile),
    )


def _pending_settings_change(db: Session) -> bool:
    if db.info.get(_CHANGED):
        return True
    return any(isinstance(obj, BusinessSettings) for obj in (*db.new, *db.dirty, *db.deleted))


def cached_settings(db: Session) -> SettingsSnapshot:
    """Business settings for read paths, served from memory. A session holding uncommitted settings changes
    always reads its own row so it sees them."""
    if _pending_settings_change(db):
        return snapshot_of(load_settings(db))
    from app.core.cache import get_value

    tenant_id = active_tenant_id()
    key = (id(db.get_bind()), tenant_id)
    token = get_value(f"tenant:{tenant_id}:settings:token")
    hit = _cache.get(key)
    if hit is not None and (token is None or hit[1] == token):
        return hit[0]
    generation = _cache.generation()
    row, created = _load(db, lock=False)
    snapshot = snapshot_of(row)
    if not created:
        _cache.put(key, snapshot, generation, token)
    return snapshot


def business_currency(db: Session) -> str:
    return cached_settings(db).currency


def report_currency(db: Session, requested: str | None) -> str:
    """Reports default to the business currency; an explicit code reads history taken in another one."""
    if requested is None:
        return business_currency(db)
    code = requested.strip().upper()
    if re.fullmatch(r"[A-Z]{3}", code) is None:
        raise ApiError(422, "invalid_request", "currency must be a 3-letter ISO code.")
    return code


def settings_out(settings: BusinessSettings | SettingsSnapshot) -> BusinessSettingsOut:
    snapshot = settings if isinstance(settings, SettingsSnapshot) else snapshot_of(settings)
    return BusinessSettingsOut(
        currency=snapshot.currency,
        supported_currencies=list(SUPPORTED_CURRENCIES),
        updated_at=snapshot.updated_at,
        updated_by_name=snapshot.updated_by_name,
        vat_registered=snapshot.vat_registered,
        trn=snapshot.trn,
        legal_name=snapshot.legal_name,
        legal_name_ar=snapshot.legal_name_ar,
        prices_include_vat=snapshot.prices_include_vat,
        standard_rate_bps=snapshot.standard_rate_bps,
        primary_color=snapshot.primary_color,
        business_profile=snapshot.business_profile,
        capabilities=[capability.value for capability in snapshot.capabilities],
        planned_capabilities=[capability.value for capability in snapshot.planned_capabilities],
        entitlement_revision=snapshot.entitlement_revision,
        purchased_capabilities=list(snapshot.purchased_capabilities),
        entitlement_until=snapshot.entitlement_until,
        register_capabilities=[
            capability.value
            for capability in snapshot.capabilities
            if capability in capability_catalog.REGISTER_CAPABILITIES
        ],
        onboarded=snapshot.onboarded,
        practice_mode=snapshot.practice_mode,
        tax_portal_pending=snapshot.tax_portal_pending,
        tax_authority=snapshot.tax_authority,
        module_settings=snapshot.module_settings.model_copy(deep=True),
        pos_policy=snapshot.pos_policy.model_copy(deep=True),
    )


def pos_policy(db: Session) -> PosPolicy:
    return cached_settings(db).pos_policy


def change_pos_policy(db: Session, actor: User, data: PosPolicy) -> BusinessSettingsOut:
    row = load_settings(db, lock=True)
    before = resolve_pos_policy(row.pos_policy, row.business_profile).model_dump()
    after = data.model_dump()
    if before == after:
        return settings_out(row)
    row.pos_policy = after
    row.updated_by_id = actor.id
    audit.record(
        db,
        action_type="UPDATE",
        action="settings.pos_policy",
        target_entity="Settings",
        target_entity_id=row.id,
        user=actor,
        old_values=before,
        new_values=after,
    )
    db.commit()
    db.refresh(row)
    return settings_out(row)


def change_appearance(db: Session, actor: User, data: AppearanceUpdate) -> BusinessSettingsOut:
    row = load_settings(db, lock=True)
    previous = row.primary_color
    if previous == data.primary_color:
        return settings_out(row)
    row.primary_color = data.primary_color
    row.updated_by_id = actor.id
    audit.record(
        db,
        action_type="UPDATE",
        action="settings.appearance",
        target_entity="Settings",
        target_entity_id=row.id,
        user=actor,
        old_values={"primary_color": previous},
        new_values={"primary_color": data.primary_color},
    )
    db.commit()
    db.refresh(row)
    return settings_out(row)


PROFILE_CHANGED = "settings.profile"


def provision_profile(db: Session, profile: str) -> None:
    """Seed and tenant provisioning: the profile's preset modules. Onboarding is left to the first admin."""
    if profile not in capability_catalog.PROFILES:
        raise ApiError(422, "invalid_request", f"Unknown business profile '{profile}'.")
    row = load_settings(db, lock=True)
    row.business_profile = profile
    row.capabilities = None
    db.commit()


def tenant_modules(db: Session, tenant_name: str) -> TenantModulesOut:
    snapshot = cached_settings(db)
    profile = snapshot.business_profile
    enabled = {capability.value for capability in snapshot.capabilities}
    listed = capability_catalog.catalogue(profile)
    return TenantModulesOut(
        tenant_name=tenant_name,
        business_profile=profile,
        profile_label=capability_catalog.PROFILE_LABELS.get(profile, profile),
        locked=snapshot.onboarded,
        enabled=[capability.value for capability in snapshot.capabilities],
        base=[capability.value for capability in listed.base],
        optional=[capability.value for capability in listed.optional],
        available=[
            capability.value
            for capability in capability_catalog.compatible(profile)
            if capability.value not in enabled and capability_catalog.SPECS[capability].available
        ],
        planned=[capability.value for capability in snapshot.planned_capabilities],
        managed=dict(snapshot.managed_capabilities),  # type: ignore[arg-type]
        support_email=get_settings().support_email,
    )


def locked_message(support_email: str) -> str:
    return f"To change your business type and migrate store data safely, please contact IT Support at {support_email}"


def _check_locked_change(row: BusinessSettings, profile: str) -> None:
    """After onboarding the business type is fixed. Its sales and stock depend on it."""
    if profile != row.business_profile:
        raise ApiError(409, "business_type_locked", locked_message(get_settings().support_email))


def _check_selection_fits(profile: str, selection: list[str] | None, managed: dict[str, str]) -> None:
    """A store can switch on only modules its business type offers, plus modules IT support already forced on."""
    if selection is None:
        return
    allowed = set(capability_catalog.compatible(profile))
    outside = [
        value for value in selection if capability_catalog.Capability(value) not in allowed and value not in managed
    ]
    if outside:
        names = ", ".join(capability_catalog.SPECS[capability_catalog.Capability(value)].label for value in outside)
        raise ApiError(
            422,
            "module_not_available",
            f"{names} does not fit a {capability_catalog.PROFILE_LABELS.get(profile, profile)} business. "
            "Ask IT Support to add it.",
            details={"modules": outside},
        )


def _guard_reorder_module(db: Session, resolved: capability_catalog.Resolved) -> None:
    """A store cannot drop reorder plans, or leave the business type that uses them, while plans still exist."""
    if capability_catalog.Capability.CUSTOMER_REORDERS in resolved.enabled:
        return
    from app.services.reorder_service import has_open_plans

    if has_open_plans(db):
        raise ApiError(
            409,
            "module_in_use",
            "Customer reorder plans still exist. Archive them before turning this module off.",
        )


def commercial_module_keys() -> set[str]:
    """Capability ids a priced add-on is allowed to sell. Tenancy off means nothing is sold as an add-on."""
    settings = get_settings()
    if not settings.tenancy_enabled:
        return set()
    from sqlalchemy import select

    from app.tenancy import registry
    from app.tenancy.models import BillingAddon

    try:
        with registry.control_session(settings) as control:
            rows = control.scalars(select(BillingAddon).where(BillingAddon.active.is_(True))).all()
            return {key for row in rows for key in (row.module_keys or [])}
    except Exception as exc:
        raise ApiError(
            503,
            "entitlement_unavailable",
            "Module access could not be confirmed. Try again.",
        ) from exc


def _refuse_unpaid(profile: str, selection: list[str] | None, row: BusinessSettings, purchased: list[str]) -> None:
    """A module mapped to a priced add-on cannot be switched on from the portal until payment is verified.

    Modules already stored for this store stay, including ones chosen before the add-on was mapped.
    """
    if selection is None:
        return
    preset = {capability.value for capability in capability_catalog.PROFILES.get(profile, ())}
    stored = row.capabilities
    already = set(stored) if stored is not None else preset
    newly = set(selection) - already - preset - set(purchased)
    if not newly:
        return
    blocked = sorted(newly & commercial_module_keys())
    if not blocked:
        return
    names = ", ".join(capability_catalog.SPECS[capability_catalog.Capability(value)].label for value in blocked)
    raise ApiError(
        402,
        "payment_required",
        f"{names} is sold as an add-on. It switches on after the payment is verified.",
        details={"modules": blocked},
    )


def _refuse_dropping_purchased(profile: str, selection: list[str] | None, purchased: list[str]) -> None:
    if selection is None or not purchased:
        return
    fitting = {
        key
        for key in purchased
        if key in {capability.value for capability in capability_catalog.compatible(profile)}
    }
    removed = sorted(fitting - set(selection))
    if not removed:
        return
    names = ", ".join(capability_catalog.SPECS[capability_catalog.Capability(value)].label for value in removed)
    raise ApiError(
        409,
        "module_purchased",
        f"{names} stays on until the add-on subscription ends.",
        details={"modules": removed},
    )


def note_register_entitlement(db: Session, device_id: uuid.UUID | None, revision: int, seen: int | None) -> None:
    """Records the entitlement revision a register just fetched. The same revision is not written again."""
    if device_id is None or seen == revision:
        return
    from app.models.device import Device

    db.execute(
        update(Device)
        .where(Device.id == device_id)
        .values(entitlement_revision=revision, entitlement_synced_at=datetime.now(UTC))
    )


def change_profile(db: Session, actor: User, data: ProfileUpdate) -> BusinessSettingsOut:
    """Switches the business type and/or its modules. Roadmap modules are kept as planned, never enabled, and a
    disabled module only hides features: its data stays."""
    if data.business_profile not in capability_catalog.PROFILES:
        raise ApiError(422, "invalid_request", f"Unknown business profile '{data.business_profile}'.")
    selection = None
    chosen: list[capability_catalog.Capability] = []
    if data.capabilities is not None:
        unknown = sorted(set(data.capabilities) - {capability.value for capability in capability_catalog.Capability})
        if unknown:
            raise ApiError(422, "invalid_request", f"Unknown modules: {', '.join(unknown)}.")
        chosen = capability_catalog.parse(data.capabilities)
        selection = [capability.value for capability in chosen]

    row = load_settings(db, lock=True)
    if row.onboarded_at is not None:
        _check_locked_change(row, data.business_profile)
    # Refuse a module this business type does not offer before talking about its dependencies.
    _check_selection_fits(data.business_profile, selection, managed_of(row))
    if chosen:
        missing = capability_catalog.missing_dependencies(chosen)
        if missing:
            detail = "; ".join(
                f"{capability.value} needs {', '.join(required.value for required in needs)}"
                for capability, needs in missing.items()
            )
            raise ApiError(422, "capability_dependencies", f"Some modules need others switched on: {detail}.")
    purchased = effective_purchased_keys(row)
    _refuse_unpaid(data.business_profile, selection, row, purchased)
    _refuse_dropping_purchased(data.business_profile, selection, purchased)
    managed = managed_of(row)
    before = {
        "business_profile": row.business_profile,
        "capabilities": [
            capability.value
            for capability in capability_catalog.resolve(
                row.business_profile, row.capabilities, managed, purchased
            ).enabled
        ],
    }
    row.business_profile = data.business_profile
    row.capabilities = selection
    if data.complete_onboarding and row.onboarded_at is None:
        row.onboarded_at = datetime.now(UTC)
    row.updated_by_id = actor.id
    after = capability_catalog.resolve(row.business_profile, row.capabilities, managed, purchased)
    _guard_reorder_module(db, after)
    audit.record(
        db,
        action_type="UPDATE",
        action=PROFILE_CHANGED,
        target_entity="Settings",
        target_entity_id=row.id,
        user=actor,
        old_values={"business_profile": before["business_profile"], "capabilities": before["capabilities"]},
        new_values={"business_profile": row.business_profile, "capabilities": [c.value for c in after.enabled]},
        details={"planned": [c.value for c in after.planned], "onboarding": bool(data.complete_onboarding)},
    )
    db.commit()
    db.refresh(row)
    from app.services.addon_access import invalidate_access_cache

    invalidate_access_cache(row.tenant_id)
    return settings_out(row)


TAX_FIELDS = (
    "vat_registered",
    "trn",
    "legal_name",
    "legal_name_ar",
    "prices_include_vat",
    "standard_rate_bps",
    "tax_authority",
)


def change_tax(db: Session, actor: User, data: TaxSettingsUpdate) -> BusinessSettingsOut:
    row = load_settings(db, lock=True)
    before = {name: getattr(row, name) for name in TAX_FIELDS}
    after = data.model_dump()
    if before == after:
        return settings_out(row)
    for name, value in after.items():
        setattr(row, name, value)
    row.updated_by_id = actor.id
    audit.record(
        db,
        action_type="UPDATE",
        action="settings.tax",
        target_entity="Settings",
        target_entity_id=row.id,
        user=actor,
        old_values=before,
        new_values=after,
    )
    db.commit()
    db.refresh(row)
    return settings_out(row)


def change_module_settings(db: Session, actor: User, data: ModuleSettings) -> BusinessSettingsOut:
    from app.models.category import Category
    from app.services.grocery_service import ensure_bag_product

    row = load_settings(db, lock=True)
    ids = {key.category_id for key in data.department_keys.keys}
    if ids:
        found = set(db.scalars(select(Category.id).where(Category.id.in_(ids))).all())
        if found != ids:
            raise ApiError(422, "unknown_category", "A department key names a category that does not exist.")
    if data.bags.enabled and data.bags.fee_cents > 0:
        ensure_bag_product(db, data.bags)
    before = resolve_module_settings(row.module_settings).model_dump(mode="json")
    after = data.model_dump(mode="json")
    if before == after:
        db.commit()
        return settings_out(row)
    row.module_settings = after
    row.updated_by_id = actor.id
    audit.record(
        db,
        action_type="UPDATE",
        action="settings.modules",
        target_entity="Settings",
        target_entity_id=row.id,
        user=actor,
        old_values=before,
        new_values=after,
    )
    db.commit()
    db.refresh(row)
    return settings_out(row)


def receipt_profile(db: Session, store_id: uuid.UUID | None) -> ReceiptProfileOut:
    """Receipt branding plus the branch's own contact lines; an unknown branch prints without them."""
    store = db.get(Store, store_id) if store_id is not None else None
    return ReceiptProfileOut(
        settings=cached_settings(db).receipt.model_copy(),
        store=ReceiptStore(id=store.id, name=store.name, address=store.address, phone=store.phone)
        if store is not None
        else None,
    )


def _audited_receipt(values: dict[str, Any]) -> dict[str, Any]:
    """The logo is a data URL of up to 64 KB; the audit trail only records whether one is set."""
    return {**values, "logo_png": values.get("logo_png") is not None}


def change_receipt(db: Session, actor: User, data: ReceiptSettings) -> ReceiptProfileOut:
    row = load_settings(db, lock=True)
    before = resolve_receipt_settings(row.receipt).model_dump()
    after = data.model_dump()
    if before != after:
        row.receipt = after
        row.updated_by_id = actor.id
        logo_changed = before["logo_png"] != after["logo_png"]
        audit.record(
            db,
            action_type="UPDATE",
            action="settings.receipt",
            target_entity="Settings",
            target_entity_id=row.id,
            user=actor,
            old_values=_audited_receipt(before),
            new_values=_audited_receipt(after),
            details={"logo_changed": logo_changed},
        )
        db.commit()
    return ReceiptProfileOut(settings=resolve_receipt_settings(row.receipt))


def change_currency(db: Session, actor: User, currency: str) -> BusinessSettingsOut:
    """Relabels every store and product price in the new currency. Amounts are not converted, and
    recorded sales, returns, and repairs keep the currency they were taken in."""
    row = load_settings(db, lock=True)
    previous = row.currency
    if previous == currency:
        return settings_out(row)
    stores = db.execute(update(Store).values(currency=currency)).rowcount
    products = db.execute(update(Product).values(currency=currency)).rowcount
    row.currency = currency
    row.updated_by_id = actor.id
    audit.record(
        db,
        action_type="UPDATE",
        action=CURRENCY_CHANGED,
        target_entity="Settings",
        target_entity_id=row.id,
        user=actor,
        old_values={"currency": previous},
        new_values={"currency": currency},
        details={"from": previous, "to": currency, "stores": stores, "products": products},
    )
    db.commit()
    db.refresh(row)
    return settings_out(row)
