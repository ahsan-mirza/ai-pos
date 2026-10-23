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


def checklist(db: Session) -> Checklist:
    settings = load_settings(db)
    serials = settings.business_profile == "electronics_wholesale"
    food = settings.business_profile in FOOD_AND_BEVERAGE
    items = [
        ChecklistItem(
            key="test_sale",
            label="Ring up a test sale",
            hint="Open the register and sell a sample item; practice sales are wiped when you go live.",
            done=_exists(db, select(Sale.id)),
            href="/registers",
        ),
        ChecklistItem(
            key="real_product",
            label="Add your first real menu item" if food else "Add your first real product",
            hint=(
                "The sample menu and meals are removed at Go live; your floor plan and kitchen stations stay."
                if food
                else "Sample items are marked and removed at Go live."
            ),
            done=_exists(db, select(Product.id).where(Product.is_sample.is_(False))),
            href="/inventory/products",
        ),
    ]
    if serials:
        items.append(
            ChecklistItem(
                key="import_stock",
                label="Import your stock list",
                hint="Upload a supplier invoice or Excel sheet; IMEIs come in with it.",
                done=_exists(db, select(PurchaseBatch.id)),
                href="/inventory/batches",
            )
        )
    items += [
        ChecklistItem(
            key="till",
            label="Set up your till",
            hint="Create a register here, then enter its one-time key in the AI POS app on the till PC.",
            done=_exists(db, select(Device.id).where(Device.revoked_at.is_(None))),
            href="/registers",
        ),
        ChecklistItem(
            key="cashier",
            label="Invite a cashier",
            hint="Give each person their own login and PIN.",
            done=int(db.scalar(select(func.count()).select_from(User)) or 0) > 1,
            href="/users",
        ),
        ChecklistItem(
            key="go_live",
            label="Go live",
            hint="Clears practice sales and sample items and restarts invoice numbering.",
            done=settings.live_at is not None,
            href="#go-live",
        ),
    ]
    return Checklist(
        practice_mode=settings.live_at is None,
        live_at=settings.live_at,
        store_name=store_name(db),
        opening_stock_units=opening_stock_units(db),
        items=items,
    )


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


def go_live(db: Session, principal: Principal, payload: GoLiveRequest) -> GoLiveResult:
    settings = load_settings(db, lock=True)
    if settings.live_at is not None:
        raise ApiError(409, "already_live", "This store is already live.")
    if principal.user is None or principal.store_id is not None:
        raise ApiError(403, "business_wide_only", "Only a business-wide admin can take the store live.")
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
        settings.onboarded_at = None
    settings.live_at = datetime.now(UTC)
    settings.promoted_from_practice = True
    db.commit()
    return GoLiveResult(
        live_at=settings.live_at,
        mode=payload.mode,
        opening_stock=opening_stock,
        sales_removed=sales,
        sample_products_removed=products,
        sample_customers_removed=customers,
    )
