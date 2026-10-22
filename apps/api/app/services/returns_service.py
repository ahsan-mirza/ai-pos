import re
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.errors import ApiError, SyncRejected
from app.core.permissions import Permission
from app.core.returns_policy import MAX_CLOCK_SKEW_SECONDS, OVERRIDE_FLAG_THRESHOLD
from app.core.security import decrypt_value
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.product import Product
from app.models.return_item import ReturnItem
from app.models.return_tender import ReturnTender
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sale_return import SaleReturn
from app.models.serial_number import SerialNumber
from app.models.store_credit import StoreCredit
from app.models.user import User
from app.schemas.payloads import (
    CashierReturnRow,
    ConditionSlice,
    OverrideLogRow,
    ReceiptItemOut,
    ReceiptOut,
    ReturnConditionOut,
    ReturnedProductRow,
    ReturnItemOut,
    ReturnOut,
    ReturnPayload,
    ReturnPolicyOut,
    ReturnReasonOut,
    ReturnsAnalytics,
    ReturnTenderOut,
    TenderSlice,
)
from app.schemas.pos_policy import ReturnsPolicy
from app.services import (
    audit,
    batch_ledger,
    combo_service,
    integrated_payment_service,
    loyalty_service,
    recipe_service,
    warranty_service,
    weighed,
)
from app.services.analytics_service import load_sales, period_edges, period_start
from app.services.identifiers import identifier_hash, normalize_identifier
from app.services.inventory import move_stock, transition_serial
from app.services.settings_service import pos_policy
from app.services.sync_validation import parse_payload, require_cashier, require_store

OVERRIDE_ACTION = "return.override"
RETURNABLE_SALE_STATUSES = frozenset({"completed", "partially_refunded"})
# Refunds go back the way the customer paid, or to store credit. Cash-for-card is the classic refund fraud.
ALLOWED_TENDERS: dict[str, frozenset[str]] = {
    "cash": frozenset({"cash", "store_credit"}),
    "card": frozenset({"original_card", "store_credit"}),
    "transfer": frozenset({"store_credit"}),
    "store_credit": frozenset({"store_credit"}),
    "gift_card": frozenset({"store_credit"}),
    "bnpl": frozenset({"original_bnpl", "store_credit"}),
}
TENDER_LABELS = {
    "cash": "Cash",
    "original_card": "Card",
    "original_bnpl": "the pay-later provider",
    "store_credit": "Store credit",
}
RECEIPT_CODE = re.compile(r"[A-Za-z0-9-]{8,64}")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def returns_policy(db: Session) -> ReturnsPolicy:
    return pos_policy(db).returns


def policy_out(db: Session) -> ReturnPolicyOut:
    policy = returns_policy(db)
    open_box = policy.condition("open_box")
    return ReturnPolicyOut(
        window_days=policy.window_days,
        exchange_window_days=policy.exchange_window_days,
        open_box_fee_bps=open_box.fee_bps if open_box is not None else 0,
        serial_status_by_condition={condition.key: condition.serial_status for condition in policy.conditions},
        preset=policy.preset,
        conditions=[ReturnConditionOut(**condition.model_dump()) for condition in policy.conditions],
        reasons=[ReturnReasonOut(**reason.model_dump()) for reason in policy.reasons],
    )


# --- Pricing rules (mirrored in apps/desktop/src/features/returns/returnMath.ts) -------------------


def _made_to_order(db: Session, product_id: uuid.UUID) -> bool:
    """A dish made from a recipe, or a meal served from its parts, is never restocked."""
    return bool(recipe_service.recipe_product_ids(db, {product_id}) or combo_service.combo_ids(db, {product_id}))


def restocking_fee(unit_price_cents: int, quantity: int, fee_bps: int, scale: int = 1) -> int:
    if not fee_bps:
        return 0
    return (weighed.amount(quantity, unit_price_cents, scale) * fee_bps + 5_000) // 10_000


