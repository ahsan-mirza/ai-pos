"""Thirty days of demo sales, recorded through the live sale, return, and ledger services.

Sales are rung at the current time, then moved back with seed_history._backdate_sale. The sales
service is not changed to accept an older sold_at. The random stream is fixed, so a fresh database
always produces the same totals.
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.models.customer import Customer
from app.models.inventory import InventoryLevel
from app.models.menu import ModifierGroup
from app.models.product import Product
from app.models.promotion import Promotion
from app.models.sale import Sale
from app.models.store import Store
from app.models.user import User
from app.schemas.payloads import (
    ModifierChoice,
    ReturnItemPayload,
    ReturnPayload,
    ReturnTenderPayload,
    SaleItemPayload,
    SalePayload,
    SaleTenderPayload,
)
from app.schemas.wholesale import PaymentCreate
from app.seed_history import _backdate_sale
from app.services import customer_service, sale_service, weighed
from app.services.demo_catalog import _NAMESPACE, _owner, _ref, _session
from app.services.returns_service import apply_return, prorated_tax, restocking_fee, returns_policy
from app.services.tax import entered_includes_tax, line_tax
from app.services.tax import policy as tax_policy
from app.tenancy.context import use_tenant
from app.tenancy.models import Tenant

_RETURNABLE = {
    "restaurant": "RST-JUICE",
    "supermarket": "GRO-WATER",
    "electronics": "EL-CABLE",
    "fashion": "FSH-OX-S-SND",
}
_DAYS = 30


def _by_sku(db: Session, sku: str) -> Product:
    product = db.scalar(select(Product).where(Product.sku == sku))
    if product is None:
        raise RuntimeError(f"Demo product {sku} is missing.")
    return product


def _customer(db: Session, name: str) -> Customer:
    found = db.scalar(select(Customer).where(Customer.name == name))
    if found is None:
        raise RuntimeError(f"Demo customer {name} is missing.")
    return found


def _pool(db: Session, store: Store) -> list[Product]:
    rows = db.scalars(
        select(Product)
        .where(
            Product.is_active.is_(True),
            Product.price_cents > 0,
            Product.is_ingredient.is_(False),
            Product.is_serialized.is_(False),
            Product.sold_by_weight.is_(False),
            Product.item_type != "MADE_TO_ORDER",
        )
        .order_by(Product.sku)
    ).all()
    sellable = []
    for product in rows:
        level = db.scalar(
            select(InventoryLevel).where(InventoryLevel.product_id == product.id, InventoryLevel.store_id == store.id)
        )
        if product.sku == "GRO-MILK":
            continue
        if level is not None and level.quantity_on_hand > 40:
            sellable.append(product)
    return sellable


def _money(
    db: Session, store: Store, product: Product, quantity: int, unit_price: int, discount: int
) -> tuple[int, int, int]:
    charged = weighed.amount(quantity, unit_price, weighed.scale_of(product)) - discount
    rule = tax_policy(db, store.id)
    if not rule.enforced:
        return charged, 0, charged
    priced = line_tax(charged, 1, rule.rate_for(product.tax_category), inclusive=entered_includes_tax(product))
    return priced.net_cents, priced.tax_cents, priced.line_total_cents


def _ring(
    db: Session,
    settings: Settings,
    *,
    user: User,
    store: Store,
    client_id: str,
    when: datetime,
    lines: list[tuple[Product, int, int, int, uuid.UUID | None, list[ModifierChoice], str | None]],
    customer: Customer | None,
    method: str,
    sale_type: str,
    service_charge: int,
    split: bool,
) -> None:
    if db.scalar(select(Sale.id).where(Sale.client_sale_id == client_id)) is not None:
        return
    items: list[SaleItemPayload] = []
    net = tax_cents = 0
    for product, quantity, unit_price, discount, promotion_id, modifiers, serial in lines:
        line_net, line_tax_cents, line_total = _money(db, store, product, quantity, unit_price, discount)
        items.append(
            SaleItemPayload(
                id=uuid.uuid5(_NAMESPACE, f"{client_id}:{product.sku}"),
                product_id=product.id,
                quantity=quantity,
                unit_price_cents=unit_price,
                tax_cents=line_tax_cents,
                line_total_cents=line_total,
                discount_cents=discount,
                promotion_id=promotion_id,
                modifiers=modifiers,
                serial_value=serial,
                serial_kind="serial" if serial else None,
            )
        )
        net += line_net
        tax_cents += line_tax_cents
    rule = tax_policy(db, store.id)
    service_tax = 0
    if service_charge and rule.enforced:
        service_tax = line_tax(service_charge, 1, rule.standard_rate_bps, inclusive=False).tax_cents
    total = net + tax_cents + service_charge + service_tax
    if method == "on_account":
        tenders = [SaleTenderPayload(method="on_account", amount_cents=total)]
    elif split:
        first = max(1, total // 2)
        tenders = [
            SaleTenderPayload(method="cash", amount_cents=first),
            SaleTenderPayload(method="cash", amount_cents=total - first),
        ]
    else:
        tenders = [SaleTenderPayload(method="cash", amount_cents=total)]
    payload = SalePayload(
        id=uuid.uuid5(_NAMESPACE, client_id),
        store_id=store.id,
        cashier_id=user.id,
        currency=store.currency,
        payment_method=method,
        subtotal_cents=net + service_charge,
        tax_cents=tax_cents + service_tax,
        total_cents=total,
        client_sale_id=client_id,
        items=items,
        sale_type=sale_type,
        customer_id=customer.id if customer is not None else None,
        tenders=tenders,
        sold_at=datetime.now(UTC),
        service_charge_cents=service_charge,
        service_charge_tax_cents=service_tax,
    )
    sale = sale_service.record_sale(db, settings, payload)
    _backdate_sale(db, sale, when, customer)
    db.commit()


def _plain(product: Product, quantity: int = 1) -> tuple:
    return (product, quantity, product.price_cents, 0, None, [], None)


def _lines_for(
    db: Session,
    spec: dict,
    store: Store,
    index: int,
    rng: random.Random,
    pool: list[Product],
) -> tuple[list, Customer | None, str, str, int, bool]:
    """One day's lines, the customer, the tender, the sale type, service charge, and whether to split cash."""
    code = spec["code"]
    retail = _customer(db, spec["customers"][0]["name"])
    if index == 0:
        return [_plain(_by_sku(db, _RETURNABLE[code]))], retail, "cash", "RETAIL", 0, False
    if code == "restaurant" and index == 1:
        coffee = _by_sku(db, "RST-COFFEE")
        group = db.scalar(select(ModifierGroup).where(ModifierGroup.name == spec["modifier"]["group"]))
        option = group.options[0]
        choice = ModifierChoice(
            group_id=group.id,
            option_id=option.id,
            group=group.name,
            option=option.name,
            price_delta_cents=option.price_delta_cents,
        )
        cake = _by_sku(db, "RST-CAKE")
        return (
            [
                (coffee, 1, coffee.price_cents + option.price_delta_cents, 0, None, [choice], None),
                _plain(cake),
            ],
            retail,
            "cash",
            "RETAIL",
            0,
            False,
        )
    if code == "restaurant" and index == 2:
        return [_plain(_by_sku(db, "RST-WRAP"), 2)], retail, "cash", "RETAIL", 500, True
    if code == "supermarket" and index == 1:
        bananas = _by_sku(db, "GRO-BANANA")
        return [(bananas, 750, bananas.price_cents, 0, None, [], None)], retail, "cash", "RETAIL", 0, False
    if code == "supermarket" and index == 3:
        milk = _by_sku(db, "GRO-MILK")
        return [_plain(milk, 8)], retail, "cash", "RETAIL", 0, False
    if code == "electronics" and index == 1:
        phone = _by_sku(db, "EL-PHONE")
        return [(phone, 1, phone.price_cents, 0, None, [], "SN-EL-0001")], retail, "cash", "RETAIL", 0, False
    if code == "electronics" and index in {2, 4}:
        wholesale = _customer(db, "Noor Trading LLC")
        product = _by_sku(db, "EL-CASE" if index == 2 else "EL-CHARGER")
        return [_plain(product, 2)], wholesale, "on_account", "WHOLESALE", 0, False
    promo = _promo_line(db, spec, index)
    if promo is not None:
        return [promo], retail, "cash", "RETAIL", 0, False
    picked = rng.sample(pool, k=min(2, len(pool)))
    customer = retail if index % 2 == 0 else None
    return [_plain(product, 1) for product in picked], customer, "cash", "RETAIL", 0, False


