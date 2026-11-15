"""Console reset and restore for one tenant's operational data.

Snapshots are Fernet-encrypted files under ``data_reset_dir``. That directory is not
served by the API. Subscription invoices, console operators, audit logs, the owner
login, branch records, legal business settings, and e-invoice copies are never
targets. Every query includes the tenant id. A reset does not start until the
snapshot decrypts and its counts match.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import Date, DateTime, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.console.entitlements import get_tenant, tenant_session
from app.console.security import OperatorPrincipal, audit_operator
from app.core.config import Settings
from app.core.errors import ApiError
from app.core.security import verify_password
from app.models.accounting import JournalEntry, JournalLine
from app.models.batch import Supplier
from app.models.brand import Brand, ProductModel
from app.models.category import Category, SubCategory
from app.models.cheque import Cheque
from app.models.customer import Customer, CustomerCoupon, CustomerLedgerEntry
from app.models.device import Device, DeviceActivation
from app.models.expense import Expense, PettyCashEntry
from app.models.inventory import InventoryLevel, StockMovement
from app.models.kitchen import KitchenStation, KitchenTicket, KitchenTicketItem
from app.models.loyalty import LoyaltyEntry
from app.models.payables import SupplierBill, SupplierBillLine, SupplierPayment, SupplierPaymentAllocation
from app.models.payment_intent import PaymentIntent, PaymentRefund
from app.models.product import Product
from app.models.product_price import ProductPrice
from app.models.promotion import Promotion, PromotionRedemption
from app.models.purchasing import GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine
from app.models.recipe import Recipe, RecipeLine
from app.models.repair_ticket import RepairAttachment, RepairDeposit, RepairEvent, RepairLine, RepairTicket
from app.models.reservation import (
    Reservation,
    ReservationSettings,
    ReservationStatusEvent,
    SeatingSessionOrder,
    TableActivityEvent,
    TableSeatingSession,
)
from app.models.restaurant import DiningArea, DiningTable, OpenOrder, OpenOrderItem
from app.models.return_item import ReturnItem
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sale_return import SaleReturn
from app.models.sale_tender import SaleTender
from app.models.serial_number import SerialNumber
from app.models.shift import CashMovement, RegisterShift
from app.models.store import Store
from app.models.store_credit import StoreCredit
from app.models.time_entry import TimeEntry
from app.models.user import User
from app.tenancy import registry
from app.tenancy.models import ConsoleResetGuard, Operator, TenantDataOperation

log = logging.getLogger("ai_pos.data_reset")

RESET_PERMISSION = "tenant.data.reset"
SNAPSHOT_VERSION = 1
PAGE = 200

PROTECTED = (
    "Tenant ownership and the owner login (a user with no branch).",
    "Branch records. Reset clears a branch's data and leaves the branch in place.",
    "Roles and console administrator accounts.",
    "Legal business settings.",
    "Audit logs.",
    "Tax e-invoice copies and the invoice chain.",
    "Subscription, billing invoices, and payment verification on the console.",
    "Any row whose tenant id is not the tenant in this operation.",
)


@dataclass(frozen=True)
class Target:
    model: type
    category: str
    label: str
    # store: filter this table's branch column. parent: follow a parent row.
    # tenant: shared catalog, only when every branch is in scope. branch_user: branch staff, never the owner.
    scope: str
    column: str = "store_id"
    parent: type | None = None
    parent_fk: str = ""
    parent_column: str | None = "store_id"


def _t(
    model: type,
    category: str,
    label: str,
    scope: str,
    *,
    column: str = "store_id",
    parent: type | None = None,
    parent_fk: str = "",
    parent_column: str | None = "store_id",
) -> Target:
    return Target(model, category, label, scope, column, parent, parent_fk, parent_column)


# Children first. Restore walks this list backwards.
TARGETS: tuple[Target, ...] = (
    _t(StockMovement, "products", "Stock movements", "store"),
    _t(InventoryLevel, "products", "Stock quantities", "store"),
    _t(SerialNumber, "products", "Serial numbers", "store"),
    _t(ProductPrice, "products", "Price tiers", "tenant", parent_column=None),
    _t(Product, "products", "Products and variants", "tenant", parent_column=None),
    _t(SubCategory, "products", "Sub-categories", "tenant", parent_column=None),
    _t(Category, "products", "Categories", "tenant", parent_column=None),
    _t(ProductModel, "products", "Product models", "tenant", parent_column=None),
    _t(Brand, "products", "Brands", "tenant", parent_column=None),
    _t(ReturnItem, "sales", "Return items", "parent", parent=SaleReturn, parent_fk="return_id"),
    _t(SaleReturn, "sales", "Returns", "store"),
    _t(SaleItem, "sales", "Sale items", "parent", parent=Sale, parent_fk="sale_id"),
    _t(SaleTender, "sales", "Sale tenders", "parent", parent=Sale, parent_fk="sale_id"),
    _t(PromotionRedemption, "sales", "Promotion redemptions", "store"),
    _t(
        CustomerLedgerEntry,
        "sales",
        "Customer ledger entries for these sales",
        "parent",
        parent=Sale,
        parent_fk="sale_id",
    ),
    _t(LoyaltyEntry, "sales", "Loyalty entries for these sales", "parent", parent=Sale, parent_fk="sale_id"),
    _t(Sale, "sales", "Sales", "store"),
    _t(Promotion, "sales", "Promotions", "tenant", parent_column=None),
    _t(CustomerCoupon, "sales", "Customer coupons", "tenant", parent_column=None),
    _t(CustomerLedgerEntry, "sales", "Customer ledger", "tenant", parent_column=None),
    _t(LoyaltyEntry, "sales", "Loyalty points", "tenant", parent_column=None),
    _t(Customer, "sales", "Customers", "tenant", parent_column=None),
    _t(
        GoodsReceiptLine,
        "purchasing",
        "Goods receipt lines",
        "parent",
        parent=GoodsReceipt,
        parent_fk="goods_receipt_id",
    ),
    _t(GoodsReceipt, "purchasing", "Goods received notes", "store"),
    _t(
        PurchaseOrderLine,
        "purchasing",
        "Purchase order lines",
        "parent",
        parent=PurchaseOrder,
        parent_fk="purchase_order_id",
        parent_column="destination_store_id",
    ),
    _t(PurchaseOrder, "purchasing", "Purchase orders", "store", column="destination_store_id"),
    _t(
        SupplierPaymentAllocation,
        "purchasing",
        "Supplier payment allocations",
        "parent",
        parent=SupplierBill,
        parent_fk="bill_id",
    ),
    _t(SupplierBillLine, "purchasing", "Supplier bill lines", "parent", parent=SupplierBill, parent_fk="bill_id"),
    _t(SupplierBill, "purchasing", "Supplier bills", "store"),
    _t(SupplierPayment, "purchasing", "Supplier payments", "tenant", parent_column=None),
    _t(Supplier, "purchasing", "Suppliers", "tenant", parent_column=None),
    _t(
        SeatingSessionOrder,
        "restaurant",
        "Seating session orders",
        "parent",
        parent=TableSeatingSession,
        parent_fk="seating_session_id",
    ),
    _t(KitchenTicketItem, "restaurant", "Kitchen ticket items", "parent", parent=KitchenTicket, parent_fk="ticket_id"),
    _t(KitchenTicket, "restaurant", "Kitchen tickets", "store"),
    _t(OpenOrderItem, "restaurant", "Open order items", "parent", parent=OpenOrder, parent_fk="order_id"),
    _t(OpenOrder, "restaurant", "Open orders", "store"),
    _t(TableSeatingSession, "restaurant", "Table seating sessions", "store"),
    _t(TableActivityEvent, "restaurant", "Table activity", "store"),
    _t(DiningTable, "restaurant", "Dining tables", "parent", parent=DiningArea, parent_fk="area_id"),
    _t(DiningArea, "restaurant", "Floor areas", "store"),
    _t(KitchenStation, "restaurant", "Kitchen stations", "store"),
    _t(ReservationStatusEvent, "restaurant", "Reservation status events", "store"),
    _t(Reservation, "restaurant", "Reservations", "store"),
    _t(ReservationSettings, "restaurant", "Reservation settings", "store"),
    _t(RecipeLine, "restaurant", "Recipe lines", "tenant", parent_column=None),
    _t(Recipe, "restaurant", "Recipes", "tenant", parent_column=None),
    _t(CashMovement, "finance", "Cash movements", "store"),
    _t(RegisterShift, "finance", "Register sessions", "store"),
    _t(PettyCashEntry, "finance", "Petty cash", "store"),
    _t(Expense, "finance", "Expenses", "store"),
    _t(PaymentRefund, "finance", "Payment refunds", "parent", parent=PaymentIntent, parent_fk="intent_id"),
    _t(PaymentIntent, "finance", "Payment records", "store"),
    _t(JournalLine, "finance", "Journal lines", "tenant", parent_column=None),
    _t(JournalEntry, "finance", "Journal entries", "tenant", parent_column=None),
    _t(DeviceActivation, "staff", "Register activation keys", "parent", parent=Device, parent_fk="device_id"),
    _t(Device, "staff", "Registers", "store"),
    _t(TimeEntry, "staff", "Timesheets", "store"),
    _t(User, "staff", "Branch users", "branch_user"),
    _t(RepairAttachment, "operations", "Repair attachments", "parent", parent=RepairTicket, parent_fk="ticket_id"),
    _t(RepairDeposit, "operations", "Repair deposits", "parent", parent=RepairTicket, parent_fk="ticket_id"),
    _t(RepairEvent, "operations", "Repair events", "parent", parent=RepairTicket, parent_fk="ticket_id"),
    _t(RepairLine, "operations", "Repair lines", "parent", parent=RepairTicket, parent_fk="ticket_id"),
    _t(RepairTicket, "operations", "Repair tickets", "store"),
    _t(Cheque, "operations", "Cheques", "store"),
    _t(StoreCredit, "operations", "Store credit", "store"),
)

CATEGORIES: tuple[dict[str, str], ...] = (
    {
        "id": "products",
        "group": "Products & Inventory",
        "label": "Products, stock, and catalog",
        "kind": "operational",
        "warning": (
            "A single branch reset removes that branch's stock only. "
            "The shared catalog is removed when every branch is in scope."
        ),
    },
    {
        "id": "sales",
        "group": "Sales & Customers",
        "label": "Sales, returns, customers, and loyalty",
        "kind": "operational",
        "warning": (
            "Sale items, tenders, returns, and ledger rows for those sales are included. "
            "Customer records are removed only when every branch is in scope."
        ),
    },
    {
        "id": "purchasing",
        "group": "Purchasing & Suppliers",
        "label": "Purchase orders, receipts, and supplier bills",
        "kind": "operational",
        "warning": (
            "Supplier records and supplier payments are shared. "
            "They are removed only when every branch is in scope."
        ),
    },
    {
        "id": "restaurant",
        "group": "Restaurant & Operations",
        "label": "Tables, open orders, kitchen, and reservations",
        "kind": "operational",
        "warning": "Recipes are shared across branches and are removed only for an all-branch reset.",
    },
    {
        "id": "finance",
        "group": "Finance",
        "label": "Register sessions, expenses, and payments",
        "kind": "operational",
        "warning": (
            "Journal entries are not stored per branch. They are removed only when every branch is in scope. "
            "Subscription invoices are not included."
        ),
    },
    {
        "id": "staff",
        "group": "Configuration & Staff",
        "label": "Branch users, registers, and timesheets",
        "kind": "configuration",
        "warning": (
            "The owner login has no branch and is kept. "
            "Sales that still reference a branch user block this category until sales are reset too."
        ),
    },
    {
        "id": "operations",
        "group": "Other operational data",
        "label": "Repairs, cheques, and store credit",
        "kind": "operational",
        "warning": "",
    },
)

CATEGORY_IDS = {row["id"] for row in CATEGORIES}


def require_reset(operator: OperatorPrincipal) -> None:
    """``tenant.data.reset`` is held by console ADMIN only. SUPPORT cannot reset or restore."""
    if operator.role != "ADMIN":
        raise ApiError(403, "forbidden", "Tenant data reset requires the console admin permission tenant.data.reset.")


def catalog() -> dict:
    return {"categories": list(CATEGORIES), "protected": list(PROTECTED), "permission": RESET_PERMISSION}


def _fingerprint(tenant_id: uuid.UUID, scope: str, store_ids: list[uuid.UUID], categories: list[str]) -> str:
    payload = {
        "tenant_id": str(tenant_id),
        "scope": scope,
        "store_ids": sorted(str(item) for item in store_ids),
        "categories": sorted(categories),
    }
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def _stores(session: Session, tenant_id: uuid.UUID) -> list[Store]:
    return list(session.scalars(select(Store).where(Store.tenant_id == tenant_id).order_by(Store.name)))


def _resolve_stores(session: Session, tenant_id: uuid.UUID, scope: str, store_id: uuid.UUID | None) -> list[Store]:
    rows = _stores(session, tenant_id)
    if scope == "tenant":
        return rows
    if store_id is None:
        raise ApiError(422, "store_required", "Choose the branch to reset.")
    match = [row for row in rows if row.id == store_id]
    if not match:
        raise ApiError(422, "store_outside_tenant", "That branch is not part of this tenant.")
    return match


def _applies(target: Target, scope: str) -> bool:
    """A shared-catalog target runs only for an all-branch reset. It replaces the narrower copy of the same table."""
    if scope == "tenant" and target.scope != "tenant":
        if any(
            other.model is target.model and other.scope == "tenant" and other.category == target.category
            for other in TARGETS
        ):
            return False
    if target.scope == "tenant":
        return scope == "tenant"
    return True


def _clause(target: Target, tenant_id: uuid.UUID, store_ids: list[uuid.UUID], scope: str):
    model = target.model
    cond = [model.tenant_id == tenant_id]
    if not _applies(target, scope):
        return None
    if target.scope != "tenant" and not store_ids:
        return None
    if target.scope == "store":
        cond.append(getattr(model, target.column).in_(store_ids))
    elif target.scope == "branch_user":
        cond.append(model.store_id.in_(store_ids))
        cond.append(model.store_id.is_not(None))
    elif target.scope == "parent":
        assert target.parent is not None
        parent_ids = select(target.parent.id).where(target.parent.tenant_id == tenant_id)
        if target.parent_column:
            parent_ids = parent_ids.where(getattr(target.parent, target.parent_column).in_(store_ids))
        elif scope != "tenant":
            return None
        cond.append(getattr(model, target.parent_fk).in_(parent_ids))
    return cond


def _selected(categories: list[str], scope: str) -> list[Target]:
    return [target for target in TARGETS if target.category in categories and _applies(target, scope)]


def _count(
    session: Session, target: Target, tenant_id: uuid.UUID, store_ids: list[uuid.UUID], scope: str
) -> int | None:
    cond = _clause(target, tenant_id, store_ids, scope)
    if cond is None:
        return None
    try:
        return int(session.scalar(select(func.count()).select_from(target.model).where(*cond)) or 0)
    except Exception as exc:
        log.warning("data reset count failed for %s: %s", target.model.__tablename__, type(exc).__name__)
        raise ApiError(409, "count_unavailable", f"Could not count {target.label}. The reset was not started.") from exc


def _blockers(
    session: Session, tenant_id: uuid.UUID, store_ids: list[uuid.UUID], categories: set[str], scope: str
) -> list[dict[str, str]]:
    extra: list[dict[str, str]] = []
    if not store_ids:
        return extra
    sales = int(
        session.scalar(
            select(func.count()).select_from(Sale).where(Sale.tenant_id == tenant_id, Sale.store_id.in_(store_ids))
        )
        or 0
    )
    if "staff" in categories and "sales" not in categories and sales:
        extra.append(
            {
                "category": "sales",
                "reason": (
                    "Branch users are referenced by sales in this scope. "
                    "Those sales have to be reset as well, or the users stay."
                ),
            }
        )
    if scope == "tenant" and "products" in categories and "sales" not in categories and sales:
        extra.append(
            {
                "category": "sales",
                "reason": (
                    "Sale items reference products. Resetting the shared catalog requires resetting sales as well."
                ),
            }
        )
    return extra


def _public(row: TenantDataOperation, operator_name: str | None = None) -> dict:
    preview = row.preview or {}
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "scope": row.scope,
        "store_ids": list(row.store_ids or []),
        "categories": list(row.categories or []),
        "status": row.status,
        "ready": bool(preview.get("ready")),
        "preview": preview,
        "snapshot_records": row.snapshot_records,
        "records_reset": row.records_reset,
        "records_restored": row.records_restored,
        "conflicts": row.conflicts or [],
        "failure": row.failure,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "restored_at": row.restored_at.isoformat() if row.restored_at else None,
        "created_by": operator_name or preview.get("operator_name") or "",
        "snapshot_reference": row.id.hex[:12] if row.snapshot_sha256 else None,
    }


def list_branches(settings: Settings, operator: OperatorPrincipal, tenant_id: uuid.UUID) -> dict:
    require_reset(operator)
    with registry.control_session(settings) as control:
        tenant = get_tenant(control, tenant_id)
        with tenant_session(tenant, settings) as session:
            rows = _stores(session, tenant.id)
        return {
            "tenant_id": str(tenant.id),
            "tenant_name": tenant.name,
            "branches": [{"id": str(row.id), "name": row.name, "code": row.code} for row in rows],
        }


def preview(
    settings: Settings,
    operator: OperatorPrincipal,
    tenant_id: uuid.UUID,
    *,
    scope: str,
    store_id: uuid.UUID | None,
    categories: list[str],
    idempotency_key: str,
    acknowledge_dependencies: bool,
) -> dict:
    require_reset(operator)
    if scope not in ("store", "tenant"):
        raise ApiError(422, "bad_scope", "Choose one branch or all branches.")
    unknown = [item for item in categories if item not in CATEGORY_IDS]
    if unknown:
        raise ApiError(422, "unknown_category", "One of the categories is not resettable.")
    if not categories:
        raise ApiError(422, "categories_required", "Select at least one data category.")
    with registry.control_session(settings) as control:
        tenant = get_tenant(control, tenant_id)
        with tenant_session(tenant, settings) as session:
            stores = _resolve_stores(session, tenant.id, scope, store_id)
            store_ids = [row.id for row in stores]
            chosen = set(categories)
            blockers = _blockers(session, tenant.id, store_ids, chosen, scope)
            needed = sorted({item["category"] for item in blockers if item["category"] not in chosen})
            ready = not needed or acknowledge_dependencies
            stored_categories = sorted(chosen | set(needed)) if ready else sorted(chosen)
            counts = []
            skipped = []
            for target in TARGETS:
                if target.category not in stored_categories:
                    continue
                if not _applies(target, scope):
                    if target.scope == "tenant":
                        skipped.append(
                            {
                                "table": target.model.__tablename__,
                                "label": target.label,
                                "reason": "Shared across branches. Included only when every branch is reset.",
                            }
                        )
                    continue
                amount = _count(session, target, tenant.id, store_ids, scope)
                if amount is None:
                    continue
                counts.append(
                    {
                        "table": target.model.__tablename__,
                        "label": target.label,
                        "category": target.category,
                        "records": amount,
                    }
                )
            body = {
                "ready": ready,
                "tenant_name": tenant.name,
                "tenant_id": str(tenant.id),
                "scope": scope,
                "branches": [{"id": str(row.id), "name": row.name, "code": row.code} for row in stores],
                "categories": stored_categories,
                "counts": counts,
                "total_records": sum(row["records"] for row in counts),
                "dependencies": blockers,
                "required_categories": needed,
                "skipped_shared": skipped,
                "operator_name": operator.full_name,
                "protected": list(PROTECTED),
            }
            digest = _fingerprint(tenant.id, scope, store_ids, stored_categories)
            existing = control.scalar(
                select(TenantDataOperation).where(
                    TenantDataOperation.tenant_id == tenant.id,
                    TenantDataOperation.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                # A draft can be refreshed, including when the administrator confirms extra
                # categories the dependency check requires. A started reset cannot be reused.
                if existing.status not in {"PREVIEWED", "AUTHORIZED"} or (
                    existing.status == "AUTHORIZED" and existing.fingerprint != digest
                ):
                    raise ApiError(409, "duplicate_reset", "This reset request was already used.")
                existing.preview = body
                existing.categories = stored_categories
                existing.store_ids = [str(item) for item in store_ids]
                existing.scope = scope
                existing.fingerprint = digest
                existing.status = "PREVIEWED"
                existing.authorized_until = None
                control.commit()
                return _public(existing, operator.full_name)
            row = TenantDataOperation(
                tenant_id=tenant.id,
                operator_id=operator.id,
                scope=scope,
                store_ids=[str(item) for item in store_ids],
                categories=stored_categories,
                fingerprint=digest,
                status="PREVIEWED",
                idempotency_key=idempotency_key,
                preview=body,
            )
            control.add(row)
            audit_operator(
                control,
                operator,
                "console.data_reset_previewed",
                tenant_id=tenant.id,
                after={
                    "operation_id": str(row.id),
                    "scope": scope,
                    "categories": stored_categories,
                    "records": body["total_records"],
                },
            )
            control.commit()
            return _public(row, operator.full_name)


def _load_operation(control: Session, tenant_id: uuid.UUID, operation_id: uuid.UUID) -> TenantDataOperation:
    row = control.get(TenantDataOperation, operation_id)
    if row is None or row.tenant_id != tenant_id:
        raise ApiError(404, "not_found", "That reset was not found for this tenant.")
    return row


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _check_guard(control: Session, operator_id: uuid.UUID) -> None:
    row = control.get(ConsoleResetGuard, operator_id)
    locked = _aware(row.locked_until) if row is not None else None
    if locked is not None and locked > datetime.now(UTC):
        raise ApiError(429, "reset_locked", "Too many incorrect passwords. Try again later.")


def _reject_password(control: Session, operator: OperatorPrincipal, settings: Settings, tenant_id: uuid.UUID) -> None:
    now = datetime.now(UTC)
    window = timedelta(minutes=settings.login_lockout_minutes)
    row = control.get(ConsoleResetGuard, operator.id)
    if row is None:
        row = ConsoleResetGuard(operator_id=operator.id, failures=1, window_started=now)
        control.add(row)
    elif _aware(row.window_started) is None or now - _aware(row.window_started) > window:
        row.failures = 1
        row.window_started = now
        row.locked_until = None
    else:
        row.failures += 1
        if row.failures >= settings.login_max_attempts:
            row.locked_until = now + window
    audit_operator(
        control,
        operator,
        "console.data_reset_password_failed",
        tenant_id=tenant_id,
        after={"failures": row.failures},
    )
    control.commit()
    raise ApiError(401, "bad_password", "The console administrator password was not accepted.")


def _verify_password(
    control: Session, operator: OperatorPrincipal, settings: Settings, tenant_id: uuid.UUID, password: str
) -> None:
    _check_guard(control, operator.id)
    account = control.get(Operator, operator.id)
    if account is None or not account.is_active:
        raise ApiError(401, "unauthorized", "The console session is no longer valid.")
    if not password or not verify_password(password, account.password_hash):
        _reject_password(control, operator, settings, tenant_id)
    guard = control.get(ConsoleResetGuard, operator.id)
    if guard is not None:
        guard.failures = 0
        guard.locked_until = None


def authorize(
    settings: Settings,
    operator: OperatorPrincipal,
    tenant_id: uuid.UUID,
    operation_id: uuid.UUID,
    password: str,
) -> dict:
    require_reset(operator)
    with registry.control_session(settings) as control:
        row = _load_operation(control, tenant_id, operation_id)
        if not (row.preview or {}).get("ready"):
            raise ApiError(409, "dependencies", "Confirm the dependent categories before authorizing this reset.")
        if row.status == "COMPLETED":
            return _public(row)
        if row.status not in {"PREVIEWED", "AUTHORIZED"}:
            raise ApiError(409, "reset_closed", "This reset can no longer be authorized.")
        _verify_password(control, operator, settings, tenant_id, password)
        row.status = "AUTHORIZED"
        row.authorized_until = datetime.now(UTC) + timedelta(minutes=settings.data_reset_auth_minutes)
        audit_operator(
            control,
            operator,
            "console.data_reset_authorized",
            tenant_id=tenant_id,
            after={"operation_id": str(row.id)},
        )
        control.commit()
        return _public(row)


def _root(settings: Settings) -> Path:
    root = Path(settings.data_reset_dir)
    if not root.is_absolute():
        root = Path.cwd() / root
    root.mkdir(parents=True, exist_ok=True)
    return root


def _snapshot_path(settings: Settings, tenant_id: uuid.UUID, operation_id: uuid.UUID) -> Path:
    folder = _root(settings) / str(tenant_id)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{operation_id}.json.enc"


def _dump(value: object) -> object:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"__b64__": base64.b64encode(value).decode("ascii")}
    return value


def _load_cell(column, value: object) -> object:
    if value is None:
        return None
    if isinstance(value, dict) and "__b64__" in value:
        return base64.b64decode(str(value["__b64__"]))
    name = type(column.type).__name__
    if name in {"Uuid", "UUID"} and isinstance(value, str):
        return uuid.UUID(value)
    if isinstance(column.type, DateTime) and isinstance(value, str):
        return datetime.fromisoformat(value)
    if isinstance(column.type, Date) and isinstance(value, str):
        return date.fromisoformat(value)
    return value


def _capture(
    session: Session, targets: list[Target], tenant_id: uuid.UUID, store_ids: list[uuid.UUID], scope: str
) -> tuple[bytes, dict[str, int]]:
    tables: dict[str, list[dict]] = {}
    counts: dict[str, int] = {}
    for target in targets:
        cond = _clause(target, tenant_id, store_ids, scope)
        if cond is None:
            continue
        columns = [column for column in target.model.__table__.columns if column.computed is None]
        rows: list[dict] = []
        last = None
        while True:
            query = select(target.model).where(*cond).order_by(target.model.id).limit(PAGE)
            if last is not None:
                query = query.where(target.model.id > last)
            batch = list(session.scalars(query))
            if not batch:
                break
            for item in batch:
                rows.append({column.key: _dump(getattr(item, column.key)) for column in columns})
            last = batch[-1].id
            session.expire_all()
        key = target.model.__tablename__
        tables.setdefault(key, [])
        tables[key].extend(rows)
        counts[key] = counts.get(key, 0) + len(rows)
    payload = {
        "version": SNAPSHOT_VERSION,
        "tenant_id": str(tenant_id),
        "store_ids": [str(item) for item in store_ids],
        "tables": tables,
        "counts": counts,
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"), counts


def _write_snapshot(settings: Settings, path: Path, plaintext: bytes) -> str:
    from app.core.security import encrypt_value

    token = encrypt_value(plaintext.decode("utf-8"), settings)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(token, encoding="utf-8")
    os.replace(temporary, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return hashlib.sha256(plaintext).hexdigest()


def _read_snapshot(settings: Settings, path: Path, expected_sha: str, tenant_id: uuid.UUID) -> dict:
    from app.core.security import decrypt_value

    if not path.is_file():
        raise ApiError(409, "snapshot_missing", "The recovery snapshot is missing. The reset was not changed.")
    try:
        plaintext = decrypt_value(path.read_text(encoding="utf-8"), settings).encode("utf-8")
        body = json.loads(plaintext)
    except Exception as exc:
        raise ApiError(
            409, "snapshot_corrupt", "The recovery snapshot could not be read. Nothing was restored."
        ) from exc
    digest = hashlib.sha256(plaintext).hexdigest()
    if (
        digest != expected_sha
        or str(body.get("tenant_id")) != str(tenant_id)
        or body.get("version") != SNAPSHOT_VERSION
    ):
        raise ApiError(409, "snapshot_corrupt", "The recovery snapshot failed its integrity check.")
    counted = {key: len(value) for key, value in body.get("tables", {}).items()}
    if counted != body.get("counts"):
        raise ApiError(409, "snapshot_corrupt", "The recovery snapshot counts do not match its rows.")
    return body


def _delete_targets(
    session: Session, targets: list[Target], tenant_id: uuid.UUID, store_ids: list[uuid.UUID], scope: str
) -> int:
    removed = 0
    for target in targets:
        cond = _clause(target, tenant_id, store_ids, scope)
        if cond is None:
            continue
        last = None
        while True:
            query = select(target.model.id).where(*cond).order_by(target.model.id).limit(PAGE)
            if last is not None:
                query = query.where(target.model.id > last)
            batch = list(session.scalars(query))
            if not batch:
                break
            session.execute(delete(target.model).where(target.model.tenant_id == tenant_id, target.model.id.in_(batch)))
            session.commit()
            removed += len(batch)
            last = batch[-1]
    return removed


def execute(settings: Settings, operator: OperatorPrincipal, tenant_id: uuid.UUID, operation_id: uuid.UUID) -> dict:
    require_reset(operator)
    with registry.control_session(settings) as control:
        row = _load_operation(control, tenant_id, operation_id)
        if row.status in {"COMPLETED", "RESTORED"}:
            return _public(row)
        if row.status not in {"AUTHORIZED", "SNAPSHOTTING", "SNAPSHOT_VERIFIED", "RESETTING"}:
            raise ApiError(409, "not_authorized", "Authorize this reset with your console password before it runs.")
        authorized_until = _aware(row.authorized_until)
        if row.status == "AUTHORIZED" and (authorized_until is None or authorized_until < datetime.now(UTC)):
            row.status = "PREVIEWED"
            row.authorized_until = None
            control.commit()
            raise ApiError(
                409, "authorization_expired", "The password confirmation expired. Enter your password again."
            )
        tenant = get_tenant(control, tenant_id)
        store_ids = [uuid.UUID(item) for item in row.store_ids]
        categories = list(row.categories)
        if _fingerprint(tenant.id, row.scope, store_ids, categories) != row.fingerprint:
            raise ApiError(409, "request_mismatch", "This reset no longer matches the request that was authorized.")
        targets = _selected(categories, row.scope)
        path = _snapshot_path(settings, tenant.id, row.id)
        if row.status == "AUTHORIZED":
            row.status = "SNAPSHOTTING"
            control.commit()
            try:
                with tenant_session(tenant, settings) as session:
                    plaintext, counts = _capture(session, targets, tenant.id, store_ids, row.scope)
                digest = _write_snapshot(settings, path, plaintext)
                verified = _read_snapshot(settings, path, digest, tenant.id)
                if verified["counts"] != counts:
                    raise ApiError(409, "snapshot_mismatch", "The snapshot counts did not match. No data was reset.")
            except ApiError:
                row.status = "FAILED"
                row.failure = "The recovery snapshot could not be verified. No data was reset."
                audit_operator(
                    control,
                    operator,
                    "console.data_reset_failed",
                    tenant_id=tenant.id,
                    after={"operation_id": str(row.id)},
                )
                control.commit()
                raise
            except Exception as exc:
                log.warning("data reset snapshot failed for %s: %s", row.id, type(exc).__name__)
                row.status = "FAILED"
                row.failure = "The recovery snapshot could not be created. No data was reset."
                control.commit()
                raise ApiError(409, "snapshot_failed", row.failure) from exc
            row.status = "SNAPSHOT_VERIFIED"
            row.snapshot_relpath = str(path.relative_to(_root(settings)))
            row.snapshot_sha256 = digest
            row.snapshot_records = sum(counts.values())
            control.commit()
        if not row.snapshot_sha256:
            raise ApiError(409, "snapshot_missing", "This reset has no verified snapshot.")
        _read_snapshot(settings, path, row.snapshot_sha256, tenant.id)
        row.status = "RESETTING"
        control.commit()
        try:
            with tenant_session(tenant, settings) as session:
                removed = _delete_targets(session, targets, tenant.id, store_ids, row.scope)
            from app.console import stats

            stats.collect(control, tenant, settings)
        except Exception as exc:
            log.warning("data reset failed after snapshot %s: %s", row.id, type(exc).__name__)
            row.status = "FAILED"
            row.failure = "The reset stopped after the snapshot was saved. Restore is available."
            control.commit()
            raise ApiError(409, "reset_failed", row.failure) from exc
        row.status = "COMPLETED"
        row.records_reset = removed
        row.completed_at = datetime.now(UTC)
        row.expires_at = row.completed_at + timedelta(days=settings.data_reset_retention_days)
        row.authorized_until = None
        audit_operator(
            control,
            operator,
            "console.data_reset_completed",
            tenant_id=tenant.id,
            after={
                "operation_id": str(row.id),
                "records": removed,
                "snapshot_reference": row.id.hex[:12],
                "categories": categories,
            },
        )
        control.commit()
        return _public(row, operator.full_name)


def history(settings: Settings, operator: OperatorPrincipal, tenant_id: uuid.UUID) -> list[dict]:
    require_reset(operator)
    with registry.control_session(settings) as control:
        get_tenant(control, tenant_id)
        rows = control.scalars(
            select(TenantDataOperation)
            .where(TenantDataOperation.tenant_id == tenant_id)
            .order_by(TenantDataOperation.created_at.desc())
            .limit(50)
        ).all()
        names = {
            item.id: item.full_name
            for item in control.scalars(
                select(Operator).where(Operator.id.in_([row.operator_id for row in rows] or [uuid.uuid4()]))
            )
        }
        return [_public(row, names.get(row.operator_id)) for row in rows]


def _restorable(row: TenantDataOperation) -> None:
    restorable = {"COMPLETED", "RESTORED", "FAILED", "RESTORE_FAILED", "RESTORE_REQUESTED", "RESTORING"}
    if row.status not in restorable or not row.snapshot_sha256:
        raise ApiError(409, "not_restorable", "This reset has no recovery snapshot.")
    expires = _aware(row.expires_at)
    if expires is not None and expires < datetime.now(UTC):
        raise ApiError(409, "snapshot_expired", "This recovery snapshot has expired.")


def restore_preview(
    settings: Settings, operator: OperatorPrincipal, tenant_id: uuid.UUID, operation_id: uuid.UUID
) -> dict:
    require_reset(operator)
    with registry.control_session(settings) as control:
        row = _load_operation(control, tenant_id, operation_id)
        _restorable(row)
        tenant = get_tenant(control, tenant_id)
        path = _snapshot_path(settings, tenant.id, row.id)
        body = _read_snapshot(settings, path, row.snapshot_sha256 or "", tenant.id)
        conflicts = []
        with tenant_session(tenant, settings) as session:
            for target in reversed(_selected(list(row.categories), row.scope)):
                table_rows = body.get("tables", {}).get(target.model.__tablename__, [])
                if not table_rows:
                    continue
                ids = [uuid.UUID(item["id"]) for item in table_rows if item.get("id")]
                existing = set(
                    session.scalars(
                        select(target.model.id).where(
                            target.model.tenant_id == tenant.id, target.model.id.in_(ids[:500])
                        )
                    )
                )
                for found in list(existing)[:20]:
                    conflicts.append(
                        {"table": target.model.__tablename__, "id": str(found), "resolution": "left unchanged"}
                    )
        return {
            **_public(row),
            "records_to_restore": sum(len(rows) for rows in body.get("tables", {}).values()),
            "conflicts": conflicts,
            "conflict_count": len(conflicts),
        }


def restore_authorize(
    settings: Settings,
    operator: OperatorPrincipal,
    tenant_id: uuid.UUID,
    operation_id: uuid.UUID,
    password: str,
) -> dict:
    require_reset(operator)
    with registry.control_session(settings) as control:
        row = _load_operation(control, tenant_id, operation_id)
        _restorable(row)
        _verify_password(control, operator, settings, tenant_id, password)
        row.restore_authorized_until = datetime.now(UTC) + timedelta(minutes=settings.data_reset_auth_minutes)
        if row.status != "RESTORED":
            row.status = "RESTORE_REQUESTED"
        audit_operator(
            control,
            operator,
            "console.data_restore_authorized",
            tenant_id=tenant_id,
            after={"operation_id": str(row.id)},
        )
        control.commit()
        return _public(row)


def restore(settings: Settings, operator: OperatorPrincipal, tenant_id: uuid.UUID, operation_id: uuid.UUID) -> dict:
    require_reset(operator)
    with registry.control_session(settings) as control:
        row = _load_operation(control, tenant_id, operation_id)
        _restorable(row)
        if _aware(row.restore_authorized_until) is None or _aware(row.restore_authorized_until) < datetime.now(UTC):
            raise ApiError(409, "authorization_expired", "Enter your console password again before restoring.")
        tenant = get_tenant(control, tenant_id)
        path = _snapshot_path(settings, tenant.id, row.id)
        body = _read_snapshot(settings, path, row.snapshot_sha256 or "", tenant.id)
        row.status = "RESTORING"
        control.commit()
        restored = 0
        conflicts: list[dict[str, str]] = []
        try:
            with tenant_session(tenant, settings) as session:
                order = list(reversed(_selected(list(row.categories), row.scope)))
                seen: set[str] = set()
                for target in order:
                    key = target.model.__tablename__
                    if key in seen:
                        continue
                    seen.add(key)
                    table_rows = body.get("tables", {}).get(key, [])
                    columns = [column for column in target.model.__table__.columns if column.computed is None]
                    for raw in table_rows:
                        if str(raw.get("tenant_id")) != str(tenant.id):
                            raise ApiError(409, "snapshot_corrupt", "The snapshot contains a row for another tenant.")
                        identifier = uuid.UUID(str(raw["id"]))
                        current = session.scalar(
                            select(target.model.id).where(
                                target.model.tenant_id == tenant.id, target.model.id == identifier
                            )
                        )
                        if current is not None:
                            conflicts.append({"table": key, "id": str(identifier), "resolution": "left unchanged"})
                            continue
                        values = {
                            column.key: _load_cell(column, raw.get(column.key))
                            for column in columns
                            if column.key in raw
                        }
                        values["tenant_id"] = tenant.id
                        try:
                            session.execute(target.model.__table__.insert().values(**values))
                            session.commit()
                            restored += 1
                        except IntegrityError:
                            session.rollback()
                            conflicts.append(
                                {"table": key, "id": str(identifier), "resolution": "kept the newer record"}
                            )
        except ApiError:
            row.status = "RESTORE_FAILED"
            row.failure = "The snapshot failed its tenant check. No further rows were written."
            control.commit()
            raise
        except Exception as exc:
            log.warning("data restore failed for %s: %s", row.id, type(exc).__name__)
            row.status = "RESTORE_FAILED"
            row.failure = "The restore stopped. The snapshot is still available."
            control.commit()
            raise ApiError(409, "restore_failed", row.failure) from exc
        from app.console import stats

        stats.collect(control, tenant, settings)
        row.status = "RESTORED"
        row.records_restored = restored
        row.conflicts = conflicts[:100]
        row.restored_at = datetime.now(UTC)
        row.restore_operator_id = operator.id
        row.restore_authorized_until = None
        row.failure = None
        audit_operator(
            control,
            operator,
            "console.data_restore_completed",
            tenant_id=tenant.id,
            after={"operation_id": str(row.id), "records": restored, "conflicts": len(conflicts)},
        )
        control.commit()
        return _public(row, operator.full_name)


def purge_expired(settings: Settings, operator: OperatorPrincipal) -> dict:
    """Deletes expired snapshot files. Incomplete resets are left alone."""
    require_reset(operator)
    removed = 0
    with registry.control_session(settings) as control:
        now = datetime.now(UTC)
        rows = control.scalars(
            select(TenantDataOperation).where(
                TenantDataOperation.expires_at.is_not(None),
                TenantDataOperation.expires_at < now,
                TenantDataOperation.status.in_(("COMPLETED", "RESTORED", "RESTORE_FAILED")),
            )
        ).all()
        for row in rows:
            if row.snapshot_relpath:
                path = _root(settings) / row.snapshot_relpath
                if path.is_file():
                    path.unlink()
                    removed += 1
            row.snapshot_relpath = None
            row.snapshot_sha256 = None
            audit_operator(
                control,
                operator,
                "console.data_reset_purged",
                tenant_id=row.tenant_id,
                after={"operation_id": str(row.id)},
            )
        control.commit()
    return {"purged": removed}