def discount_share(discount_cents: int, item_quantity: int, quantity: int, prior_quantity: int) -> int:
    """Part of a line's discounts (promotion plus cashier) that `quantity` returned units carry; cumulative rounding
    makes successive partial returns add up to the whole discount exactly."""
    if not discount_cents or item_quantity <= 0:
        return 0
    before = discount_cents * prior_quantity // item_quantity
    return discount_cents * (prior_quantity + quantity) // item_quantity - before


def prorated_tax(item_tax: int, item_quantity: int, quantity: int, prior_quantity: int, prior_tax: int) -> int:
    """Tax refunded for `quantity` units. The final units take whatever tax is left, so rounding never drifts."""
    remaining_tax = item_tax - prior_tax
    if quantity >= item_quantity - prior_quantity:
        return remaining_tax
    share = (item_tax * quantity * 2 + item_quantity) // (item_quantity * 2)
    return min(share, remaining_tax)


# --- Lookups -------------------------------------------------------------------------------------


@dataclass
class _Prior:
    quantity: int = 0
    tax_cents: int = 0


def _prior_returns(db: Session, sale_item_ids: list[uuid.UUID]) -> dict[uuid.UUID, _Prior]:
    if not sale_item_ids:
        return {}
    rows = db.execute(
        select(ReturnItem.sale_item_id, func.sum(ReturnItem.quantity), func.sum(ReturnItem.tax_refund_cents))
        .where(ReturnItem.sale_item_id.in_(sale_item_ids))
        .group_by(ReturnItem.sale_item_id)
    ).all()
    return {row[0]: _Prior(quantity=int(row[1] or 0), tax_cents=int(row[2] or 0)) for row in rows}


def _prior_refunds(db: Session, sale_id: uuid.UUID) -> tuple[int, int]:
    total = db.scalar(
        select(func.coalesce(func.sum(SaleReturn.total_refund_cents), 0)).where(SaleReturn.original_sale_id == sale_id)
    )
    card = db.scalar(
        select(func.coalesce(func.sum(ReturnTender.amount_cents), 0))
        .join(SaleReturn, ReturnTender.return_id == SaleReturn.id)
        .where(SaleReturn.original_sale_id == sale_id, ReturnTender.method == "original_card")
    )
    return int(total or 0), int(card or 0)


def _load_sale(db: Session, sale_id: uuid.UUID, *, lock: bool = False) -> Sale | None:
    statement = (
        select(Sale)
        .options(
            selectinload(Sale.items).selectinload(SaleItem.serial_number),
            selectinload(Sale.items).selectinload(SaleItem.product),
        )
        .where(Sale.id == sale_id)
    )
    if lock and db.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    return db.scalars(statement).unique().one_or_none()


def _invoice(sale: Sale) -> str:
    return sale.invoice_number or sale.client_sale_id[:8].upper()


def receipt_out(db: Session, settings: Settings, sale: Sale) -> ReceiptOut:
    prior = _prior_returns(db, [item.id for item in sale.items])
    refunded, card_refunded = _prior_refunds(db, sale.id)
    cover = warranty_service.expiry_by_sale_item(db, [item.id for item in sale.items])
    items: list[ReceiptItemOut] = []
    for item in sale.items:
        previous = prior.get(item.id, _Prior())
        serial: SerialNumber | None = item.serial_number
        last4 = decrypt_value(serial.value_encrypted, settings)[-4:] if serial is not None else None
        items.append(
            ReceiptItemOut(
                sale_item_id=item.id,
                product_id=item.product_id,
                sku=item.product.sku,
                name=item.product.name,
                category=item.product.category,
                is_serialized=item.serial_number_id is not None,
                serial_kind=serial.kind if serial is not None else None,  # type: ignore[arg-type]
                serial_last4=last4,
                quantity=item.quantity,
                returned_quantity=previous.quantity,
                unit_price_cents=item.unit_price_cents,
                tax_cents=item.tax_cents,
                refunded_tax_cents=previous.tax_cents,
                line_total_cents=item.line_total_cents,
                warranty_expires_at=cover.get(item.id),
                sold_by_weight=item.product.sold_by_weight,
                discount_cents=(item.discount_cents or 0) + (item.manual_discount_cents or 0),
                final_sale=bool(item.final_sale),
                gift_card=item.gift_card_code is not None,
                variant=" · ".join((item.product.variant_attributes or {}).values()) or None,
            )
        )
    return ReceiptOut(
        sale_id=sale.id,
        invoice=_invoice(sale),
        store_id=sale.store_id,
        cashier_id=sale.cashier_id,
        status=sale.status,  # type: ignore[arg-type]
        currency=sale.currency,
        payment_method=sale.payment_method,  # type: ignore[arg-type]
        subtotal_cents=sale.subtotal_cents,
        tax_cents=sale.tax_cents,
        total_cents=sale.total_cents,
        refunded_cents=refunded,
        card_refundable_cents=max(0, sale.total_cents - card_refunded) if sale.payment_method == "card" else 0,
        created_at=_as_utc(sale.created_at),
        policy=policy_out(db),
        items=items,
    )


