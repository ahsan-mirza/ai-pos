"""Practice mode for self-service stores: the "First win" checklist and the one-time Go live reset.

Go live removes practice transactions and sample products. Keep configuration leaves the catalog, staff, layout
and registers, and either keeps opening stock or zeroes it. Start fresh also drops that configuration and reopens
the setup wizard. Both paths destroy practice tax stamps and restart document numbering."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.capabilities import FOOD_AND_BEVERAGE
from app.core.config import Settings
from app.core.deps import Principal
from app.core.errors import ApiError
from app.models.accounting import JournalEntry, JournalLine
from app.models.approval import ApprovalRequest
from app.models.audit_log import AuditLog
from app.models.banking import BankStatement, BankStatementLine
from app.models.batch import BatchAllocation, BatchItem, ImportMappingTemplate, PurchaseBatch, Supplier
from app.models.brand import Brand, ProductModel
from app.models.business_settings import BusinessSettings
from app.models.category import Category
from app.models.channel import ChannelPayout, DeliveryChannel
from app.models.cheque import Cheque, ChequeEvent
from app.models.consignment import ConsignmentSettlement, ConsignmentSettlementLine
from app.models.currency import ExchangeRate
from app.models.customer import Customer, CustomerLedgerEntry
from app.models.device import Device, DeviceActivation
from app.models.document_sequence import DocumentSequence
from app.models.einvoice import EInvoice, EInvoiceChain, TaxAuthorityCredential
from app.models.expense import Expense, PettyCashEntry
from app.models.inventory import InventoryLevel, StockMovement
from app.models.kitchen import KitchenStation, KitchenTicket, KitchenTicketItem
from app.models.loyalty import LoyaltyEntry
from app.models.margin import MarginPolicy
from app.models.markdown import MarkdownEvent, PriceChange
from app.models.menu import ComboSlot, ComboSlotOption, ModifierGroup, ModifierOption, ProductModifierGroup
from app.models.messaging import OutboundMessage
from app.models.payables import SupplierBill, SupplierBillLine, SupplierPayment, SupplierPaymentAllocation
from app.models.payment_intent import PaymentIntent, PaymentRefund, PaymentTerminal
from app.models.price_list import (
    CustomerGroup,
    PriceList,
    PriceListItem,
    ScheduledPriceChange,
    ScheduledPriceChangeLine,
)
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.product_price import ProductPrice
from app.models.promotion import Promotion, PromotionRedemption
from app.models.purchasing import GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine
from app.models.quote_payment import QuotePayment
from app.models.recipe import ModifierIngredient, Recipe, RecipeLine, RecipeUsage
from app.models.repair_ticket import RepairAttachment, RepairDeposit, RepairEvent, RepairLine, RepairTicket
from app.models.replenishment import DemandDaily, ReplenishmentRun, ReplenishmentSuggestion, SeasonalEvent
from app.models.restaurant import DiningArea, DiningTable, OpenOrder, OpenOrderItem
from app.models.return_item import ReturnItem
from app.models.return_tender import ReturnTender
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sale_return import SaleReturn
from app.models.sale_tender import SaleTender
from app.models.sales_order import DeliveryNote, DeliveryNoteLine, PickList, PickListLine, SalesOrder, SalesOrderLine
from app.models.serial_number import SerialNumber
from app.models.shift import CashMovement, RegisterShift
from app.models.staff import EmployeeProfile, PayrollLine, PayrollRun
from app.models.stock_count import StockCount, StockCountLine
from app.models.store import Store
from app.models.store_credit import StoreCredit, StoreCreditRedemption
from app.models.time_entry import TimeEntry
from app.models.trade_in import TradeIn
from app.models.transfer import StockTransfer, StockTransferLine, StockTransferSerial
from app.models.user import User
from app.models.warranty import WarrantyPlan, WarrantyPolicy, WarrantyRegistration
from app.schemas.onboarding import Checklist, ChecklistItem, GoLiveRequest, GoLiveResult
from app.services import batch_ledger
from app.services.settings_service import load_settings

# Bump when a new required step is added. Completed explore timestamps and known skips are kept.
ONBOARDING_VERSION = 1
# Optional actions inside a step. Skipping one does not mark the step complete.
SKIPPABLE = frozenset({"invite"})

# Stock moved by practice sales and returns, including the ingredients practice dishes drew.
PRACTICE_REFERENCES = ("sale", "sale_return", "sale_recipe")


def _exists(db: Session, statement) -> bool:  # type: ignore[no-untyped-def]
    return db.scalar(statement.limit(1)) is not None


def store_name(db: Session) -> str:
    settings = load_settings(db)
    if settings.legal_name:
        return settings.legal_name
    store = _primary_store(db)
    return store.name if store else "My store"


def _primary_store(db: Session) -> Store | None:
    store = db.scalar(select(Store).where(Store.is_warehouse.is_(False)).order_by(Store.created_at).limit(1))
    if store is None:
        store = db.scalar(select(Store).order_by(Store.created_at).limit(1))
    return store


def opening_stock_units(db: Session) -> int:
    """On-hand of real products after practice sales are put back: what Keep opening stock would carry."""
    samples = select(Product.id).where(Product.is_sample.is_(True))
    on_hand = int(
        db.scalar(
            select(func.coalesce(func.sum(InventoryLevel.quantity_on_hand), 0)).where(
                InventoryLevel.product_id.not_in(samples)
            )
        )
        or 0
    )
    # Sale movements are negative, and restore subtracts that quantity, which puts the units back.
    practice = int(
        db.scalar(
            select(func.coalesce(func.sum(StockMovement.quantity), 0)).where(
                StockMovement.reference_type.in_(PRACTICE_REFERENCES),
                StockMovement.product_id.not_in(samples),
            )
        )
        or 0
    )
    return on_hand - practice


def catalogue_copy(profile: str) -> tuple[str, str, str]:
    """Title, explanation, and action for the catalogue step. Profile keys come from the module registry."""
    if profile in FOOD_AND_BEVERAGE:
        return (
            "Add your first menu items",
            "Add menu categories, items, and prices. Modifiers, recipes, and kitchen stations stay when you go live "
            "if this store uses them. Sample items are removed at Go live.",
            "Add a menu item",
        )
    if profile == "retail_fashion":
        return (
            "Add your first products",
            "Add products, categories, sizes, colours, and prices. Sample items are removed when you go live.",
            "Add a product",
        )
    if profile == "grocery":
        return (
            "Add your first products",
            "Add products, categories, barcodes, units, and prices. Sample items are removed when you go live.",
            "Add a product",
        )
    if profile == "electronics_wholesale":
        return (
            "Add your first products",
            "Add products, SKUs, and prices. Stock import and serial numbers stay on the inventory pages when that "
            "module is included. Sample items are removed when you go live.",
            "Add a product",
        )
    return (
        "Add your first products",
        "Prepare the catalogue your team will sell. Sample items are removed when you go live.",
        "Add a product",
    )


def _progress(row: BusinessSettings) -> dict[str, object]:
    raw = row.guided_onboarding if isinstance(row.guided_onboarding, dict) else {}
    skipped = [key for key in raw.get("skipped", []) if isinstance(key, str) and key in SKIPPABLE]
    explored = raw.get("explored_at")
    return {
        "version": ONBOARDING_VERSION,
        "explored_at": explored if isinstance(explored, str) and explored else None,
        "skipped": skipped,
    }


def _write_progress(db: Session, row: BusinessSettings, progress: dict[str, object]) -> None:
    raw = row.guided_onboarding if isinstance(row.guided_onboarding, dict) else {}
    stored: dict[str, object] = {
        "version": ONBOARDING_VERSION,
        "explored_at": progress.get("explored_at"),
        "skipped": list(progress.get("skipped") or []),
    }
    if "modifier_templates" in raw:
        stored["modifier_templates"] = raw["modifier_templates"]
    row.guided_onboarding = stored
    db.commit()


def subscription_gate(settings: Settings) -> tuple[str, str | None]:
    """Billing state, and why Go live must wait. Unbilled stores are not on this payment policy."""
    if not settings.tenancy_enabled:
        return "unbilled", None
    from app.tenancy.context import current_tenant

    ref = current_tenant()
    if ref is None:
        return "unbilled", None
    from app.console.transfers import access_state
    from app.tenancy import registry
    from app.tenancy.models import BillingTransfer

    tenant_id = uuid.UUID(ref.id)
    with registry.control_session(settings) as control:
        state = access_state(control, tenant_id)
        if state == "trial" and _exists(
            control,
            select(BillingTransfer.id).where(
                BillingTransfer.tenant_id == tenant_id,
                BillingTransfer.status == "pending_review",
            ),
        ):
            state = "pending_review"
    if state in {"unbilled", "active", "grace"}:
        return state, None
    if state == "pending_review":
        return state, "A receipt is waiting for review. Uploading it did not activate the subscription."
    if state == "trial":
        return (
            state,
            "Verify a subscription payment before going live. Uploading a receipt does not activate the store.",
        )
    return state, "This subscription has to be active before the store can go live."


def checklist(db: Session, settings: Settings) -> Checklist:
    row = load_settings(db)
    progress = _progress(row)
    state, blocked = subscription_gate(settings)
    label, hint, action = catalogue_copy(row.business_profile)
    register = _exists(db, select(Device.id).where(Device.revoked_at.is_(None)))
    invited = int(db.scalar(select(func.count()).select_from(User)) or 0) > 1
    invite_skipped = "invite" in progress["skipped"]
    team_hint = "Create a register, then enter its one-time key in the Windows Register. Inviting staff is optional."
    if invite_skipped:
        team_hint = "Create a register when you are ready. Staff invites can be finished later."
    elif invited:
        team_hint = "A teammate already has a login. Create a register and enter its key in the Windows Register."
    items = [
        ChecklistItem(
            key="explore",
            label="Explore your Business Portal",
            hint="Discover your dashboard, business tools, and the features available for your store.",
            done=progress["explored_at"] is not None,
            href="/dashboard",
            action="Open dashboard",
        ),
        ChecklistItem(
            key="configure",
            label="Configure your store",
            hint="Add your business details and prepare currency, tax, and receipt settings.",
            done=bool(row.legal_name and row.legal_name.strip()) and len(row.currency or "") == 3,
            href="/settings",
            action="Open store settings",
        ),
        ChecklistItem(
            key="catalogue",
            label=label,
            hint=hint,
            done=_exists(db, select(Product.id).where(Product.is_sample.is_(False))),
            href="/inventory/products",
            action=action,
        ),
        ChecklistItem(
            key="practice",
            label="Try a practice sale",
            hint=(
                "Ring up a sample item on the register. Practice sales are cleared at Go live, so they do not stay "
                "in live reports, stock, or invoice numbers."
            ),
            done=_exists(db, select(Sale.id)),
            href="/registers",
            action="Open registers",
        ),
        ChecklistItem(
            key="team",
            label="Set up your team",
            hint=team_hint,
            done=register,
            href="/registers",
            action="Set up a register",
            secondary_href="/users",
            secondary_label="Invite staff",
            skippable=not invite_skipped and not invited,
            skipped=invite_skipped,
        ),
        ChecklistItem(
            key="activate",
            label="Activate your store",
            hint=(
                "Choose a plan and activate live operations after payment is verified. "
                "Uploading a receipt does not activate the store."
            ),
            done=row.live_at is not None,
            href="#go-live",
            action="Review plans" if blocked else "Go live",
            blocked=None if row.live_at is not None else blocked,
        ),
    ]
    pending = next((item.key for item in items if not item.done), None)
    return Checklist(
        version=ONBOARDING_VERSION,
        practice_mode=row.live_at is None,
        live_at=row.live_at,
        store_name=store_name(db),
        opening_stock_units=opening_stock_units(db),
        subscription_state=state,
        next_key=pending,
        items=items,
    )


def mark_explored(db: Session, settings: Settings) -> Checklist:
    """Records that someone opened the Business Portal. Signup alone does not complete this step."""
    row = load_settings(db)
    progress = _progress(row)
    if progress["explored_at"] is None:
        progress["explored_at"] = datetime.now(UTC).isoformat()
        _write_progress(db, row, progress)
    return checklist(db, settings)


def skip_optional(db: Session, key: str, settings: Settings) -> Checklist:
    if key not in SKIPPABLE:
        raise ApiError(422, "invalid_step", "That step cannot be skipped.")
    row = load_settings(db)
    progress = _progress(row)
    skipped = list(progress["skipped"])
    if key not in skipped:
        skipped.append(key)
        progress["skipped"] = skipped
        _write_progress(db, row, progress)
    return checklist(db, settings)


def _restore_practice_stock(db: Session, sample_ids: set[uuid.UUID]) -> None:
    """Puts back what practice sales and returns did to real products' stock, then forgets the movements."""
    movements = list(db.scalars(select(StockMovement).where(StockMovement.reference_type.in_(PRACTICE_REFERENCES))))
    touched_serials: set[uuid.UUID] = set()
    for movement in movements:
        if movement.product_id in sample_ids:
            continue
        level = db.scalar(
            select(InventoryLevel).where(
                InventoryLevel.product_id == movement.product_id, InventoryLevel.store_id == movement.store_id
            )
        )
        if level is not None:
            level.quantity_on_hand -= movement.quantity
        if movement.serial_number_id is not None:
            touched_serials.add(movement.serial_number_id)
    movement_ids = [movement.id for movement in movements]
    batches: set[uuid.UUID] = set()
    for allocation in db.scalars(
        select(BatchAllocation).where(
            BatchAllocation.stock_movement_id.in_(movement_ids) | BatchAllocation.sale_item_id.is_not(None)
        )
    ):
        item = db.get(BatchItem, allocation.batch_item_id)
        if item is not None and item.product_id not in sample_ids:
            item.quantity_remaining = min(
                item.quantity_imported, item.quantity_remaining + allocation.quantity - allocation.quantity_returned
            )
            batches.add(item.batch_id)
        db.delete(allocation)
    db.flush()
    if movement_ids:
        db.execute(delete(StockMovement).where(StockMovement.id.in_(movement_ids)))
    for serial_id in touched_serials:
        serial = db.get(SerialNumber, serial_id)
        if serial is None or serial.product_id in sample_ids:
            continue
        received = _exists(db, select(StockMovement.id).where(StockMovement.serial_number_id == serial.id))
        if received or serial.batch_item_id is not None:
            serial.status = "in_stock"
    db.execute(update(InventoryLevel).values(quantity_reserved=0))
    db.execute(update(SerialNumber).where(SerialNumber.status == "reserved").values(status="in_stock"))
    if batches:
        batch_ledger.refresh_status(db, batches)


