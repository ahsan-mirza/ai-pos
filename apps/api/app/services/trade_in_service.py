"""Trade-ins: buying used devices at the register, stocking them as pre-owned SKUs, and paying the seller in
cash, store credit, or credit on the sale they are making."""

from __future__ import annotations

import secrets
import string
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import Principal
from app.core.errors import ApiError, SyncRejected
from app.core.permissions import Permission
from app.core.security import decrypt_value, encrypt_value
from app.models.batch import BatchItem, PurchaseBatch
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.serial_number import SerialNumber
from app.models.store import Store
from app.models.store_credit import StoreCredit
from app.models.trade_in import TradeIn
from app.models.user import User
from app.schemas.trade_ins import (
    TradeInCheck,
    TradeInChecklist,
    TradeInCheckOut,
    TradeInCreate,
    TradeInList,
    TradeInOut,
)
from app.services import warranty_service
from app.services.identifiers import identifier_hash, identifier_suffix, normalize_identifier
from app.services.inventory import transition_serial
from app.services.numbering import next_server_number
from app.services.settings_service import business_currency

REFERENCE = "trade_in"
GRADE_LABELS = {"A": "Grade A", "B": "Grade B", "C": "Grade C", "D": "Faulty"}
BLOCKING = {
    "in_stock": "is already in stock",
    "reserved": "is reserved on a quote",
    "in_transit": "is in transit between branches",
    "repair": "is booked in for repair",
    "defective": "is recorded as defective stock",
    "quarantine": "is in quarantine",
}
CODE_ALPHABET = string.ascii_uppercase + string.digits


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _identify(kind: str, value: str) -> tuple[str, str]:
    try:
        normalized = normalize_identifier(kind, value)
    except SyncRejected as exc:
        raise ApiError(422, "identifier_invalid", exc.message) from exc
    return normalized, identifier_hash(normalized)


def check(db: Session, data: TradeInCheck) -> TradeInCheckOut:
    normalized, digest = _identify(data.kind, data.value)
    serial = db.scalar(select(SerialNumber).where(SerialNumber.value_hash == digest))
    if serial is not None and serial.status in BLOCKING:
        return TradeInCheckOut(ok=False, message=f"{normalized} {BLOCKING[serial.status]}; it cannot be bought in.")
    if serial is None:
        return TradeInCheckOut(ok=True, message="Not seen before. Check the unit is not reported lost or stolen.")
    sold = db.execute(
        select(Sale.created_at, Product.name)
        .join(SaleItem, SaleItem.sale_id == Sale.id)
        .join(Product, Product.id == SaleItem.product_id)
        .where(SaleItem.serial_number_id == serial.id)
        .order_by(Sale.created_at.desc())
        .limit(1)
    ).first()
    registration = warranty_service.registration_for_identifier(db, digest)
    return TradeInCheckOut(
        ok=True,
        message="Sold by us before: a buyback." if sold else "Known unit, not in stock.",
        sold_here_at=_aware(sold[0]) if sold else None,
        sold_as=sold[1] if sold else None,
        warranty_status=warranty_service.status_of(registration) if registration else None,
    )


def _cashier(db: Session, principal: Principal, data: TradeInCreate) -> User:
    if principal.store_id is not None and principal.store_id != data.store_id:
        raise ApiError(403, "store_scope", "This register belongs to another branch.")
    cashier = db.get(User, data.cashier_id)
    if cashier is None:
        raise ApiError(404, "not_found", "Cashier was not found.")
    if Permission.POS_TRADE_IN.value not in cashier.permissions:
        raise ApiError(403, "forbidden", f"{cashier.full_name} cannot buy trade-ins.")
    if cashier.store_id is not None and cashier.store_id != data.store_id:
        raise ApiError(403, "store_scope", f"{cashier.full_name} works at another branch.")
    return cashier