def find_receipt(db: Session, settings: Settings, code: str, *, store_scope: uuid.UUID | None) -> ReceiptOut:
    cleaned = code.strip()
    if RECEIPT_CODE.fullmatch(cleaned) is None:
        raise ApiError(422, "invalid_request", "Enter a receipt barcode or an invoice number of at least 8 characters.")
    conditions = [
        Sale.client_sale_id == cleaned,
        Sale.client_sale_id.like(f"{cleaned.lower()}%"),
        Sale.invoice_number == cleaned.upper(),
    ]
    try:
        conditions.append(Sale.id == uuid.UUID(cleaned))
    except ValueError:
        pass
    statement = select(Sale.id).where(or_(*conditions), Sale.is_quote_proforma.is_(False)).limit(2)
    matches = list(db.scalars(statement).all())
    if len(matches) > 1:
        raise ApiError(409, "ambiguous_receipt", "More than one sale matches. Scan the full receipt barcode.")
    sale = _load_sale(db, matches[0]) if matches else None
    if sale is None or (store_scope is not None and sale.store_id != store_scope):
        raise ApiError(404, "not_found", "No sale matches that receipt.")
    return receipt_out(db, settings, sale)


# --- Applying a return ---------------------------------------------------------------------------


def _describe(reasons: set[str], window_days: int = 30) -> str:
    labels = {
        "no_refund_permission": "the cashier cannot issue refunds",
        "outside_window": f"the sale is older than the {window_days}-day return window",
        "fee_waived": "the restocking fee is waived",
        "final_sale": "a final-sale item is returned",
    }
    return "; ".join(labels[item] for item in sorted(reasons))


def _approver(
    db: Session, data: ReturnPayload, cashier: User, required: set[str], window_days: int = 30
) -> User | None:
    override = data.override
    if override is None:
        if required:
            raise SyncRejected(f"Manager approval is required: {_describe(required, window_days)}.")
        return None
    missing = required - set(override.reasons)
    if missing:
        raise SyncRejected(f"Manager approval does not cover: {_describe(missing, window_days)}.")
    approver = db.get(User, override.approved_by_id)
    if approver is None:
        raise SyncRejected("Approving manager does not exist.")
    if approver.id == cashier.id:
        raise SyncRejected("A cashier cannot approve their own return.")
    if Permission.POS_REFUND.value not in approver.permissions:
        raise SyncRejected("Approving manager cannot issue refunds.")
    if approver.store_id is not None and approver.store_id != data.store_id:
        raise SyncRejected("Approving manager is not assigned to this store.")
    return approver