def _delete_operational_history(db: Session) -> None:
    """Practice documents that are not master data: orders, bills, counts, repairs, payroll runs, and the rest.

    Suppliers, bank accounts, promotions, price lists, employee profiles, terminals and delivery channels stay.
    Sync idempotency rows stay too, so a till retry of a practice sale is a duplicate instead of a new live sale.
    """
    for model in (
        ChannelPayout,
        ReplenishmentSuggestion,
        ReplenishmentRun,
        DemandDaily,
        ConsignmentSettlementLine,
        ConsignmentSettlement,
        SupplierPaymentAllocation,
        SupplierPayment,
        BankStatementLine,
        PettyCashEntry,
        Expense,
        BankStatement,
        SupplierBillLine,
        SupplierBill,
        StockTransferSerial,
        StockTransferLine,
        StockTransfer,
        StockCountLine,
        StockCount,
        RepairAttachment,
        RepairDeposit,
        RepairEvent,
        RepairLine,
        RepairTicket,
        TradeIn,
        PayrollLine,
        PayrollRun,
        TimeEntry,
        DeliveryNoteLine,
        DeliveryNote,
        PickListLine,
        PickList,
        SalesOrderLine,
        SalesOrder,
        GoodsReceiptLine,
        GoodsReceipt,
        PurchaseOrderLine,
        PurchaseOrder,
    ):
        db.execute(delete(model))