def resale_product(db: Session, product: Product, grade: str, price_cents: int) -> Product:
    """The pre-owned SKU for a model and grade, created on first use; its price follows the latest resale price."""
    sku = f"PO-{product.sku}-{grade}"[:64]
    found = db.scalar(select(Product).where(Product.sku == sku))
    if found is not None:
        if price_cents:
            found.price_cents = price_cents
        return found
    resale = Product(
        sku=sku,
        barcode=f"PO{grade}{product.barcode}"[:64],
        name=f"Pre-owned {product.name} ({GRADE_LABELS[grade]})"[:200],
        model_number=product.model_number,
        brand=product.brand,
        brand_id=product.brand_id,
        category="Pre-owned",
        price_cents=price_cents,
        currency=product.currency,
        is_serialized=True,
        tax_category=product.tax_category,
        variant_attributes=dict(product.variant_attributes or {}),
    )
    db.add(resale)
    db.flush()
    return resale


def _voucher_code(db: Session) -> str:
    while True:
        body = "".join(secrets.choice(CODE_ALPHABET) for _ in range(12))
        code = f"SC-{body[:4]}-{body[4:8]}-{body[8:]}"
        if db.scalar(select(StoreCredit.id).where(StoreCredit.code == code)) is None:
            return code


def create(db: Session, settings: Settings, principal: Principal, data: TradeInCreate) -> TradeInOut:
    existing = db.get(TradeIn, data.id)
    if existing is not None:
        return trade_in_out(db, settings, existing)
    cashier = _cashier(db, principal, data)
    store = db.get(Store, data.store_id)
    if store is None:
        raise ApiError(404, "not_found", "Store was not found.")
    product = db.get(Product, data.product_id)
    if product is None or not product.is_serialized:
        raise ApiError(422, "model_required", "Choose the phone or device model from the catalog.")
    if data.payout == "SALE_CREDIT" and data.offer_cents == 0:
        raise ApiError(422, "offer_required", "A zero offer cannot be credited to a sale.")
    if not data.checklist.account_removed:
        raise ApiError(
            422, "account_locked", "Ask the seller to sign out of iCloud / Google and remove the lock first."
        )
    normalized, digest = _identify(data.identifier_kind, data.identifier_value)
    serial = db.scalar(select(SerialNumber).where(SerialNumber.value_hash == digest))
    if serial is not None and serial.status in BLOCKING:
        raise ApiError(422, "identifier_in_stock", f"{normalized} {BLOCKING[serial.status]}.")

    currency = business_currency(db)
    resale = resale_product(db, product, data.grade, data.resale_price_cents)
    number = next_server_number(db, store.id, "TRD")
    batch = PurchaseBatch(
        batch_number=number[-32:],
        store_id=store.id,
        import_source="MANUAL",
        currency=currency,
        total_cost_amount=data.offer_cents,
        total_items_count=1,
        notes=f"Trade-in {number} from {data.seller_name.strip()}",
        created_by_id=cashier.id,
    )
    db.add(batch)
    db.flush()
    item = BatchItem(
        batch_id=batch.id,
        product_id=resale.id,
        store_id=store.id,
        quantity_imported=1,
        quantity_remaining=1,
        purchase_cost_per_unit=data.offer_cents,
        selling_price_per_unit=data.resale_price_cents,
    )
    db.add(item)
    db.flush()
    if serial is None:
        serial = SerialNumber(
            product_id=resale.id,
            store_id=store.id,
            kind=data.identifier_kind,
            value_hash=digest,
            value_encrypted=encrypt_value(normalized, settings),
            value_suffix=identifier_suffix(normalized),
            status="received",
        )
        db.add(serial)
    else:
        # A buyback of a unit sold here: the same serial row moves to the pre-owned SKU.
        serial.product_id = resale.id
        serial.status = "received"
    serial.batch_item_id = item.id
    db.flush()
    item.imported_serials = [str(serial.id)]
    trade_in = TradeIn(
        id=data.id,
        number=number,
        store_id=store.id,
        product_id=product.id,
        resale_product_id=resale.id,
        serial_number_id=serial.id,
        identifier_kind=data.identifier_kind,
        identifier_hash=digest,
        grade=data.grade,
        checklist=data.checklist.model_dump(),
        notes=data.notes.strip(),
        seller_name=data.seller_name.strip(),
        seller_phone=data.seller_phone.strip(),
        seller_id_encrypted=encrypt_value(data.seller_id_number.strip(), settings),
        seller_id_last4=data.seller_id_number.strip()[-4:],
        customer_id=data.customer_id,
        offer_cents=data.offer_cents,
        resale_price_cents=data.resale_price_cents,
        currency=currency,
        payout=data.payout,
        status="ACCEPTED" if data.payout == "SALE_CREDIT" else "APPLIED",
        batch_item_id=item.id,
        cashier_id=cashier.id,
    )
    db.add(trade_in)
    db.flush()
    # Faulty units go straight to the workshop instead of the shelf.
    transition_serial(
        db,
        serial,
        status="in_stock",
        store_id=store.id,
        movement_type="PURCHASE_IN",
        reference_type=REFERENCE,
        reference_id=trade_in.id,
        user_id=cashier.id,
        note=f"Trade-in {number}",
    )
    if data.grade == "D":
        transition_serial(
            db,
            serial,
            status="repair",
            store_id=store.id,
            movement_type="AUDIT_ADJUSTMENT",
            reference_type=REFERENCE,
            reference_id=trade_in.id,
            user_id=cashier.id,
            note=f"Trade-in {number} needs repair before resale",
        )
    if data.payout == "STORE_CREDIT" and data.offer_cents > 0:
        credit = StoreCredit(
            code=_voucher_code(db),
            store_id=store.id,
            return_id=None,
            currency=currency,
            initial_cents=data.offer_cents,
            balance_cents=data.offer_cents,
        )
        db.add(credit)
        db.flush()
        trade_in.store_credit_id = credit.id
    db.commit()
    return trade_in_out(db, settings, trade_in)


