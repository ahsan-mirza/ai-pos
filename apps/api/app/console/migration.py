"""Business-type migration. Every store shares one schema, so switching type means switching module presets; the
risk is hiding a module whose data is still live. A preflight lists what is gained and lost, refuses while live data
would be stranded (blockers), names what only becomes hidden (warnings), and signs that exact diff: the switch is
only accepted with a fresh token for it and the store's subdomain typed by the operator."""

import hashlib
import hmac
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.console.entitlements import apply_managed, get_tenant, overrides_of, tenant_session
from app.console.security import OperatorPrincipal, audit_operator
from app.core import capabilities as catalog
from app.core.config import Settings
from app.core.errors import ApiError
from app.models.batch import BatchItem, PurchaseBatch
from app.models.cheque import Cheque
from app.models.customer import Customer
from app.models.kitchen import KitchenStation
from app.models.product import Product
from app.models.recipe import Recipe
from app.models.repair_ticket import RepairTicket
from app.models.restaurant import DiningTable, OpenOrder
from app.models.sale import Sale
from app.models.serial_number import SerialNumber
from app.schemas.console import MigrationCheck, MigrationIn, MigrationPreflight, ModuleState
from app.services.settings_service import load_settings, managed_of
from app.tenancy import registry
from app.tenancy.models import TenantChangeRequest

TOKEN_SECONDS = 15 * 60
C = catalog.Capability


def _count(db: Session, statement) -> int:
    return int(db.scalar(statement) or 0)


def _blockers(db: Session, lost: set[catalog.Capability]) -> list[MigrationCheck]:
    """Live data a lost module would strand: it must be finished or settled first."""
    checks: list[tuple[catalog.Capability, str, str, object]] = [
        (
            C.OPEN_ORDERS,
            "open_orders",
            "open tabs or orders must be settled or voided",
            select(func.count(OpenOrder.id)).where(OpenOrder.status == "OPEN"),
        ),
        (
            C.DELIVERY_CHANNELS,
            "open_channel_orders",
            "delivery-app orders are still open",
            select(func.count(OpenOrder.id)).where(OpenOrder.status == "OPEN", OpenOrder.channel_id.is_not(None)),
        ),
        (
            C.B2B_CREDIT,
            "on_account_balances",
            "customers still owe on account",
            select(func.count(Customer.id)).where(Customer.current_balance_cents > 0),
        ),
        (
            C.QUOTES_LAYAWAY,
            "open_quotes",
            "quotations or layaways are still open",
            select(func.count(Sale.id)).where(Sale.is_quote_proforma.is_(True), Sale.quote_status == "OPEN"),
        ),
        (
            C.CHEQUES,
            "uncleared_cheques",
            "cheques have not cleared yet",
            select(func.count(Cheque.id)).where(Cheque.status.in_(("RECEIVED", "DEPOSITED"))),
        ),
        (
            C.REPAIRS,
            "active_repairs",
            "repair tickets are still in the workshop",
            select(func.count(RepairTicket.id)).where(RepairTicket.status.not_in(("closed", "cancelled"))),
        ),
        (
            C.CONSIGNMENT,
            "consignment_stock",
            "supplier-owned consignment stock is still on hand",
            select(func.count(BatchItem.id))
            .join(PurchaseBatch, PurchaseBatch.id == BatchItem.batch_id)
            .where(PurchaseBatch.is_consignment.is_(True), BatchItem.quantity_remaining > 0),
        ),
    ]
    found = []
    for capability, code, message, statement in checks:
        if capability in lost:
            count = _count(db, statement)
            if count:
                found.append(MigrationCheck(code=code, message=f"{count} {message}.", count=count))
    return found


def _warnings(db: Session, lost: set[catalog.Capability]) -> list[MigrationCheck]:
    """Data that stays but is hidden while the module is off."""
    checks: list[tuple[catalog.Capability, str, str, object]] = [
        (
            C.SERIAL_TRACKING,
            "serialized_units",
            "IMEI/serial units in stock become untracked at the till",
            select(func.count(SerialNumber.id)).where(SerialNumber.status == "in_stock"),
        ),
        (
            C.WEIGHED_ITEMS,
            "weighed_products",
            "products sold by weight lose scale support",
            select(func.count(Product.id)).where(Product.sold_by_weight.is_(True)),
        ),
        (C.RECIPES, "recipes", "recipes stop drawing ingredients", select(func.count(Recipe.id))),
        (C.KDS, "kitchen_stations", "kitchen stations go dark", select(func.count(KitchenStation.id))),
        (C.TABLES, "tables", "tables leave the floor plan", select(func.count(DiningTable.id))),
        (
            C.LOYALTY,
            "loyalty_balances",
            "customers hold loyalty points they cannot redeem",
            select(func.count(Customer.id)).where(Customer.loyalty_points > 0),
        ),
    ]
    found = []
    for capability, code, message, statement in checks:
        if capability in lost:
            count = _count(db, statement)
            if count:
                found.append(MigrationCheck(code=code, message=f"{count} {message}.", count=count))
    return found