def _delete_practice_transactions(db: Session) -> int:
    sales = int(db.scalar(select(func.count()).select_from(Sale)) or 0)
    _delete_operational_history(db)
    for model in (
        # Restaurant practice: kitchen tickets, ingredient draws and tabs go before the sales that paid them.
        KitchenTicketItem,
        KitchenTicket,
        RecipeUsage,
        OpenOrderItem,
        OpenOrder,
        PromotionRedemption,
        StoreCreditRedemption,
        LoyaltyEntry,
        WarrantyRegistration,
        PaymentRefund,
        PaymentIntent,
        ChequeEvent,
        Cheque,
        CustomerLedgerEntry,
        ReturnTender,
        ReturnItem,
        StoreCredit,
        SaleReturn,
        QuotePayment,
        SaleTender,
        SaleItem,
        Sale,
        CashMovement,
        RegisterShift,
        JournalLine,
        JournalEntry,
        ApprovalRequest,
        OutboundMessage,
        EInvoice,
        EInvoiceChain,
        # Practice signing keys must not continue into live invoices. The TRN itself stays on the settings row.
        TaxAuthorityCredential,
    ):
        db.execute(delete(model))
    db.execute(
        update(Customer).values(
            current_balance_cents=0,
            loyalty_points=0,
            credit_hold=False,
            credit_hold_reason=None,
            credit_hold_manual=False,
        )
    )
    db.execute(update(DocumentSequence).values(last_value=0, gaps=0))
    return sales