def _promo_line(db: Session, spec: dict, index: int) -> tuple | None:
    if index != 5 or spec["code"] not in {"supermarket", "fashion"}:
        return None
    sku = "GRO-RICE" if spec["code"] == "supermarket" else "FSH-OX-S-NVY"
    product = _by_sku(db, sku)
    promotion = db.scalar(select(Promotion).where(Promotion.name == f"{spec['name']} 10% off"))
    if promotion is None:
        return _plain(product)
    gross = weighed.amount(1, product.price_cents, weighed.scale_of(product))
    discount = (gross * int((promotion.params or {}).get("percent_bps") or 0)) // 10_000
    if discount < 1:
        return _plain(product)
    return (product, 1, product.price_cents, discount, promotion.id, [], None)


def _refund(db: Session, settings: Settings, spec: dict, user: User, store: Store) -> None:
    client_id = f"dm-{spec['code']}-000"
    sale = db.scalar(select(Sale).where(Sale.client_sale_id == client_id).options(selectinload(Sale.items)))
    if sale is None or sale.status == "refunded":
        return
    from app.models.sale_return import SaleReturn

    return_id = uuid.uuid5(_NAMESPACE, f"{client_id}:return")
    if db.get(SaleReturn, return_id) is not None:
        return
    policy = returns_policy(db)
    condition = next(row for row in policy.conditions if row.restock and row.fee_bps == 0)
    reason = "changed_mind" if any(row.key == "changed_mind" for row in policy.reasons) else policy.reasons[0].key
    item = sale.items[0]
    product = db.get(Product, item.product_id)
    scale = weighed.scale_of(product)
    tax_refund = prorated_tax(item.tax_cents, item.quantity, item.quantity, 0, 0)
    fee = restocking_fee(item.unit_price_cents, item.quantity, condition.fee_bps, scale)
    subtotal = weighed.amount(item.quantity, item.unit_price_cents, scale) - int(item.discount_cents or 0)
    refund = subtotal + tax_refund - fee
    payload = ReturnPayload(
        id=return_id,
        original_sale_id=sale.id,
        store_id=store.id,
        cashier_id=user.id,
        currency=sale.currency,
        processed_at=datetime.now(UTC),
        subtotal_cents=subtotal,
        tax_refund_cents=tax_refund,
        restocking_fee_cents=fee,
        total_refund_cents=refund,
        reason_notes="Demo customer changed their mind.",
        items=[
            ReturnItemPayload(
                id=uuid.uuid5(return_id, "line"),
                sale_item_id=item.id,
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price_cents=item.unit_price_cents,
                tax_refund_cents=tax_refund,
                restocking_fee_cents=fee,
                refund_cents=refund,
                condition_status=condition.key,
                reason_code=reason,
            )
        ],
        tenders=[ReturnTenderPayload(method="cash", amount_cents=refund)],
    )
    apply_return(db, settings, payload.model_dump(mode="json"))
    db.commit()


