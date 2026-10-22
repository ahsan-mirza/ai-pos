"""Practice mode for self-service stores: the "First win" checklist and the one-time Go live reset.

Go live removes every practice transaction (sales, returns, quotes, payments, shifts, ledger and journal entries)
and the sample products and customers, gives back the stock practice sales took from real products, and restarts
document numbering, so the books begin clean on the first real sale."""

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
from app.models.batch import BatchAllocation, BatchItem, PurchaseBatch
from app.models.cheque import Cheque, ChequeEvent
from app.models.consignment import ConsignmentSettlementLine
from app.models.customer import Customer, CustomerLedgerEntry
from app.models.device import Device
from app.models.document_sequence import DocumentSequence
from app.models.einvoice import EInvoice, EInvoiceChain
from app.models.inventory import InventoryLevel, StockMovement
from app.models.kitchen import KitchenTicket, KitchenTicketItem
from app.models.loyalty import LoyaltyEntry
from app.models.margin import MarginPolicy
from app.models.menu import ComboSlot, ComboSlotOption, ModifierGroup, ModifierOption, ProductModifierGroup
from app.models.messaging import OutboundMessage
from app.models.payables import SupplierBillLine
from app.models.payment_intent import PaymentIntent
from app.models.product import Product
from app.models.product_price import ProductPrice
from app.models.promotion import PromotionRedemption
from app.models.purchasing import GoodsReceiptLine, PurchaseOrderLine
from app.models.quote_payment import QuotePayment
from app.models.recipe import ModifierIngredient, Recipe, RecipeLine, RecipeUsage
from app.models.repair_ticket import RepairLine, RepairTicket
from app.models.replenishment import DemandDaily, ReplenishmentSuggestion
from app.models.restaurant import OpenOrder, OpenOrderItem
from app.models.return_item import ReturnItem
from app.models.return_tender import ReturnTender
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sale_return import SaleReturn
from app.models.sale_tender import SaleTender
from app.models.serial_number import SerialNumber
from app.models.shift import CashMovement, RegisterShift
from app.models.stock_count import StockCountLine
from app.models.store import Store
from app.models.store_credit import StoreCredit, StoreCreditRedemption
from app.models.sync_event import SyncEvent
from app.models.trade_in import TradeIn
from app.models.transfer import StockTransferLine, StockTransferSerial
from app.models.user import User
from app.models.warranty import WarrantyPlan, WarrantyPolicy, WarrantyRegistration
from app.schemas.onboarding import Checklist, ChecklistItem, GoLiveResult
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
    store = db.scalar(select(Store).where(Store.is_warehouse.is_(False)).order_by(Store.created_at).limit(1))
    return store.name if store else "My store"


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
        practice_mode=settings.live_at is None, live_at=settings.live_at, store_name=store_name(db), items=items
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


def _delete_practice_transactions(db: Session) -> int:
    sales = int(db.scalar(select(func.count()).select_from(Sale)) or 0)
    db.execute(update(RepairTicket).values(sale_id=None, warranty_registration_id=None))
    db.execute(update(TradeIn).values(sale_id=None, store_credit_id=None))
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
        SyncEvent,
        OutboundMessage,
        EInvoice,
        EInvoiceChain,
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


def go_live(db: Session, principal: Principal, confirm: str) -> GoLiveResult:
    settings = load_settings(db, lock=True)
    if settings.live_at is not None:
        raise ApiError(409, "already_live", "This store is already live.")
    if principal.store_id is not None:
        raise ApiError(403, "business_wide_only", "Only a business-wide admin can take the store live.")
    expected = store_name(db)
    if confirm.strip().lower() != expected.strip().lower():
        raise ApiError(422, "confirm_mismatch", f'Type the store name "{expected}" to confirm.')
    sample_ids = set(db.scalars(select(Product.id).where(Product.is_sample.is_(True))))
    _restore_practice_stock(db, sample_ids)
    sales = _delete_practice_transactions(db)
    products, customers = _delete_samples(db, sample_ids)
    settings.live_at = datetime.now(UTC)
    db.commit()
    return GoLiveResult(
        live_at=settings.live_at,
        sales_removed=sales,
        sample_products_removed=products,
        sample_customers_removed=customers,
    )