def apply_return(db: Session, settings: Settings, payload: dict[str, object]) -> uuid.UUID:
    data = parse_payload(ReturnPayload, payload)
    # Refunds follow the original sale's currency, which may predate a business currency change.
    require_store(db, data.store_id)
    cashier = require_cashier(db, data.cashier_id, data.store_id)
    if db.get(SaleReturn, data.id) is not None:
        raise SyncRejected("Return already exists.")

    sale = _load_sale(db, data.original_sale_id, lock=True)
    if sale is None:
        raise SyncRejected("Original sale does not exist.")
    if sale.store_id != data.store_id:
        raise SyncRejected("Returns must be processed at the store that made the sale.")
    if sale.currency != data.currency:
        raise SyncRejected("Return currency must match the original sale.")
    if sale.status == "refunded":
        raise SyncRejected("Every item on this sale was already returned.")
    if sale.status not in RETURNABLE_SALE_STATUSES:
        raise SyncRejected("This sale is not eligible for returns.")

    skew = timedelta(seconds=MAX_CLOCK_SKEW_SECONDS)
    processed_at = _as_utc(data.processed_at)
    sold_at = _as_utc(sale.created_at)
    if processed_at > datetime.now(UTC) + skew:
        raise SyncRejected("Return time is in the future.")
    if processed_at < sold_at - skew:
        raise SyncRejected("Return time is before the original sale.")
    policy = returns_policy(db)
    age = processed_at - sold_at
    outside_window = age > timedelta(days=policy.window_days)
    # After the refund window, an exchange window accepts the return as an exchange voucher only.
    exchange_only = outside_window and age <= timedelta(days=policy.window_days + policy.exchange_window_days)
    if exchange_only:
        outside_window = False
    final_sale = False

    items_by_id = {item.id: item for item in sale.items}
    prior = _prior_returns(db, list(items_by_id))
    seen: set[uuid.UUID] = set()
    resolved: list[tuple[int, SaleItem, SerialNumber | None]] = []
    fee_waived = False
    subtotal = tax = fee = 0
    for index, line in enumerate(data.items):
        if line.sale_item_id in seen:
            raise SyncRejected("Each sale line can appear only once per return.")
        seen.add(line.sale_item_id)
        item = items_by_id.get(line.sale_item_id)
        if item is None:
            raise SyncRejected("Item is not on the original sale.")
        if line.product_id != item.product_id:
            raise SyncRejected("Returned product does not match the sale line.")
        if line.unit_price_cents != item.unit_price_cents:
            raise SyncRejected("Refund price must match the price paid.")
        if item.gift_card_code is not None:
            raise SyncRejected("A gift card is not returned; void the card from the portal instead.")
        condition = policy.condition(line.condition_status)
        if condition is None:
            raise SyncRejected(f"Return condition {line.condition_status!r} is not in the returns policy.")
        if item.final_sale:
            final_sale = True
        previous = prior.get(item.id, _Prior())
        if line.quantity > item.quantity - previous.quantity:
            raise SyncRejected("Return quantity exceeds what is left to return on this line.")

        serial = item.serial_number
        if item.serial_number_id is not None:
            if line.serial_kind is None or line.serial_value is None:
                raise SyncRejected("Scan the IMEI or serial number of the returned device.")
            normalized = normalize_identifier(line.serial_kind, line.serial_value)
            if serial is None or identifier_hash(normalized) != serial.value_hash:
                raise SyncRejected("IMEI or serial number does not match the unit that was sold.")
            if serial.status != "sold":
                raise SyncRejected("This unit is not recorded as sold.")
        elif line.serial_value is not None:
            raise SyncRejected("Serial numbers are only valid for serialized products.")

        expected_tax = prorated_tax(item.tax_cents, item.quantity, line.quantity, previous.quantity, previous.tax_cents)
        if line.tax_refund_cents != expected_tax:
            raise SyncRejected("Tax refund does not match the original sale.")
        scale = weighed.scale_of(db.get(Product, item.product_id))
        expected_fee = restocking_fee(line.unit_price_cents, line.quantity, condition.fee_bps, scale)
        if line.restocking_fee_cents != expected_fee:
            if line.restocking_fee_cents != 0:
                raise SyncRejected("Restocking fee does not match the return policy.")
            fee_waived = True
        discounted = discount_share(
            (item.discount_cents or 0) + (item.manual_discount_cents or 0), item.quantity, line.quantity, previous.quantity
        )
        line_subtotal = weighed.amount(line.quantity, line.unit_price_cents, scale) - discounted
        if line.refund_cents != line_subtotal + line.tax_refund_cents - line.restocking_fee_cents:
            raise SyncRejected("Line refund does not match price, discount, tax, and restocking fee.")
        subtotal += line_subtotal
        tax += line.tax_refund_cents
        fee += line.restocking_fee_cents
        resolved.append((index, item, serial))

    if (
        data.subtotal_cents != subtotal
        or data.tax_refund_cents != tax
        or data.restocking_fee_cents != fee
        or data.total_refund_cents != subtotal + tax - fee
    ):
        raise SyncRejected("Return totals do not match line items.")

    methods = [tender.method for tender in data.tenders]
    if len(set(methods)) != len(methods):
        raise SyncRejected("Each refund method can be used only once.")
    if sum(tender.amount_cents for tender in data.tenders) != data.total_refund_cents:
        raise SyncRejected("Refund tenders must add up to the refund total.")
    allowed = ALLOWED_TENDERS.get(sale.payment_method, frozenset({"store_credit"}))
    if exchange_only:
        # Past the refund window but inside the exchange window: an exchange voucher, never money back.
        allowed = frozenset({"store_credit"})
    for tender in data.tenders:
        if tender.method not in allowed:
            options = " or ".join(TENDER_LABELS[item] for item in sorted(allowed))
            raise SyncRejected(f"This sale was paid by {sale.payment_method.replace('_', ' ')}; refund to {options}.")
    _, card_refunded = _prior_refunds(db, sale.id)
    card = sum(tender.amount_cents for tender in data.tenders if tender.method == "original_card")
    if card > sale.total_cents - card_refunded:
        raise SyncRejected("Card refund exceeds what is left on the original card payment.")

    required: set[str] = set()
    if Permission.POS_REFUND.value not in cashier.permissions:
        required.add("no_refund_permission")
    if outside_window:
        required.add("outside_window")
    if fee_waived:
        required.add("fee_waived")
    if final_sale:
        required.add("final_sale")
    approver = _approver(db, data, cashier, required, policy.window_days)

    primary = max(data.tenders, key=lambda tender: tender.amount_cents).method
    db.add(
        SaleReturn(
            id=data.id,
            original_sale_id=sale.id,
            store_id=data.store_id,
            cashier_id=cashier.id,
            approved_by_id=approver.id if approver is not None else None,
            currency=data.currency,
            subtotal_cents=subtotal,
            tax_refund_cents=tax,
            restocking_fee_cents=fee,
            total_refund_cents=data.total_refund_cents,
            refund_method=primary,
            reason_notes=data.reason_notes.strip(),
            shift_id=data.shift_id,
            created_at=processed_at,
            updated_at=processed_at,
        )
    )
    db.flush()

    for index, item, serial in resolved:
        line = data.items[index]
        db.add(
            ReturnItem(
                id=line.id,
                return_id=data.id,
                sale_item_id=item.id,
                product_id=item.product_id,
                serial_number_id=serial.id if serial is not None else None,
                quantity=line.quantity,
                unit_price_cents=line.unit_price_cents,
                tax_refund_cents=line.tax_refund_cents,
                restocking_fee_cents=line.restocking_fee_cents,
                refund_cents=line.refund_cents,
                condition_status=line.condition_status,
                reason_code=line.reason_code,
            )
        )
        if serial is not None:
            warranty_service.void_for_return(db, item.id)
            transition_serial(
                db,
                serial,
                status=policy.condition(line.condition_status).serial_status,  # type: ignore[union-attr]
                store_id=data.store_id,
                movement_type="RETURN_IN",
                reference_type="sale_return",
                reference_id=data.id,
                user_id=cashier.id,
            )
        elif policy.condition(line.condition_status).restock and not _made_to_order(  # type: ignore[union-attr]
            db, item.product_id
        ):
            move_stock(
                db,
                product_id=item.product_id,
                store_id=data.store_id,
                quantity=line.quantity,
                movement_type="RETURN_IN",
                reference_type="sale_return",
                reference_id=data.id,
                user_id=cashier.id,
            )
            batch_ledger.restore_sale_item(db, sale_item_id=item.id, store_id=data.store_id, quantity=line.quantity)

    for tender in data.tenders:
        credit_id: uuid.UUID | None = None
        if tender.store_credit_code is not None:
            if db.scalar(select(StoreCredit.id).where(StoreCredit.code == tender.store_credit_code)) is not None:
                raise SyncRejected("Store credit code is already in use.")
            credit_id = uuid.uuid4()
            db.add(
                StoreCredit(
                    id=credit_id,
                    code=tender.store_credit_code,
                    store_id=data.store_id,
                    return_id=data.id,
                    currency=data.currency,
                    initial_cents=tender.amount_cents,
                    balance_cents=tender.amount_cents,
                )
            )
            db.flush()
        db.add(
            ReturnTender(
                return_id=data.id,
                method=tender.method,
                amount_cents=tender.amount_cents,
                store_credit_id=credit_id,
            )
        )
        integrated_payment_service.queue_refunds(
            db, sale_id=sale.id, return_id=data.id, method=tender.method, amount_cents=tender.amount_cents
        )

    returned_now = {item.id: data.items[index].quantity for index, item, _ in resolved}
    fully_returned = all(
        prior.get(item.id, _Prior()).quantity + returned_now.get(item.id, 0) >= item.quantity for item in sale.items
    )
    sale.status = "refunded" if fully_returned else "partially_refunded"
    if sale.customer_id is not None:
        owner = db.get(Customer, sale.customer_id)
        if owner is not None:
            loyalty_service.reverse_for_return(
                db, owner, return_id=data.id, refund_cents=data.total_refund_cents, user_id=cashier.id
            )

    override = data.override if approver is not None else None
    details: dict[str, object] = {
        "refund_cents": data.total_refund_cents,
        "original_sale_id": str(sale.id),
        "tenders": {tender.method: tender.amount_cents for tender in data.tenders},
    }
    if override is not None:
        details |= {"reasons": sorted(set(override.reasons)), "required": sorted(required)}
    audit.record(
        db,
        action_type="REFUND_PROCESSED",
        action=OVERRIDE_ACTION if override is not None else "return.processed",
        target_entity="SaleReturn",
        target_entity_id=data.id,
        user=cashier,
        approver_id=approver.id if override is not None and approver is not None else None,
        store_id=data.store_id,
        reason_notes=override.note.strip() if override is not None else None,
        details=details,
        client_device="desktop",
        occurred_at=processed_at,
    )
    db.flush()
    return data.id