def _delete_sample_menu(db: Session, ids: list[uuid.UUID]) -> None:
    """Meals, modifier links, sample modifier groups and recipes of the sample menu. The floor plan, kitchen
    stations and categories stay: they are the store's real layout."""
    sample_slots = select(ComboSlot.id).where(ComboSlot.product_id.in_(ids))
    db.execute(
        delete(ComboSlotOption).where(ComboSlotOption.slot_id.in_(sample_slots) | ComboSlotOption.product_id.in_(ids))
    )
    db.execute(delete(ComboSlot).where(ComboSlot.product_id.in_(ids)))
    db.execute(delete(ProductModifierGroup).where(ProductModifierGroup.product_id.in_(ids)))
    groups = select(ModifierGroup.id).where(ModifierGroup.is_sample.is_(True))
    db.execute(delete(ProductModifierGroup).where(ProductModifierGroup.group_id.in_(groups)))
    sample_options = select(ModifierOption.id).where(ModifierOption.group_id.in_(groups))
    db.execute(
        delete(ModifierIngredient).where(
            ModifierIngredient.option_id.in_(sample_options) | ModifierIngredient.ingredient_id.in_(ids)
        )
    )
    db.execute(delete(ModifierOption).where(ModifierOption.group_id.in_(groups)))
    db.execute(delete(ModifierGroup).where(ModifierGroup.is_sample.is_(True)))
    recipes = select(Recipe.id).where(Recipe.product_id.in_(ids))
    db.execute(delete(RecipeLine).where(RecipeLine.recipe_id.in_(recipes) | RecipeLine.ingredient_id.in_(ids)))
    db.execute(delete(Recipe).where(Recipe.product_id.in_(ids)))


