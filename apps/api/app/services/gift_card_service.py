"""Gift cards: GIFT_CARD store credits. Sold at the till as a line on the service product SRV-GIFT-CARD (the register
generates the code offline, as it does for return vouchers), issued from the portal, spent as a `gift_card` tender at
any branch. A multi-purpose voucher carries no VAT when sold; VAT falls on what it buys."""

from __future__ import annotations

import calendar
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, SyncRejected
from app.models.customer import Customer
from app.models.inventory import InventoryLevel
from app.models.product import Product
from app.models.sale import Sale
from app.models.store import Store
from app.models.store_credit import StoreCredit
from app.models.user import User
from app.schemas.payloads import SaleItemPayload
from app.schemas.store_credit import GiftCardIssue, GiftCardProductOut, StoreCreditList, StoreCreditOut
from app.services import audit
from app.services.settings_service import business_currency, pos_policy

GIFT_CARD_SKU = "SRV-GIFT-CARD"
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(12))
    return f"GC-{raw[:4]}-{raw[4:8]}-{raw[8:]}"


def ensure_product(db: Session) -> Product:
    """The open-value service product gift cards are sold as; created the first time it is needed."""
    product = db.scalar(select(Product).where(Product.sku == GIFT_CARD_SKU))
    if product is not None:
        return product
    product = Product(
        sku=GIFT_CARD_SKU,
        barcode=GIFT_CARD_SKU,
        name="Gift card",
        brand="Service",
        category="Gift cards",
        price_cents=0,
        currency=business_currency(db),
        is_service=True,
        tax_category="ZERO",
    )
    db.add(product)
    db.flush()
    # Registers list a branch's catalogue from its stock levels, so every branch gets a (zero) level.
    for store_id in db.scalars(select(Store.id)):
        db.add(InventoryLevel(product_id=product.id, store_id=store_id, quantity_on_hand=0, quantity_reserved=0))
    return product


def product_out(db: Session) -> GiftCardProductOut:
    product = ensure_product(db)
    db.commit()
    rules = pos_policy(db).gift_cards
    return GiftCardProductOut(
        product_id=product.id,
        sku=product.sku,
        name=product.name,
        min_cents=rules.min_cents,
        max_cents=rules.max_cents,
        expiry_months=rules.expiry_months,
    )


def add_months(value: datetime, months: int) -> datetime:
    index = value.month - 1 + months
    year, month = value.year + index // 12, index % 12 + 1
    return value.replace(year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1]))


def _expiry(db: Session, issued_at: datetime) -> datetime | None:
    months = pos_policy(db).gift_cards.expiry_months
    return add_months(issued_at, months) if months else None


def check_sale_line(db: Session, item: SaleItemPayload, product: Product) -> None:
    if product.sku != GIFT_CARD_SKU:
        raise SyncRejected("Gift cards are sold on the gift card product.")
    rules = pos_policy(db).gift_cards
    if not rules.min_cents <= item.unit_price_cents <= rules.max_cents:
        raise SyncRejected(
            f"A gift card is loaded with {rules.min_cents / 100:,.2f} to {rules.max_cents / 100:,.2f}."
        )
    if item.tax_cents:
        raise SyncRejected("A gift card carries no VAT when sold.")
    if db.scalar(select(StoreCredit.id).where(StoreCredit.code == item.gift_card_code)) is not None:
        raise SyncRejected(f"Gift card {item.gift_card_code} already exists.")


def issue_from_sale(db: Session, sale: Sale, lines: list, customer: Customer | None) -> None:
    """Loads one GIFT_CARD credit per gift card line of a recorded sale."""
    for line in lines:
        code = line.item.gift_card_code
        if code is None:
            continue
        db.add(
            StoreCredit(
                code=code,
                store_id=sale.store_id,
                currency=sale.currency,
                initial_cents=line.item.line_total_cents,
                balance_cents=line.item.line_total_cents,
                kind="GIFT_CARD",
                issued_sale_id=sale.id,
                customer_id=customer.id if customer is not None else None,
                expires_at=_expiry(db, sale.created_at or datetime.now(UTC)),
                note=f"Sold on {sale.invoice_number or sale.client_sale_id[:8].upper()}",
            )
        )


def _require(db: Session, code: str) -> StoreCredit:
    card = db.scalar(select(StoreCredit).where(StoreCredit.code == code.strip().upper()))
    if card is None or card.kind != "GIFT_CARD":
        raise ApiError(404, "not_found", "No gift card with that code.")
    return card


def list_cards(db: Session, *, open_only: bool, store_scope: uuid.UUID | None, limit: int) -> StoreCreditList:
    from app.services import store_credit_service

    return store_credit_service.list_credits(
        db, open_only=open_only, store_scope=store_scope, limit=limit, kind="GIFT_CARD"
    )


def issue(db: Session, actor: User, data: GiftCardIssue) -> list[StoreCreditOut]:
    from app.services import store_credit_service

    store = db.get(Store, data.store_id)
    if store is None:
        raise ApiError(404, "not_found", "Store not found.")
    if data.customer_id is not None and db.get(Customer, data.customer_id) is None:
        raise ApiError(404, "not_found", "Customer not found.")
    now = datetime.now(UTC)
    cards = []
    for _ in range(data.count):
        card = StoreCredit(
            code=new_code(),
            store_id=store.id,
            currency=store.currency,
            initial_cents=data.amount_cents,
            balance_cents=data.amount_cents,
            kind="GIFT_CARD",
            customer_id=data.customer_id,
            expires_at=_expiry(db, now),
            note=data.note.strip(),
        )
        db.add(card)
        cards.append(card)
    db.flush()
    audit.record(
        db,
        action_type="CREATE",
        action="gift_cards.issue",
        target_entity="GiftCard",
        target_entity_id=cards[0].id,
        user=actor,
        new_values={"count": data.count, "amount_cents": data.amount_cents, "codes": [card.code for card in cards]},
        reason_notes=data.note,
    )
    db.commit()
    return [store_credit_service.lookup(db, card.code) for card in cards]


def void(db: Session, actor: User, code: str, note: str) -> StoreCreditOut:
    from app.services import store_credit_service

    card = _require(db, code)
    if card.voided_at is not None:
        raise ApiError(409, "already_voided", "This gift card is already voided.")
    card.voided_at = datetime.now(UTC)
    audit.record(
        db,
        action_type="DELETE",
        action="gift_cards.void",
        target_entity="GiftCard",
        target_entity_id=card.id,
        user=actor,
        old_values={"balance_cents": card.balance_cents},
        reason_notes=note,
    )
    db.commit()
    return store_credit_service.lookup(db, card.code)