def _collect(db: Session, spec: dict, user: User) -> None:
    if spec["code"] != "electronics":
        return
    customer = _customer(db, "Noor Trading LLC")
    if customer.current_balance_cents <= 0:
        return
    payment = min(10_000, customer.current_balance_cents)
    # A second seed finds the balance already reduced and would post another receipt. The reference is the guard.
    from app.models.customer import CustomerLedgerEntry

    if db.scalar(select(CustomerLedgerEntry.id).where(CustomerLedgerEntry.reference == "DEMO-RCPT")) is not None:
        return
    customer_service.receive_payment(
        db,
        customer.id,
        PaymentCreate(
            amount_cents=payment,
            method="cash",
            reference="DEMO-RCPT",
            note="Part payment on the demo account.",
        ),
        user.id,
    )


def seed_history(settings: Settings, spec: dict, tenant: Tenant) -> None:
    ref = _ref(tenant, settings)
    db = _session(settings, tenant)
    try:
        with use_tenant(ref):
            user = _owner(db)
            store = db.scalar(select(Store).where(Store.is_active.is_(True)).order_by(Store.code))
            if store is None:
                raise RuntimeError(f"{spec['slug']} has no store.")
            rng = random.Random(f"axiz-demo-{spec['code']}-{_DAYS}")
            pool = _pool(db, store)
            now = datetime.now(UTC).replace(microsecond=0)
            for index in range(_DAYS + 1):
                lines, customer, method, sale_type, service, split = _lines_for(db, spec, store, index, rng, pool)
                _ring(
                    db,
                    settings,
                    user=user,
                    store=store,
                    client_id=f"dm-{spec['code']}-{index:03d}",
                    when=now - timedelta(days=5 if index == 0 else max(0, _DAYS - index)),
                    lines=lines,
                    customer=customer,
                    method=method,
                    sale_type=sale_type,
                    service_charge=service,
                    split=split,
                )
            _refund(db, settings, spec, user, store)
            _collect(db, spec, user)
    finally:
        db.close()