def _delete_samples(db: Session, sample_ids: set[uuid.UUID]) -> tuple[int, int]:
    ids = list(sample_ids)
    if ids:
        sample_movements = select(StockMovement.id).where(StockMovement.product_id.in_(ids))
        db.execute(delete(BatchAllocation).where(BatchAllocation.stock_movement_id.in_(sample_movements)))
        db.execute(delete(StockMovement).where(StockMovement.product_id.in_(ids)))
        sample_serials = select(SerialNumber.id).where(SerialNumber.product_id.in_(ids))
        db.execute(delete(StockTransferSerial).where(StockTransferSerial.serial_number_id.in_(sample_serials)))
        db.execute(update(TradeIn).where(TradeIn.resale_product_id.in_(ids)).values(store_credit_id=None))
        db.execute(delete(TradeIn).where(TradeIn.product_id.in_(ids) | TradeIn.resale_product_id.in_(ids)))
        db.execute(delete(SerialNumber).where(SerialNumber.product_id.in_(ids)))
        for model in (
            InventoryLevel,
            ProductPrice,
            StockCountLine,
            StockTransferLine,
            RepairLine,
            GoodsReceiptLine,
            PurchaseOrderLine,
            ConsignmentSettlementLine,
            DemandDaily,
            ReplenishmentSuggestion,
            WarrantyPlan,
            WarrantyPolicy,
            MarginPolicy,
        ):
            db.execute(delete(model).where(model.product_id.in_(ids)))
        db.execute(update(SupplierBillLine).where(SupplierBillLine.product_id.in_(ids)).values(product_id=None))
        _delete_sample_menu(db, ids)
        sample_items = select(BatchItem.id).where(BatchItem.product_id.in_(ids))
        db.execute(delete(BatchAllocation).where(BatchAllocation.batch_item_id.in_(sample_items)))
        db.execute(delete(BatchItem).where(BatchItem.product_id.in_(ids)))
        db.execute(delete(Product).where(Product.id.in_(ids)))
    customers = [row for row in db.scalars(select(Customer.id).where(Customer.is_sample.is_(True)))]
    if customers:
        db.execute(update(RepairTicket).where(RepairTicket.customer_id.in_(customers)).values(customer_id=None))
        db.execute(update(TradeIn).where(TradeIn.customer_id.in_(customers)).values(customer_id=None))
        db.execute(delete(Customer).where(Customer.id.in_(customers)))
    return len(ids), len(customers)


