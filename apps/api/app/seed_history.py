"""Demo trading history (`python -m app.seed --history`): about four months of sales and B2B account activity, so
forecasts, credit risk scores and the dead-stock report have something real to work on.

Every sale goes through `sale_service.record_sale`, the same path a register sync takes, so stock, costing, ledgers
and e-invoices stay consistent. Registers may only sync sales up to 30 days old, so each sale is recorded as of now and
then moved back to its simulated date, together with its ledger rows and stock movements."""

import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import Principal
from app.models.customer import Customer, CustomerLedgerEntry
from app.models.inventory import InventoryLevel, StockMovement
from app.models.product import Product
from app.models.sale import Sale
from app.models.store import Store
from app.models.user import User
from app.schemas.inventory import PurchaseOrderCreate, PurchaseOrderLineIn, ReceiveLineIn, ReceiveRequest
from app.schemas.payloads import SalePayload
from app.services import credit_risk_service, credit_service, inventory, ledger_service, replenishment_service
from app.services.sale_service import record_sale
from app.services.tax import line_tax
from app.services.tax import policy as tax_policy

DAYS = 120
MARKER = "demo-history"
# Retail demand shapes, assigned to the store's first stocked products in SKU order.
PATTERNS = ("trend_up", "weekend", "steady", "fading", "steady", "weekend")


@dataclass(frozen=True)
class Payer:
    #: Days after the due date the account pays (negative: early).
    late_days: int
    #: Unpaid invoices from the last N days are left open, which makes them overdue.
    stops_paying_days: int = 0


# Matched to the demo wholesale accounts in packages/catalog/seed.json.
PAYERS = {
    "ALNR-0001": Payer(late_days=-2),
    "GULF-0002": Payer(late_days=16),
    "EMIR-0003": Payer(late_days=40, stops_paying_days=75),
}


def _daily_units(pattern: str, day_index: int, weekday: int, rng: random.Random) -> int:
    progress = day_index / DAYS
    base = {
        "trend_up": 1 + 5 * progress,
        "fading": 5 - 4 * progress,
        "weekend": 6 if weekday >= 4 else 1.5,
        "steady": 3,
    }[pattern]
    return max(0, round(rng.gauss(base, max(0.6, base * 0.3))))


def _payload(
    db: Session, *, store: Store, cashier: User, lines: list[tuple[Product, int]], customer: Customer | None
) -> SalePayload:
    tax = tax_policy(db)
    items = []
    for product, quantity in lines:
        rate = tax.rate_for(product.tax_category) if tax.enforced else 0
        priced = line_tax(product.price_cents, quantity, rate, inclusive=tax.prices_include_vat)
        items.append(
            {
                "id": str(uuid.uuid4()),
                "product_id": str(product.id),
                "quantity": quantity,
                "unit_price_cents": product.price_cents,
                "list_price_cents": product.price_cents,
                "tax_cents": priced.tax_cents,
                "line_total_cents": priced.line_total_cents,
            }
        )
    total = sum(item["line_total_cents"] for item in items)
    tax_cents = sum(item["tax_cents"] for item in items)
    sale_id = str(uuid.uuid4())
    body: dict = {
        "id": sale_id,
        "store_id": str(store.id),
        "cashier_id": str(cashier.id),
        "currency": store.currency,
        "payment_method": "cash",
        "subtotal_cents": total - tax_cents,
        "tax_cents": tax_cents,
        "total_cents": total,
        "client_sale_id": f"{MARKER}-{sale_id[:18]}",
        "items": items,
    }
    if customer is not None:
        body.update(
            customer_id=str(customer.id),
            sale_type="WHOLESALE",
            payment_method="on_account",
            tenders=[{"method": "on_account", "amount_cents": total}],
        )
    return SalePayload.model_validate(body)


def _backdate_sale(db: Session, sale: Sale, when: datetime, customer: Customer | None) -> None:
    sale.created_at = when
    if customer is not None:
        sale.due_date = ledger_service.due_date_for(customer, when)
    entries = db.scalars(select(CustomerLedgerEntry).where(CustomerLedgerEntry.sale_id == sale.id)).all()
    for offset, entry in enumerate(sorted(entries, key=lambda row: row.created_at)):
        entry.created_at = when + timedelta(microseconds=offset)
        if entry.entry_type == "INVOICE":
            entry.due_date = sale.due_date
    db.execute(
        update(StockMovement)
        .where(StockMovement.reference_type == "sale", StockMovement.reference_id == sale.id)
        .values(created_at=when)
    )