def _sign(settings: Settings, tenant_id: uuid.UUID, current: str, target: str, diff: str, expires: int) -> str:
    key = (settings.console_jwt_secret or settings.encryption_secret).encode("utf-8")
    message = f"{tenant_id}|{current}|{target}|{diff}|{expires}".encode()
    return f"{expires}.{hmac.new(key, message, hashlib.sha256).hexdigest()}"


def _diff_key(gained: list[str], lost: list[str]) -> str:
    return f"+{','.join(gained)}-{','.join(lost)}"


def _assess(db: Session, target: str) -> tuple[str, list[str], list[str], dict[str, str], list, list]:
    row = load_settings(db)
    managed = managed_of(row)
    current = set(catalog.resolve(row.business_profile, row.capabilities, managed).enabled)
    after = set(catalog.resolve(target, None, managed).enabled)
    lost = current - after
    gained = sorted(capability.value for capability in after - current)
    return (
        row.business_profile,
        gained,
        sorted(capability.value for capability in lost),
        managed,
        _blockers(db, lost),
        _warnings(db, lost),
    )


def _target(value: str) -> str:
    if value not in catalog.PROFILES:
        raise ApiError(422, "invalid_request", f"Unknown business type '{value}'.")
    return value


def preflight(settings: Settings, operator: OperatorPrincipal, tenant_id: uuid.UUID, target: str) -> MigrationPreflight:
    target = _target(target)
    with registry.control_session(settings) as control:
        tenant = get_tenant(control, tenant_id)
        with tenant_session(tenant, settings) as db:
            current, gained, lost, _, blockers, warnings = _assess(db, target)
        if current == target:
            raise ApiError(422, "invalid_request", "The store already has this business type.")
        expires = int(time.time()) + TOKEN_SECONDS
        token = _sign(settings, tenant.id, current, target, _diff_key(gained, lost), expires)
        audit_operator(
            control,
            operator,
            "tenant.migration_preflight",
            tenant_id=tenant.id,
            after={"target": target, "blockers": [check.code for check in blockers]},
        )
        control.commit()
        return MigrationPreflight(
            tenant_id=tenant.id,
            current_profile=current,
            target_profile=target,
            gained=gained,
            lost=lost,
            blockers=blockers,
            warnings=warnings,
            preflight_token=token,
            expires_at=datetime.fromtimestamp(expires, UTC),
        )


def migrate(
    settings: Settings, operator: OperatorPrincipal, tenant_id: uuid.UUID, data: MigrationIn
) -> list[ModuleState]:
    target = _target(data.target_profile)
    with registry.control_session(settings) as control:
        tenant = get_tenant(control, tenant_id)
        if data.confirm_slug.strip().lower() != tenant.slug:
            raise ApiError(422, "confirm_mismatch", "Type the store's subdomain exactly to confirm.")
        with tenant_session(tenant, settings) as db:
            current, gained, lost, managed, blockers, _ = _assess(db, target)
        expires_text, _, _ = data.preflight_token.partition(".")
        if not expires_text.isdigit() or int(expires_text) < time.time():
            raise ApiError(409, "preflight_expired", "Run the safety checks again; that preflight has expired.")
        expected = _sign(settings, tenant.id, current, target, _diff_key(gained, lost), int(expires_text))
        if not hmac.compare_digest(expected, data.preflight_token):
            raise ApiError(409, "preflight_changed", "The store changed since the safety checks; run them again.")
        if blockers:
            raise ApiError(
                409,
                "migration_blocked",
                "Finish these first: " + " ".join(check.message for check in blockers),
                details={"blockers": [check.model_dump() for check in blockers]},
            )
        request = None
        if data.change_request_id is not None:
            request = control.get(TenantChangeRequest, data.change_request_id)
            if request is None or request.tenant_id != tenant.id or request.status != "PENDING":
                raise ApiError(422, "invalid_request", "That change request is not pending for this store.")
        control.flush()
        _, states = apply_managed(
            tenant,
            settings,
            {key: row.state for key, row in overrides_of(control, tenant.id).items()} or managed,
            operator=operator,
            reason=data.reason.strip(),
            profile=target,
            reset_selection=True,
        )
        tenant.profile = target
        if request is not None:
            request.status = "RESOLVED"
            request.resolved_by_operator_id = operator.id
            request.resolution_notes = f"Business type changed to {catalog.PROFILE_LABELS.get(target, target)}."
            request.resolved_at = datetime.now(UTC)
        audit_operator(
            control,
            operator,
            "tenant.migrate_business_type",
            tenant_id=tenant.id,
            before={"business_profile": current},
            after={"business_profile": target, "gained": gained, "lost": lost},
            reason=data.reason.strip(),
        )
        control.commit()
        registry.invalidate(tenant.slug)
        return states