def _reset_opening_stock(db: Session) -> None:
    """Zero on-hand for a physical count. Reorder levels and shelf locations stay on the inventory rows."""
    db.execute(delete(BatchAllocation))
    db.execute(delete(StockMovement))
    db.execute(delete(SerialNumber))
    db.execute(delete(BatchItem))
    db.execute(delete(PurchaseBatch))
    db.execute(update(InventoryLevel).values(quantity_on_hand=0, quantity_reserved=0))


def _delete_configuration(db: Session, keeper_id: uuid.UUID) -> None:
    """Start fresh: drop the practice catalog, layout, registers and staff, and keep the confirming admin."""
    for model in (
        ModifierIngredient,
        RecipeLine,
        Recipe,
        ComboSlotOption,
        ComboSlot,
        ProductModifierGroup,
        ModifierOption,
        ModifierGroup,
        PriceChange,
        ScheduledPriceChangeLine,
        ScheduledPriceChange,
        PriceListItem,
        PriceList,
        WarrantyPlan,
        WarrantyPolicy,
        MarginPolicy,
        ProductPrice,
        InventoryLevel,
        ProductImage,
        Product,
        ProductModel,
        MarkdownEvent,
        SeasonalEvent,
        Promotion,
        ImportMappingTemplate,
        Supplier,
        DiningTable,
        DiningArea,
        KitchenStation,
        Customer,
        CustomerGroup,
        Category,
        Brand,
        DocumentSequence,
        DeviceActivation,
        PaymentTerminal,
        Device,
    ):
        db.execute(delete(model))
    kept = _primary_store(db)
    if kept is not None:
        db.execute(update(DeliveryChannel).where(DeliveryChannel.store_id != kept.id).values(store_id=kept.id))
        db.execute(delete(Store).where(Store.id != kept.id))
    db.execute(update(ExchangeRate).values(created_by_id=keeper_id))
    db.execute(update(DeliveryChannel).values(created_by_id=keeper_id))
    settings = db.scalar(select(BusinessSettings))
    if settings is not None and settings.updated_by_id != keeper_id:
        settings.updated_by_id = keeper_id
    db.flush()
    db.execute(delete(EmployeeProfile).where(EmployeeProfile.user_id != keeper_id))
    referenced = set(db.scalars(select(AuditLog.user_id).where(AuditLog.user_id.is_not(None))))
    referenced.update(id for id in db.scalars(select(AuditLog.approver_id).where(AuditLog.approver_id.is_not(None))))
    referenced.discard(keeper_id)
    if referenced:
        db.execute(
            update(User)
            .where(User.id.in_(referenced))
            .values(is_active=False, has_portal_access=False, has_pos_access=False, hashed_pin=None)
        )
    removable = select(User.id).where(User.id != keeper_id)
    if referenced:
        removable = removable.where(User.id.not_in(referenced))
    db.execute(delete(User).where(User.id.in_(removable)))