def seed_history(db: Session, settings: Settings, *, cashier: User) -> list[str]:
    if db.scalar(select(Sale.id).where(Sale.client_sale_id.like(f"{MARKER}-%")).limit(1)) is not None:
        return ["already seeded (unchanged)"]
    store = db.scalar(select(Store).where(Store.is_active.is_(True)).order_by(Store.is_warehouse, Store.code))
    if store is None:
        return ["no store to trade in"]
    rng = random.Random(20261020)
    now = datetime.now(UTC).replace(microsecond=0)
    start = now - timedelta(days=DAYS)

    stocked = db.scalars(
        select(Product)
        .join(InventoryLevel, InventoryLevel.product_id == Product.id)
        .where(
            InventoryLevel.store_id == store.id,
            InventoryLevel.quantity_on_hand > 0,
            Product.is_serialized.is_(False),
            Product.is_service.is_(False),
            Product.is_open_price.is_(False),
            Product.price_cents > 0,
        )
        .order_by(Product.sku)
    ).all()
    retail = list(stocked[: len(PATTERNS)])
    wholesale = list(stocked[: min(3, len(stocked))])
    customers = {row.code: row for row in db.scalars(select(Customer).where(Customer.code.in_(list(PAYERS))))}
    for customer in customers.values():
        customer.created_at = min(ledger_service.as_utc(customer.created_at), start - timedelta(days=200))

    # Older opening stock: products that never sell show up as dead stock instead of brand-new arrivals.
    db.execute(
        update(StockMovement)
        .where(StockMovement.reference_type == "opening_balance")
        .values(created_at=now - timedelta(days=DAYS + 90))
    )

    events: list[tuple[datetime, str, object]] = []
    for day in range(DAYS):
        moment = start + timedelta(days=day, hours=11)
        for product, pattern in zip(retail, PATTERNS, strict=False):
            units = _daily_units(pattern, day, moment.weekday(), rng)
            if units:
                events.append((moment + timedelta(minutes=rng.randint(0, 480)), "retail", (product, units)))
    for code, payer in PAYERS.items():
        customer = customers.get(code)
        if customer is None or not wholesale:
            continue
        day = rng.randint(0, 6)
        while day < DAYS - 2:
            moment = start + timedelta(days=day, hours=15)
            lines = [
                (product, max(product.min_order_quantity, rng.randint(4, 12))) for product in rng.sample(wholesale, 2)
            ]
            events.append((moment, "invoice", (customer, lines, payer)))
            day += rng.randint(6, 11)

    # Stock up first, through a received purchase order at ~60% of retail, so simulated demand never runs the shelves
    # dry and every product has a real purchase cost (margins, valuation and holding cost read it).
    needed: dict[uuid.UUID, int] = {}
    for _, kind, data in events:
        lines = [data] if kind == "retail" else data[1]  # type: ignore[index]
        for product, quantity in lines:  # type: ignore[misc]
            needed[product.id] = needed.get(product.id, 0) + quantity
    costed = db.scalars(
        select(Product).where(
            Product.is_serialized.is_(False),
            Product.is_service.is_(False),
            Product.is_open_price.is_(False),
            Product.price_cents > 0,
        )
    ).all()
    _receive_stock(db, settings, cashier, store, {product: needed.get(product.id, 1) for product in costed})
    db.execute(
        update(StockMovement)
        .where(StockMovement.movement_type == "PURCHASE_IN")
        .values(created_at=start - timedelta(days=1))
    )
    db.commit()

    payments: list[tuple[datetime, Customer, Sale]] = []
    retail_count = invoice_count = 0
    for when, kind, data in sorted(events, key=lambda event: event[0]):
        while payments and payments[0][0] <= when:
            _pay(db, *payments.pop(0))
        if kind == "retail":
            product, units = data  # type: ignore[misc]
            sale = record_sale(
                db, settings, _payload(db, store=store, cashier=cashier, lines=[(product, units)], customer=None)
            )
            _backdate_sale(db, sale, when, None)
            retail_count += 1
        else:
            customer, lines, payer = data  # type: ignore[misc]
            sale = record_sale(db, settings, _payload(db, store=store, cashier=cashier, lines=lines, customer=customer))
            _backdate_sale(db, sale, when, customer)
            invoice_count += 1
            due = ledger_service.as_utc(sale.due_date or when)
            pay_at = due + timedelta(days=payer.late_days + rng.randint(-1, 2))
            if pay_at < now and when < now - timedelta(days=payer.stops_paying_days or 0):
                payments.append((pay_at, customer, sale))
                payments.sort(key=lambda item: item[0])
        db.commit()
    for item in payments:
        if item[0] < now:
            _pay(db, *item)
    db.commit()

    replenishment_service.snapshot_demand(db, days=DAYS + 1)
    # Holds were judged while each sale was recorded "now"; judge them again against the backdated history.
    credit_service.refresh_all(db, settings)
    scored = credit_risk_service.refresh_all(db)
    run = replenishment_service.create_run(db, store_id=store.id, review_days=7, user_id=cashier.id)
    return [
        f"{retail_count} retail sales over {DAYS} days at {store.code}",
        f"{invoice_count} on-account invoices for {len(customers)} wholesale accounts",
        f"{scored} accounts scored for credit risk",
        f"replenishment run with {len(run.suggestions)} suggestions",
    ]


def _receive_stock(db: Session, settings: Settings, user: User, store: Store, quantities: dict[Product, int]) -> None:
    principal = Principal(kind="user", scope="portal", user=user, permissions=frozenset(user.permissions))
    order = inventory.create_purchase_order(
        db,
        principal,
        PurchaseOrderCreate(
            supplier_name="Gulf Electronics Supply",
            destination_store_id=store.id,
            notes="Demo history stock",
            lines=[
                PurchaseOrderLineIn(
                    product_id=product.id, quantity_ordered=quantity, unit_cost_cents=product.price_cents * 6 // 10
                )
                for product, quantity in quantities.items()
            ],
        ),
    )
    inventory.mark_ordered(db, principal, order.id)
    inventory.receive_purchase_order(
        db,
        settings,
        principal,
        order.id,
        ReceiveRequest(
            note="Demo history stock",
            lines=[
                ReceiveLineIn(purchase_order_line_id=line.id, quantity=line.quantity_ordered) for line in order.lines
            ],
        ),
    )


def _pay(db: Session, when: datetime, customer: Customer, sale: Sale) -> None:
    db.refresh(sale)
    if sale.due_balance_cents <= 0:
        return
    entry, _ = ledger_service.receive_payment(
        db,
        customer,
        amount_cents=sale.due_balance_cents,
        method="transfer",
        reference=f"DEMO-{(sale.invoice_number or '')[-6:]}",
        note="",
        user_id=None,
    )
    entry.created_at = when
    db.commit()