# --- Reads ---------------------------------------------------------------------------------------


def _return_query() -> Select[tuple[SaleReturn]]:
    return select(SaleReturn).options(
        selectinload(SaleReturn.items),
        selectinload(SaleReturn.tenders).selectinload(ReturnTender.store_credit),
    )


def return_out(record: SaleReturn) -> ReturnOut:
    return ReturnOut(
        id=record.id,
        original_sale_id=record.original_sale_id,
        store_id=record.store_id,
        cashier_id=record.cashier_id,
        approved_by_id=record.approved_by_id,
        currency=record.currency,
        subtotal_cents=record.subtotal_cents,
        tax_refund_cents=record.tax_refund_cents,
        restocking_fee_cents=record.restocking_fee_cents,
        total_refund_cents=record.total_refund_cents,
        refund_method=record.refund_method,  # type: ignore[arg-type]
        reason_notes=record.reason_notes,
        items=[
            ReturnItemOut(
                id=item.id,
                sale_item_id=item.sale_item_id,
                product_id=item.product_id,
                serial_number_id=item.serial_number_id,
                quantity=item.quantity,
                unit_price_cents=item.unit_price_cents,
                tax_refund_cents=item.tax_refund_cents,
                restocking_fee_cents=item.restocking_fee_cents,
                refund_cents=item.refund_cents,
                condition_status=item.condition_status,  # type: ignore[arg-type]
                reason_code=item.reason_code,  # type: ignore[arg-type]
            )
            for item in record.items
        ],
        tenders=[
            ReturnTenderOut(
                method=tender.method,  # type: ignore[arg-type]
                amount_cents=tender.amount_cents,
                store_credit_code=tender.store_credit.code if tender.store_credit is not None else None,
            )
            for tender in record.tenders
        ],
        credit_note_number=record.credit_note_number,
        created_at=_as_utc(record.created_at),
    )