def consume_for_sale(
    db: Session, trade_in_id: uuid.UUID | None, *, sale_id: uuid.UUID, store_id: uuid.UUID, amount_cents: int
) -> None:
    """A sale's trade_in tender spends the credit of an ACCEPTED SALE_CREDIT trade-in, exactly once."""
    if trade_in_id is None:
        raise SyncRejected("Trade-in tenders must reference the trade-in.")
    trade_in = db.get(TradeIn, trade_in_id)
    if trade_in is None or trade_in.payout != "SALE_CREDIT":
        raise SyncRejected("The trade-in for this tender does not exist.")
    if trade_in.store_id != store_id:
        raise SyncRejected("The trade-in was taken at another branch.")
    if trade_in.status != "ACCEPTED":
        raise SyncRejected(f"Trade-in {trade_in.number} is already {trade_in.status.lower()}.")
    if amount_cents != trade_in.offer_cents:
        raise SyncRejected(f"Trade-in {trade_in.number} is worth {trade_in.offer_cents} cents, not {amount_cents}.")
    trade_in.status = "APPLIED"
    trade_in.sale_id = sale_id


def cancel(db: Session, settings: Settings, principal: Principal, trade_in_id: uuid.UUID) -> TradeInOut:
    """Only an unspent sale credit can be cancelled (the customer changed their mind before paying)."""
    trade_in = db.get(TradeIn, trade_in_id)
    if trade_in is None or (principal.store_id is not None and trade_in.store_id != principal.store_id):
        raise ApiError(404, "not_found", "Trade-in was not found.")
    if trade_in.payout != "SALE_CREDIT" or trade_in.status != "ACCEPTED":
        raise ApiError(409, "trade_in_final", "Money has already changed hands for this trade-in.")
    serial = db.get(SerialNumber, trade_in.serial_number_id)
    if serial is not None and serial.status in ("in_stock", "repair"):
        transition_serial(
            db,
            serial,
            status="reversed",
            store_id=trade_in.store_id,
            movement_type="PURCHASE_REVERSAL",
            reference_type=REFERENCE,
            reference_id=trade_in.id,
            user_id=principal.user.id if principal.user else None,
            note=f"Trade-in {trade_in.number} cancelled",
        )
    item = db.get(BatchItem, trade_in.batch_item_id) if trade_in.batch_item_id else None
    if item is not None:
        item.quantity_remaining = 0
    trade_in.status = "CANCELLED"
    db.commit()
    return trade_in_out(db, settings, trade_in)