def go_live(
    db: Session,
    principal: Principal,
    payload: GoLiveRequest,
    *,
    settings: Settings,
    payment_verified: bool = False,
) -> GoLiveResult:
    """Takes the store live. A trial cannot skip payment unless the caller just verified it in this transaction."""
    row = load_settings(db, lock=True)
    if row.live_at is not None:
        raise ApiError(409, "already_live", "This store is already live.")
    if principal.user is None or principal.store_id is not None:
        raise ApiError(403, "business_wide_only", "Only a business-wide admin can take the store live.")
    if not payment_verified:
        _state, reason = subscription_gate(settings)
        if reason is not None:
            raise ApiError(409, "subscription_unverified", reason)
    if not payload.tax_acknowledged:
        raise ApiError(422, "tax_not_acknowledged", "Confirm that practice tax stamps will be removed.")
    if payload.mode == "keep" and payload.opening_stock not in ("keep", "reset"):
        raise ApiError(422, "opening_stock_required", "Choose whether to keep opening stock or reset it to zero.")
    expected = store_name(db)
    if payload.confirm.strip().lower() != expected.strip().lower():
        raise ApiError(422, "confirm_mismatch", f'Type the store name "{expected}" to confirm.')
    opening_stock = "reset" if payload.mode == "fresh" else payload.opening_stock
    assert opening_stock is not None
    sample_ids = set(db.scalars(select(Product.id).where(Product.is_sample.is_(True))))
    _restore_practice_stock(db, sample_ids)
    sales = _delete_practice_transactions(db)
    products, customers = _delete_samples(db, sample_ids)
    if opening_stock == "reset":
        _reset_opening_stock(db)
    if payload.mode == "fresh":
        _delete_configuration(db, principal.user.id)
        row.onboarded_at = None
        progress = dict(row.guided_onboarding) if isinstance(row.guided_onboarding, dict) else {}
        progress.pop("modifier_templates", None)
        row.guided_onboarding = progress
    from app.services.menu_service import ensure_default_groups

    ensure_default_groups(db, commit=False)
    row.live_at = datetime.now(UTC)
    row.promoted_from_practice = True
    db.commit()
    return GoLiveResult(
        live_at=row.live_at,
        mode=payload.mode,
        opening_stock=opening_stock,
        sales_removed=sales,
        sample_products_removed=products,
        sample_customers_removed=customers,
    )