def get_return(db: Session, return_id: uuid.UUID, *, store_scope: uuid.UUID | None = None) -> ReturnOut:
    record = db.scalars(_return_query().where(SaleReturn.id == return_id)).unique().one_or_none()
    if record is None or (store_scope is not None and record.store_id != store_scope):
        raise ApiError(404, "not_found", "Return was not found.")
    return return_out(record)


def list_returns(db: Session, *, limit: int, store_scope: uuid.UUID | None = None) -> list[ReturnOut]:
    statement = _return_query().order_by(SaleReturn.created_at.desc()).limit(limit)
    if store_scope is not None:
        statement = statement.where(SaleReturn.store_id == store_scope)
    return [return_out(record) for record in db.scalars(statement).unique().all()]


# --- Analytics -----------------------------------------------------------------------------------


def _bps(part: int, whole: int) -> int:
    return round(part * 10_000 / whole) if whole else 0


@dataclass
class _ProductTally:
    product: Product
    last_returned_at: datetime
    units_returned: int = 0
    defective_units: int = 0
    refund_cents: int = 0


def build_returns_analytics(
    db: Session,
    *,
    timeframe: str,
    currency: str,
    store_scope: uuid.UUID | None = None,
) -> ReturnsAnalytics:
    now = datetime.now(UTC)
    start = period_start(timeframe, now)
    statement = (
        select(SaleReturn)
        .options(selectinload(SaleReturn.items).selectinload(ReturnItem.product), selectinload(SaleReturn.tenders))
        .where(SaleReturn.currency == currency)
    )
    if start is not None:
        statement = statement.where(SaleReturn.created_at >= start)
    if store_scope is not None:
        statement = statement.where(SaleReturn.store_id == store_scope)
    returns = list(db.scalars(statement).unique().all())
    sales = load_sales(db, currency, start, now, store_scope)

    sold_by_product: dict[uuid.UUID, int] = defaultdict(int)
    for sale in sales:
        for sale_item in sale.items:
            sold_by_product[sale_item.product_id] += sale_item.quantity
    units_sold = sum(sold_by_product.values())

    conditions: dict[str, int] = defaultdict(int)
    tenders: dict[str, int] = defaultdict(int)
    products: dict[uuid.UUID, _ProductTally] = {}
    policy = returns_policy(db)
    # Faulty returns: conditions that send the unit to repair (DOA, damaged), plus the electronics key in old data.
    faulty = {condition.key for condition in policy.conditions if condition.serial_status == "repair"} | {
        "defective_doa"
    }
    edges = period_edges(timeframe, now)
    series = [0 for _ in range(len(edges) - 1)]
    for record in returns:
        created = _as_utc(record.created_at)
        for index in range(len(edges) - 1):
            if edges[index] <= created < edges[index + 1]:
                series[index] += record.total_refund_cents
                break
        for tender in record.tenders:
            tenders[tender.method] += tender.amount_cents
        for item in record.items:
            conditions[item.condition_status] += item.quantity
            tally = products.setdefault(item.product_id, _ProductTally(product=item.product, last_returned_at=created))
            tally.units_returned += item.quantity
            tally.refund_cents += item.refund_cents
            if item.condition_status in faulty:
                tally.defective_units += item.quantity
            tally.last_returned_at = max(tally.last_returned_at, created)

    units_returned = sum(conditions.values())
    defective_units = sum(units for key, units in conditions.items() if key in faulty)

    top_products = [
        ReturnedProductRow(
            product_id=product_id,
            sku=tally.product.sku,
            name=tally.product.name,
            category=tally.product.category,
            units_sold=sold_by_product.get(product_id, 0),
            units_returned=tally.units_returned,
            defective_units=tally.defective_units,
            return_rate_bps=_bps(tally.units_returned, max(sold_by_product.get(product_id, 0), tally.units_returned)),
            refund_cents=tally.refund_cents,
            last_returned_at=tally.last_returned_at,
        )
        for product_id, tally in products.items()
    ]
    top_products.sort(key=lambda item: (item.defective_units, item.units_returned, item.refund_cents), reverse=True)

    return_ids = [record.id for record in returns]
    logs: list[AuditLog] = []
    if return_ids:
        logs = list(
            db.scalars(
                select(AuditLog).where(AuditLog.action == OVERRIDE_ACTION, AuditLog.target_entity_id.in_(return_ids))
            ).all()
        )
    user_ids = {record.cashier_id for record in returns} | {log.approver_id for log in logs if log.approver_id}
    users = {user.id: user for user in db.scalars(select(User).where(User.id.in_(user_ids))).unique().all()}
    refunds_by_id = {record.id: record.total_refund_cents for record in returns}

    by_cashier: dict[uuid.UUID, list[SaleReturn]] = defaultdict(list)
    for record in returns:
        by_cashier[record.cashier_id].append(record)
    cashiers: list[CashierReturnRow] = []
    for cashier_id, records in by_cashier.items():
        own_logs = [log for log in logs if log.user_id == cashier_id]
        user = users.get(cashier_id)
        override_count = len(own_logs)
        cashiers.append(
            CashierReturnRow(
                cashier_id=cashier_id,
                full_name=user.full_name if user is not None else "Unknown cashier",
                role_name=user.role.name if user is not None else "",
                return_count=len(records),
                refund_cents=sum(record.total_refund_cents for record in records),
                override_count=override_count,
                outside_window_count=sum(1 for log in own_logs if "outside_window" in log.details.get("required", [])),  # type: ignore[operator]
                last_return_at=max(_as_utc(record.created_at) for record in records),
                flagged=override_count >= OVERRIDE_FLAG_THRESHOLD,
            )
        )
    cashiers.sort(key=lambda row: (row.flagged, row.override_count, row.return_count), reverse=True)

    overrides = [
        OverrideLogRow(
            id=log.id,
            return_id=log.target_entity_id,
            created_at=_as_utc(log.occurred_at),
            cashier_name=users[log.user_id].full_name if log.user_id in users else "Unknown cashier",
            approver_name=users[log.approver_id].full_name if log.approver_id in users else None,
            reasons=list(log.details.get("reasons", [])),  # type: ignore[call-overload]
            refund_cents=refunds_by_id.get(log.target_entity_id, 0) if log.target_entity_id else 0,
            note=log.reason_notes or str(log.details.get("note", "")),
        )
        for log in sorted(logs, key=lambda item: _as_utc(item.occurred_at), reverse=True)[:25]
        if log.target_entity_id is not None
    ]

    return ReturnsAnalytics(
        timeframe=timeframe,  # type: ignore[arg-type]
        currency=currency,
        return_count=len(returns),
        units_returned=units_returned,
        units_sold=units_sold,
        return_rate_bps=_bps(units_returned, max(units_sold, units_returned)),
        refund_cents=sum(record.total_refund_cents for record in returns),
        restocking_fee_cents=sum(record.restocking_fee_cents for record in returns),
        defective_units=defective_units,
        defective_rate_bps=_bps(defective_units, units_returned),
        override_count=len(logs),
        refund_series=series,
        conditions=[
            ConditionSlice(condition=key, units=conditions.get(key, 0))
            for key in [
                *(condition.key for condition in policy.conditions),
                *sorted(set(conditions) - {condition.key for condition in policy.conditions}),
            ]
        ],
        tenders=[
            TenderSlice(method=method, amount_cents=tenders.get(method, 0))  # type: ignore[arg-type]
            for method in ("original_card", "cash", "store_credit")
        ],
        top_products=top_products[:10],
        cashiers=cashiers,
        overrides=overrides,
    )
