"""Reconciles one production demo after seeding. Every check reads what the business services wrote."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.batch import BatchItem, PurchaseBatch
from app.models.customer import Customer, CustomerLedgerEntry
from app.models.inventory import InventoryLevel, StockMovement
from app.models.menu import ModifierGroup
from app.models.product import Product
from app.models.restaurant import DiningTable, OpenOrder, OpenOrderItem
from app.models.sale import Sale
from app.models.sale_return import SaleReturn
from app.models.serial_number import SerialNumber
from app.models.warranty import WarrantyRegistration
from app.services import weighed
from app.services.settings_service import cached_settings
from app.services.tax import entered_includes_tax, line_tax
from app.services.tax import policy as tax_policy

_GATEWAY = frozenset({"card", "bnpl", "qr"})


def _check(checks: list[dict], name: str, ok: bool, detail: str = "") -> None:
    checks.append({"name": name, "ok": ok, "detail": detail})


def validate_demo(db: Session, spec: dict) -> dict:
    checks: list[dict] = []
    settings = cached_settings(db)
    expected = set(settings.capabilities)
    _check(checks, "profile", settings.business_profile == spec["profile"], settings.business_profile or "")
    _check(checks, "currency", settings.currency == spec["currency"], settings.currency)
    if spec["code"] == "electronics":
        _check(checks, "b2b_credit", "b2b_credit" in expected)
    else:
        _check(checks, "no_b2b_credit", "b2b_credit" not in expected)
    _stock(db, checks)
    _sales(db, checks)
    _returns(db, checks)
    _ledger(db, checks, spec)
    _shape(db, checks, spec)
    return {"code": spec["code"], "slug": spec["slug"], "ok": all(check["ok"] for check in checks), "checks": checks}


def _stock(db: Session, checks: list[dict]) -> None:
    mismatched = []
    for level in db.scalars(select(InventoryLevel)).all():
        moved = int(
            db.scalar(
                select(func.coalesce(func.sum(StockMovement.quantity), 0)).where(
                    StockMovement.product_id == level.product_id,
                    StockMovement.store_id == level.store_id,
                )
            )
            or 0
        )
        if moved != level.quantity_on_hand:
            mismatched.append(str(level.product_id))
    _check(checks, "stock", not mismatched, f"{len(mismatched)} products")


def _sales(db: Session, checks: list[dict]) -> None:
    sales = list(db.scalars(select(Sale).options(selectinload(Sale.items), selectinload(Sale.tenders))).all())
    totals = tax = payments = gateway = 0
    for sale in sales:
        net = sum(item.line_total_cents - item.tax_cents for item in sale.items)
        if sale.subtotal_cents != net + (sale.service_charge_cents or 0):
            totals += 1
        if sale.tax_cents != sum(item.tax_cents for item in sale.items) + (sale.service_charge_tax_cents or 0):
            totals += 1
        if sale.total_cents != sale.subtotal_cents + sale.tax_cents:
            totals += 1
        if sale.amount_paid_cents + sale.due_balance_cents != sale.total_cents:
            payments += 1
        tender_sum = sum(tender.amount_cents for tender in sale.tenders)
        if tender_sum != sale.total_cents + (sale.tip_cents or 0):
            payments += 1
        if any(tender.method in _GATEWAY for tender in sale.tenders):
            gateway += 1
        rule = tax_policy(db, sale.store_id)
        for item in sale.items:
            product = db.get(Product, item.product_id)
            if product is None:
                tax += 1
                continue
            charged = (
                weighed.amount(item.quantity, item.unit_price_cents, weighed.scale_of(product))
                - int(item.discount_cents or 0)
                - int(item.manual_discount_cents or 0)
            )
            if rule.enforced:
                priced = line_tax(
                    charged, 1, rule.rate_for(product.tax_category), inclusive=entered_includes_tax(product)
                )
                if item.tax_cents != priced.tax_cents or item.line_total_cents != priced.line_total_cents:
                    tax += 1
            elif item.line_total_cents != charged or item.tax_cents:
                tax += 1
        if (sale.service_charge_cents or 0) and rule.enforced:
            expected = line_tax(sale.service_charge_cents, 1, rule.standard_rate_bps, inclusive=False).tax_cents
            if (sale.service_charge_tax_cents or 0) != expected:
                tax += 1
    _check(checks, "sale_count", len(sales) >= 30, str(len(sales)))
    _check(checks, "sale_totals", totals == 0, str(totals))
    _check(checks, "tax", tax == 0, str(tax))
    _check(checks, "payments", payments == 0, str(payments))
    _check(checks, "no_gateway_tender", gateway == 0, str(gateway))


def _returns(db: Session, checks: list[dict]) -> None:
    broken = 0
    found = 0
    for row in db.scalars(select(SaleReturn).options(selectinload(SaleReturn.tenders))).all():
        found += 1
        if sum(tender.amount_cents for tender in row.tenders) != row.total_refund_cents:
            broken += 1
        restocked = db.scalar(
            select(StockMovement.id).where(
                StockMovement.reference_type == "sale_return",
                StockMovement.reference_id == row.id,
                StockMovement.quantity > 0,
            )
        )
        if restocked is None:
            broken += 1
    _check(checks, "returns", found >= 1 and broken == 0, f"{found} returns, {broken} broken")


def _ledger(db: Session, checks: list[dict], spec: dict) -> None:
    broken = []
    outstanding = 0
    for customer in db.scalars(select(Customer)).all():
        latest = db.scalar(
            select(CustomerLedgerEntry)
            .where(CustomerLedgerEntry.customer_id == customer.id)
            .order_by(CustomerLedgerEntry.created_at.desc(), CustomerLedgerEntry.id.desc())
        )
        expected = 0 if latest is None else latest.balance_after_cents
        if expected != customer.current_balance_cents:
            broken.append(customer.name)
        if customer.customer_type == "WHOLESALE":
            outstanding = customer.current_balance_cents
    _check(checks, "ledger", not broken, ", ".join(broken))
    if spec["code"] == "electronics":
        _check(checks, "electronics_balance", outstanding > 0, str(outstanding))


def _shape(db: Session, checks: list[dict], spec: dict) -> None:
    products = list(db.scalars(select(Product)).all())
    skus = [product.sku for product in products]
    barcodes = [product.barcode for product in products]
    _check(checks, "sku_unique", len(skus) == len(set(skus)))
    _check(checks, "barcode_unique", len(barcodes) == len(set(barcodes)))
    if spec["code"] == "restaurant":
        orders = list(db.scalars(select(OpenOrder)).all())
        kinds = {order.service_type for order in orders}
        open_dine = [order.table_id for order in orders if order.status == "OPEN" and order.service_type == "DINE_IN"]
        sent = db.scalar(select(func.count()).select_from(OpenOrderItem).where(OpenOrderItem.sent_at.is_not(None)))
        tables = db.scalar(select(func.count()).select_from(DiningTable)) or 0
        group = db.scalar(select(ModifierGroup.id).where(ModifierGroup.name == spec["modifier"]["group"]))
        _check(checks, "service_types", {"DINE_IN", "TAKEAWAY", "DELIVERY"} <= kinds, ",".join(sorted(kinds)))
        _check(checks, "one_open_table", len(open_dine) == len(set(open_dine)) and len(open_dine) == 1)
        _check(checks, "kitchen", int(sent or 0) >= 3, str(sent or 0))
        _check(checks, "tables", int(tables) >= 4, str(tables))
        _check(checks, "modifiers", group is not None)
    if spec["code"] == "supermarket":
        banana = next((product for product in products if product.sku == "GRO-BANANA"), None)
        soon = _lot(db, "GRO-MILK-SOON")
        later = _lot(db, "GRO-MILK-LATER")
        _check(
            checks,
            "plu",
            banana is not None and banana.sold_by_weight and banana.plu_code == "4011",
        )
        _check(
            checks,
            "fefo",
            soon is not None
            and later is not None
            and soon.quantity_remaining < soon.quantity_imported
            and later.quantity_remaining == later.quantity_imported,
            ""
            if soon is None or later is None
            else f"soon {soon.quantity_remaining}/{soon.quantity_imported}, later {later.quantity_remaining}",
        )
    if spec["code"] == "electronics":
        serials = db.scalar(select(func.count()).select_from(SerialNumber)) or 0
        covers = db.scalar(select(func.count()).select_from(WarrantyRegistration)) or 0
        _check(checks, "serials", int(serials) >= 3, str(serials))
        _check(checks, "warranties", int(covers) >= 1, str(covers))
    if spec["code"] == "fashion":
        variants = [product for product in products if product.variant_attributes]
        sized = [
            product
            for product in variants
            if {"size", "color"} <= set(product.variant_attributes) and product.product_model_id is not None
        ]
        _check(checks, "variants", len(sized) == 4, str(len(sized)))


def _lot(db: Session, number: str) -> BatchItem | None:
    return db.scalar(
        select(BatchItem)
        .join(PurchaseBatch, PurchaseBatch.id == BatchItem.batch_id)
        .where(PurchaseBatch.batch_number == number)
    )