def trade_in_out(db: Session, settings: Settings, trade_in: TradeIn) -> TradeInOut:
    product = db.get(Product, trade_in.product_id)
    resale = db.get(Product, trade_in.resale_product_id)
    store = db.get(Store, trade_in.store_id)
    serial = db.get(SerialNumber, trade_in.serial_number_id)
    credit = db.get(StoreCredit, trade_in.store_credit_id) if trade_in.store_credit_id else None
    cashier = db.get(User, trade_in.cashier_id)
    value = decrypt_value(serial.value_encrypted, settings) if serial is not None else ""
    return TradeInOut(
        id=trade_in.id,
        number=trade_in.number,
        store_id=trade_in.store_id,
        store_code=store.code if store else "",
        product_id=trade_in.product_id,
        product_name=product.name if product else "",
        resale_product_id=trade_in.resale_product_id,
        resale_sku=resale.sku if resale else "",
        identifier_kind=trade_in.identifier_kind,  # type: ignore[arg-type]
        identifier_tail=f"…{value[-4:]}" if value else "",
        grade=trade_in.grade,  # type: ignore[arg-type]
        checklist=TradeInChecklist(**trade_in.checklist),
        notes=trade_in.notes,
        seller_name=trade_in.seller_name,
        seller_phone=trade_in.seller_phone,
        seller_id_last4=trade_in.seller_id_last4,
        customer_id=trade_in.customer_id,
        offer_cents=trade_in.offer_cents,
        resale_price_cents=trade_in.resale_price_cents,
        currency=trade_in.currency,
        payout=trade_in.payout,  # type: ignore[arg-type]
        status=trade_in.status,  # type: ignore[arg-type]
        sale_id=trade_in.sale_id,
        store_credit_code=credit.code if credit else None,
        cashier_name=cashier.full_name if cashier else None,
        created_at=_aware(trade_in.created_at),
    )


def list_trade_ins(
    db: Session, settings: Settings, *, start: date, end: date, store_scope: uuid.UUID | None
) -> TradeInList:
    since = datetime.combine(start, datetime.min.time(), UTC)
    until = datetime.combine(end, datetime.max.time(), UTC)
    query = (
        select(TradeIn)
        .where(TradeIn.created_at >= since, TradeIn.created_at <= until)
        .order_by(TradeIn.created_at.desc())
        .limit(500)
    )
    if store_scope is not None:
        query = query.where(TradeIn.store_id == store_scope)
    rows = list(db.scalars(query))
    live = [row for row in rows if row.status != "CANCELLED"]
    return TradeInList(
        items=[trade_in_out(db, settings, row) for row in rows],
        bought_cents=sum(row.offer_cents for row in live),
        count=len(live),
        awaiting_sale_cents=sum(row.offer_cents for row in live if row.status == "ACCEPTED"),
    )


def period_trade_ins(db: Session, start: date, end: date, store_id: uuid.UUID | None) -> list[TradeIn]:
    since = datetime.combine(start, datetime.min.time(), UTC)
    until = datetime.combine(end, datetime.max.time(), UTC)
    query = select(TradeIn).where(
        TradeIn.created_at >= since, TradeIn.created_at <= until, TradeIn.status != "CANCELLED"
    )
    if store_id is not None:
        query = query.where(TradeIn.store_id == store_id)
    return list(db.scalars(query))
