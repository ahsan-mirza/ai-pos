"""Recording sales (from register sync or quote conversion) and validating priced lines for sales and quotes.

Prices: a line's unit price must equal the list price the register showed unless a manager approved an
override. The list price is compared against the server's own tier/volume resolution, but a difference is
only audited, because an offline register can legitimately hold a slightly older price list."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import tax_authority
from app.core.config import Settings
from app.core.errors import SyncRejected
from app.core.permissions import Permission
from app.core.security import encrypt_value
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.device import Device
from app.models.product import Product
from app.models.restaurant import OpenOrder
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sale_tender import SaleTender
from app.models.serial_number import SerialNumber
from app.models.store import Store
from app.models.user import User
from app.schemas.payloads import PriceOverridePayload, SaleItemPayload, SalePayload
from app.services import (
    batch_ledger,
    cheque_service,
    combo_service,
    costing,
    credit_service,
    discount_service,
    fx_service,
    gift_card_service,
    ledger_service,
    loyalty_service,
    margin_service,
    menu_service,
    messaging_service,
    payment_service,
    price_list_service,
    promotion_service,
    recipe_service,
    store_credit_service,
    trade_in_service,
    uom_service,
    warranty_service,
    weighed,
)
from app.services.identifiers import identifier_hash, identifier_suffix, normalize_identifier
from app.services.inventory import level_for, move_stock, transition_serial
from app.services.numbering import accept_register_number, next_server_number
from app.services.settings_service import cached_settings
from app.services.sync_validation import register_time, require_cashier, require_store
from app.services.tax import TaxPolicy, for_customer, line_tax
from app.services.tax import policy as tax_policy_for

UNSELLABLE_SERIAL = {
    "defective": "marked defective",
    "repair": "in repair",
    "quarantine": "in quarantine",
    "scrapped": "written off",
    "reversed": "removed by a reversed purchase import",
}


@dataclass
class PricedLine:
    item: SaleItemPayload
    product: Product
    approver: User | None
    tax_rate_bps: int | None = None
    # Set when the unit price is below the margin floor.
    floor_cents: int | None = None
    floor_approver: User | None = None
    # Snapshot of the menu modifiers sold on this line.
    modifiers: list[dict] | None = None
    # Snapshot of the meal components sold on a combo line.
    components: list[dict] | None = None
    # Manager who approved a cashier discount above the cashier's own limit.
    discount_approver: User | None = None
    price_source: str | None = None
    price_list_id: uuid.UUID | None = None
    # The customer's treatment when it took this standard-rated line to 0%.
    tax_treatment: str | None = None


@dataclass
class PricedLines:
    """subtotal_cents is net of VAT; total_cents is what the customer pays."""

    lines: list[PricedLine]
    subtotal_cents: int
    tax_cents: int
    total_cents: int = 0
    mismatches: list[dict[str, object]] = field(default_factory=list)


# --- Lookups -------------------------------------------------------------------------------------


def require_customer(db: Session, customer_id: uuid.UUID | None) -> Customer | None:
    if customer_id is None:
        return None
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise SyncRejected("Customer does not exist.")
    return customer


def held_by_quote(db: Session, serial_id: uuid.UUID, *, except_quote: uuid.UUID | None = None) -> Sale | None:
    statement = (
        select(Sale)
        .join(SaleItem, SaleItem.sale_id == Sale.id)
        .where(SaleItem.serial_number_id == serial_id, Sale.quote_status == "OPEN")
    )
    if except_quote is not None:
        statement = statement.where(Sale.id != except_quote)
    return db.scalars(statement).first()


def quote_number(sale: Sale) -> str:
    return sale.invoice_number or f"Q-{sale.client_sale_id[:8].upper()}"


def invoice_label(sale: Sale) -> str:
    return sale.invoice_number or sale.client_sale_id[:8].upper()


AUDIT_ACTION_TYPES = {
    "price_override": "PRICE_OVERRIDE",
    "credit_limit_override": "CREDIT_LIMIT_OVERRIDE",
    "credit_limit_exceeded": "CREDIT_LIMIT_OVERRIDE",
    "credit_hold_override": "CREDIT_LIMIT_OVERRIDE",
    "credit_hold_bypassed": "CREDIT_LIMIT_OVERRIDE",
    "below_floor_override": "PRICE_OVERRIDE",
    "below_floor_unapproved": "PRICE_OVERRIDE",
    "price_list_mismatch": "CREATE",
    "promotion_mismatch": "PRICE_OVERRIDE",
    "manual_card_entry": "UPDATE",
    "manual_card_unapproved": "UPDATE",
    "discount": "PRICE_OVERRIDE",
}


def audit(
    db: Session,
    *,
    store_id: uuid.UUID,
    actor_id: uuid.UUID,
    action: str,
    entity_id: uuid.UUID,
    details: dict[str, object],
    approver_id: uuid.UUID | None = None,
    reason: str | None = None,
    client_device: str = "desktop",
) -> None:
    actor = db.get(User, actor_id)
    db.add(
        AuditLog(
            user_id=actor_id,
            approver_id=approver_id,
            store_id=store_id,
            action_type=AUDIT_ACTION_TYPES[action],
            action=f"sale.{action}",
            target_entity="sale",
            target_entity_id=entity_id,
            details=details,
            reason_notes=reason or None,
            client_device=client_device,
            user_name=actor.full_name if actor is not None else None,
            user_role=actor.role.name if actor is not None and actor.role is not None else None,
        )
    )


def _approver(
    db: Session,
    approved_by_id: uuid.UUID,
    *,
    permission: Permission,
    store_id: uuid.UUID,
    label: str,
) -> User:
    approver = db.get(User, approved_by_id)
    if approver is None:
        raise SyncRejected(f"The manager approving the {label} does not exist.")
    if permission.value not in approver.permissions:
        raise SyncRejected(f"The approving manager cannot approve the {label}.")
    if approver.store_id is not None and approver.store_id != store_id:
        raise SyncRejected("The approving manager is not assigned to this store.")
    return approver


def _audit_manual_card(db: Session, data: SalePayload, tenders: list, sold_at: datetime) -> None:
    """Card legs that bypassed the store's integrated terminal (offline, or the terminal was down) are accepted,
    since the customer has already paid, but each is audited: with the approving manager, or as unapproved."""
    from app.services import integrated_payment_service

    manual = [tender for tender in tenders if tender.method == "card" and tender.payment_intent_id is None]
    if not manual or not integrated_payment_service.card_terminal_required(db, data.store_id, at=sold_at):
        return
    for tender in manual:
        override = tender.manual_override
        approver = (
            _approver(
                db,
                override.approved_by_id,
                permission=Permission.POS_PRICE_OVERRIDE,
                store_id=data.store_id,
                label="manual card entry",
            )
            if override is not None
            else None
        )
        audit(
            db,
            store_id=data.store_id,
            actor_id=data.cashier_id,
            approver_id=approver.id if approver is not None else None,
            action="manual_card_entry" if approver is not None else "manual_card_unapproved",
            entity_id=data.id,
            details={"amount_cents": tender.amount_cents, "reference": tender.reference},
            reason=override.note if override is not None else None,
        )


def _service_charge_tax(db: Session, data: SalePayload) -> int:
    """VAT on the service charge: standard rate on the charge when it is taxable and VAT is enforced."""
    if data.service_charge_cents == 0:
        if data.service_charge_tax_cents:
            raise SyncRejected("Service charge VAT without a service charge.")
        return 0
    policy = tax_policy_for(db)
    taxable = cached_settings(db).module_settings.tips_service_charge.service_charge_taxable
    if not policy.enforced:
        # Legacy registers keep the tax they sent, as for lines.
        return data.service_charge_tax_cents
    expected = (
        line_tax(data.service_charge_cents, 1, policy.standard_rate_bps, inclusive=False).tax_cents if taxable else 0
    )
    if data.service_charge_tax_cents != expected:
        raise SyncRejected(f"VAT on the service charge should be {expected / 100:.2f}.")
    return expected


def _tip_user(db: Session, data: SalePayload) -> User | None:
    if data.tip_cents == 0:
        return None
    user = db.get(User, data.tip_user_id or data.cashier_id)
    if user is None:
        raise SyncRejected("The member of staff receiving the tip does not exist.")
    return user


def override_approver(db: Session, override: PriceOverridePayload, store_id: uuid.UUID) -> User:
    return _approver(
        db, override.approved_by_id, permission=Permission.POS_PRICE_OVERRIDE, store_id=store_id, label="price override"
    )


# --- Line validation -----------------------------------------------------------------------------


def price_lines(
    db: Session,
    *,
    items: list[SaleItemPayload],
    store_id: uuid.UUID,
    currency: str,
    tier: str,
    quote: bool,
    tax_policy: TaxPolicy | None = None,
    cashier: User | None = None,
    customer: Customer | None = None,
    at: datetime | None = None,
) -> PricedLines:
    """Validates every line. With an enforced tax policy the API recomputes each line's VAT itself.

    Prices are only audited: a listed price any valid price list offers is accepted as it is."""
    products: dict[uuid.UUID, Product] = {}
    pieces: dict[uuid.UUID, int] = {}
    for item in items:
        product = products.get(item.product_id) or db.get(Product, item.product_id)
        if product is None:
            raise SyncRejected("Product does not exist.")
        products[product.id] = product
        pieces[product.id] = pieces.get(product.id, 0) + item.quantity

    moment = at or datetime.now(UTC)
    entries = price_list_service.entries_for(db, set(products), currency=currency, store_id=store_id, customer=customer)
    customer_policy = for_customer(tax_policy, customer, moment.date()) if tax_policy is not None else None
    enforced = tax_policy is not None and tax_policy.enforced
    policies = margin_service.active_policies(db)
    priced = PricedLines(lines=[], subtotal_cents=0, tax_cents=0)
    for item in items:
        product = products[item.product_id]
        if quote and item.discount_cents:
            raise SyncRejected("Promotions apply at checkout, not on quotes.")
        scale = weighed.scale_of(product)
        gross = weighed.amount(item.quantity, item.unit_price_cents, scale)
        charged = gross - item.discount_cents - item.manual_discount_cents
        if charged < 0:
            raise SyncRejected("The discount cannot exceed the line's value.")
        discount_approver = (
            discount_service.check_line(
                db, item, product=product, before_cents=gross - item.discount_cents, cashier=cashier, store_id=store_id
            )
            if item.manual_discount_cents
            else None
        )
        if item.gift_card_code is not None:
            if quote:
                raise SyncRejected("Gift cards are sold at checkout, not on quotes.")
            gift_card_service.check_sale_line(db, item, product)
        elif product.sku == gift_card_service.GIFT_CARD_SKU:
            raise SyncRejected("A gift card line must carry the card's code.")
        if product.sold_by_weight:
            if item.unit_type != "PIECE" or item.serial_value is not None:
                raise SyncRejected(f"{product.name} is sold by weight, in grams.")
            if item.discount_cents:
                raise SyncRejected("Promotions do not apply to weighed items.")
        rate: int | None = None
        treatment: str | None = None
        if enforced and tax_policy is not None and customer_policy is not None:
            rate = customer_policy.rate_for(product.tax_category)
            expected = line_tax(charged, 1, rate, inclusive=tax_policy.prices_include_vat)
            standard_rate = tax_policy.rate_for(product.tax_category)
            if rate != standard_rate:
                treatment = customer_policy.treatment
                standard = line_tax(charged, 1, standard_rate, inclusive=tax_policy.prices_include_vat)
                # A register that did not know the customer's treatment charged standard VAT: keep it.
                if (item.tax_cents, item.line_total_cents) == (standard.tax_cents, standard.line_total_cents):
                    rate, expected, treatment = standard_rate, standard, None
            if item.tax_cents != expected.tax_cents:
                raise SyncRejected(
                    f"VAT on {product.name} should be {expected.tax_cents / 100:.2f}, not {item.tax_cents / 100:.2f}."
                )
            if item.line_total_cents != expected.line_total_cents:
                raise SyncRejected("Line total does not match unit price, quantity, discount, and VAT.")
            net = expected.net_cents
        else:
            if item.line_total_cents != charged + item.tax_cents:
                raise SyncRejected("Line total does not match unit price, quantity, discount, and tax.")
            net = charged
        if product.currency != currency:
            raise SyncRejected("Product currency does not match the sale.")
        if product.is_serialized:
            if item.unit_type != "PIECE":
                raise SyncRejected("Serialized products are sold by the piece.")
            assigned = item.serial_value is not None and item.serial_kind is not None
            if quote:
                if assigned and item.quantity != 1:
                    raise SyncRejected("A quote line with an IMEI or serial number covers exactly one unit.")
            elif item.quantity != 1 or not assigned:
                raise SyncRejected("Serialized products require one IMEI or serial number.")
        else:
            if item.serial_value is not None:
                raise SyncRejected("Serial numbers are only valid for serialized products.")
            if item.unit_type != "PIECE" and item.unit_type not in (product.sellable_units or []):
                pack = uom_service.label(db, item.unit_type).lower()
                raise SyncRejected(f"{product.name} is not sold by the {pack}.")
        factor = uom_service.factor_of(db, item.unit_type)
        if factor is None:
            raise SyncRejected(f"Unknown unit {item.unit_type}.")
        if item.quantity % factor != 0:
            pack = uom_service.label(db, item.unit_type)
            raise SyncRejected(f"{product.name}: quantity must be a whole number of {pack}.")

        approver = None
        modifier_delta, modifiers = 0, None
        combo_delta, components = 0, None
        price_source: str | None = None
        price_list_id: uuid.UUID | None = None
        if item.gift_card_code is not None:
            pass
        elif product.is_open_price:
            if item.modifiers or item.components:
                raise SyncRejected("Open-price items do not take modifiers.")
            if cashier is not None and Permission.POS_OPEN_PRICE.value not in cashier.permissions:
                raise SyncRejected(f"{cashier.full_name} cannot sell open-price items.")
        else:
            modifier_delta, modifiers = menu_service.price_choices(db, product, item.modifiers)
            combo_delta, components = combo_service.price_components(db, product, item.components)
            listed = item.list_price_cents if item.list_price_cents is not None else item.unit_price_cents
            if item.unit_price_cents != listed:
                if item.price_override is None:
                    raise SyncRejected(f"A manager must approve the price change on {product.name}.")
                approver = override_approver(db, item.price_override, store_id)
            resolved = price_list_service.resolve_for(
                product,
                tier,
                pieces[product.id],
                entries.get(product.id, []),
                customer=customer,
                store_id=store_id,
                at=moment,
            )
            extras = modifier_delta + combo_delta
            if listed == resolved.price_cents + extras:
                price_source = resolved.source
                price_list_id = uuid.UUID(resolved.price_list_id) if resolved.price_list_id else None
            elif listed - extras not in resolved.candidates:
                priced.mismatches.append(
                    {
                        "product_id": str(product.id),
                        "listed_cents": listed,
                        "server_cents": resolved.price_cents + extras,
                    }
                )
        floor_cents, floor_approver = None, None
        # Promotion discounts were approved when the promotion was set up, so only the shelf price meets the floor.
        floor = margin_service.floor_for(db, product, store_id, tax_policy or TaxPolicy(False, False, 0), policies)
        if floor is not None and item.unit_price_cents < floor.floor_cents:
            floor_cents = floor.floor_cents
            if item.below_floor_override is not None:
                floor_approver = _approver(
                    db,
                    item.below_floor_override.approved_by_id,
                    permission=Permission.POS_BELOW_FLOOR_OVERRIDE,
                    store_id=store_id,
                    label="below-floor price",
                )
        priced.subtotal_cents += net
        priced.tax_cents += item.tax_cents
        priced.total_cents += item.line_total_cents
        priced.lines.append(
            PricedLine(
                item=item,
                product=product,
                approver=approver,
                tax_rate_bps=rate,
                floor_cents=floor_cents,
                floor_approver=floor_approver,
                modifiers=modifiers,
                components=components,
                discount_approver=discount_approver,
                price_source=price_source,
                price_list_id=price_list_id,
                tax_treatment=treatment,
            )
        )
    return priced


def _meal_parts(db: Session, lines: list[PricedLine]) -> dict[uuid.UUID, list[Product]]:
    """Component products of each combo line, keyed by sale line id."""
    ids = {part for line in lines for part in combo_service.component_ids(line.components)}
    if not ids:
        return {}
    products = {product.id: product for product in db.scalars(select(Product).where(Product.id.in_(ids)))}
    return {
        line.item.id: [products[part] for part in combo_service.component_ids(line.components) if part in products]
        for line in lines
        if line.components
    }


def _cost_meals(
    db: Session, lines: list[PricedLine], parts: dict[uuid.UUID, list[Product]], dishes: set[uuid.UUID]
) -> None:
    """A meal line costs what its parts cost: recipe draws (written by recipe_service) plus stocked parts."""
    for line in lines:
        found = parts.get(line.item.id)
        item = db.get(SaleItem, line.item.id) if found else None
        if not found or item is None:
            continue
        cooked = any(part.id in dishes for part in found)
        total = (item.cost_cents or 0) if cooked else 0
        estimated = item.cost_estimated if cooked else False
        for part in found:
            if part.id in dishes or part.is_service:
                continue
            unit = costing.fallback_unit_cost(db, part.id)
            # Parts are drawn without their own sale line, so they are costed at the latest purchase cost.
            estimated = True
            if unit is not None:
                total += unit * line.item.quantity
        item.cost_cents = total
        item.cost_estimated = estimated
    db.flush()


# --- Serial numbers ------------------------------------------------------------------------------


def write_serial(
    db: Session,
    settings: Settings,
    *,
    serial_id: uuid.UUID,
    product: Product,
    store_id: uuid.UUID,
    kind: str,
    raw_value: str,
    status: str,
) -> uuid.UUID:
    normalized = normalize_identifier(kind, raw_value)
    digest = identifier_hash(normalized)
    existing = db.scalar(select(SerialNumber).where(SerialNumber.value_hash == digest))
    if existing is not None and existing.id != serial_id:
        raise SyncRejected("Identifier is already registered.")
    row = existing if existing is not None else db.get(SerialNumber, serial_id)
    if row is not None and row.status == "sold" and status != "sold":
        raise SyncRejected("A sold identifier cannot return to stock.")
    if row is not None and row.status == "in_transit":
        raise SyncRejected("Identifier is on a stock transfer. Receive the transfer first.")
    encrypted = encrypt_value(normalized, settings)
    if row is None:
        row = SerialNumber(
            id=serial_id,
            product_id=product.id,
            store_id=store_id,
            kind=kind,
            value_hash=digest,
            value_encrypted=encrypted,
            value_suffix=identifier_suffix(normalized),
            status="registered",
        )
        db.add(row)
        db.flush()
    elif row.product_id != product.id:
        raise SyncRejected("Identifier belongs to a different product.")
    row.kind = kind
    row.value_hash = digest
    row.value_encrypted = encrypted
    row.value_suffix = identifier_suffix(normalized)
    transition_serial(
        db,
        row,
        status=status,
        store_id=store_id,
        movement_type="AUDIT_ADJUSTMENT",
        reference_type="serial_upsert",
        reference_id=row.id,
    )
    return row.id


def sellable_serial(
    db: Session,
    *,
    product: Product,
    store_id: uuid.UUID,
    kind: str,
    raw_value: str,
    except_quote: uuid.UUID | None = None,
) -> tuple[str, SerialNumber | None]:
    """Raises unless the unit can be sold or quoted at this branch. Unknown identifiers return None."""
    normalized = normalize_identifier(kind, raw_value)
    existing = db.scalar(select(SerialNumber).where(SerialNumber.value_hash == identifier_hash(normalized)))
    if existing is None:
        return normalized, None
    if existing.product_id != product.id:
        raise SyncRejected("Identifier belongs to a different product.")
    if existing.status == "sold":
        raise SyncRejected("Identifier is already sold.")
    if existing.status == "in_transit":
        raise SyncRejected("Identifier is on a stock transfer and cannot be sold until it is received.")
    if existing.status in UNSELLABLE_SERIAL:
        raise SyncRejected(f"Identifier is {UNSELLABLE_SERIAL[existing.status]}.")
    if existing.status == "in_stock" and existing.store_id != store_id:
        branch = db.get(Store, existing.store_id)
        where = branch.code if branch is not None else "another branch"
        raise SyncRejected(f"Identifier is in stock at {where}. Transfer it first.")
    holder = held_by_quote(db, existing.id, except_quote=except_quote)
    if holder is not None:
        raise SyncRejected(f"Identifier is reserved on quote {quote_number(holder)}.")
    return normalized, existing


def consume_serial(
    db: Session,
    settings: Settings,
    *,
    product: Product,
    store_id: uuid.UUID,
    kind: str,
    raw_value: str,
    sale_id: uuid.UUID,
    cashier_id: uuid.UUID,
    except_quote: uuid.UUID | None = None,
) -> uuid.UUID:
    normalized, existing = sellable_serial(
        db, product=product, store_id=store_id, kind=kind, raw_value=raw_value, except_quote=except_quote
    )
    if existing is None:
        # Units sold before they were ever received are recorded as sold without touching branch stock.
        return write_serial(
            db,
            settings,
            serial_id=uuid.uuid4(),
            product=product,
            store_id=store_id,
            kind=kind,
            raw_value=normalized,
            status="sold",
        )
    if existing.status == "in_stock" and level_for(db, product.id, store_id).available < 1:
        raise SyncRejected(f"Every {product.name} at this branch is reserved on open quotes.")
    transition_serial(
        db,
        existing,
        status="sold",
        store_id=store_id,
        movement_type="SALE_OUT",
        reference_type="sale",
        reference_id=sale_id,
        user_id=cashier_id,
    )
    return existing.id


# --- Sales ---------------------------------------------------------------------------------------


def record_sale(
    db: Session,
    settings: Settings,
    data: SalePayload,
    *,
    except_quote: uuid.UUID | None = None,
    device: Device | None = None,
    allow_deposit: bool = False,
) -> Sale:
    store = require_store(db, data.store_id)
    if store.currency != data.currency:
        raise SyncRejected("Sale currency must match the store currency.")
    cashier = require_cashier(db, data.cashier_id, data.store_id)
    associate_id = None
    if data.sales_associate_id is not None and data.sales_associate_id != data.cashier_id:
        try:
            associate_id = require_cashier(db, data.sales_associate_id, data.store_id).id
        except SyncRejected as error:
            raise SyncRejected(str(error).replace("Cashier", "The sales associate", 1)) from error
    if db.get(Sale, data.id) is not None:
        raise SyncRejected("Sale already exists.")
    if db.scalar(select(Sale).where(Sale.client_sale_id == data.client_sale_id)) is not None:
        raise SyncRejected("Client sale id already exists.")
    now = datetime.now(UTC)
    sold_at = register_time(
        data.sold_at if data.sold_at is not None else now,
        now=now,
        message="The sale is dated in the future. Check the register's clock.",
    )
    if sold_at < now - timedelta(days=settings.sale_max_age_days):
        raise SyncRejected(f"The sale is older than {settings.sale_max_age_days} days and needs a manual entry.")
    customer = require_customer(db, data.customer_id)
    tier = price_list_service.tier_for(data.sale_type, customer, db)
    promotion_service.require_known(db, data)

    priced = price_lines(
        db,
        items=data.items,
        store_id=data.store_id,
        currency=data.currency,
        tier=tier,
        quote=False,
        tax_policy=tax_policy_for(db),
        cashier=cashier,
        customer=customer,
        at=sold_at,
    )
    service_tax = _service_charge_tax(db, data)
    if (
        data.subtotal_cents != priced.subtotal_cents + data.service_charge_cents
        or data.tax_cents != priced.tax_cents + service_tax
        or data.total_cents != priced.total_cents + data.service_charge_cents + service_tax
    ):
        raise SyncRejected("Sale totals do not match line items.")
    tip_user = _tip_user(db, data)
    if data.invoice_number is not None:
        taken = db.scalar(select(Sale.id).where(Sale.invoice_number == data.invoice_number))
        invoice_number = accept_register_number(
            db,
            number=data.invoice_number,
            store_id=data.store_id,
            device=device,
            doc_type="INV",
            taken=taken is not None,
        )
    else:
        invoice_number = next_server_number(db, data.store_id, "INV")

    tenders = data.resolved_tenders()
    if except_quote is None and not allow_deposit and any(tender.method == "deposit" for tender in tenders):
        raise SyncRejected("Deposit tenders only come from converting a layaway or invoicing a repair.")
    if any(tender.method == "channel" for tender in tenders):
        order = db.get(OpenOrder, data.order_id) if data.order_id is not None else None
        if order is None or order.channel_id is None:
            raise SyncRejected("Delivery-app tenders only settle delivery-app orders.")
    on_account = sum(tender.amount_cents for tender in tenders if tender.method == "on_account")
    loyalty_cents = sum(tender.amount_cents for tender in tenders if tender.method == "loyalty")
    if loyalty_cents or data.loyalty_points_redeemed:
        loyalty_service.check_redemption(db, customer, data.loyalty_points_redeemed, loyalty_cents)
    paid = data.total_cents - on_account
    credit_approver: User | None = None
    if on_account:
        if customer is None or customer.customer_type != "WHOLESALE":
            raise SyncRejected("On-account sales need a wholesale customer.")
        if Permission.POS_CREDIT_SALE.value not in cashier.permissions:
            raise SyncRejected("Cashier cannot sell on account.")
        if data.credit_override is not None:
            credit_approver = _approver(
                db,
                data.credit_override.approved_by_id,
                permission=Permission.CUSTOMERS_MANAGE,
                store_id=data.store_id,
                label="credit limit override",
            )
        credit_service.refresh(db, settings, customer)
        if customer.credit_hold:
            # Registers sell offline, so a held account is recorded and flagged rather than rejected after the fact.
            audit(
                db,
                store_id=data.store_id,
                actor_id=data.cashier_id,
                approver_id=credit_approver.id if credit_approver is not None else None,
                action="credit_hold_override" if credit_approver is not None else "credit_hold_bypassed",
                entity_id=data.id,
                details={"customer_id": str(customer.id), "reason": customer.credit_hold_reason or ""},
            )

    # A meal draws nothing itself: each component it was sold with draws its own stock or recipe.
    parts = _meal_parts(db, priced.lines)
    # Dishes with a recipe carry no stock of their own: their ingredients are drawn once the sale is recorded.
    dishes = (
        recipe_service.recipe_product_ids(
            db, {line.product.id for line in priced.lines} | {part.id for found in parts.values() for part in found}
        )
        if recipe_service.recipes_enabled(db)
        else set()
    )
    demand: dict[uuid.UUID, int] = {}
    for line in priced.lines:
        for product in (line.product, *parts.get(line.item.id, ())):
            if product.is_ingredient:
                raise SyncRejected(f"{product.name} is an ingredient and is not sold on its own.")
            # Open-price lines (labour, unlisted accessories) are not stocked items.
            stocked = (
                product.is_stock_tracked
                and not product.is_serialized
                and not product.is_open_price
                and not product.is_service
            )
            if stocked and product.id not in dishes:
                demand[product.id] = demand.get(product.id, 0) + line.item.quantity
    for product_id, quantity in demand.items():
        if level_for(db, product_id, data.store_id).available < quantity:
            raise SyncRejected("Insufficient stock.")

    serial_ids: list[uuid.UUID | None] = []
    for line in priced.lines:
        item = line.item
        if line.product.is_serialized and item.serial_kind is not None and item.serial_value is not None:
            serial_ids.append(
                consume_serial(
                    db,
                    settings,
                    product=line.product,
                    store_id=data.store_id,
                    kind=item.serial_kind,
                    raw_value=item.serial_value,
                    sale_id=data.id,
                    cashier_id=data.cashier_id,
                    except_quote=except_quote,
                )
            )
        else:
            serial_ids.append(None)
    for product_id, quantity in demand.items():
        move_stock(
            db,
            product_id=product_id,
            store_id=data.store_id,
            quantity=-quantity,
            movement_type="SALE_OUT",
            reference_type="sale",
            reference_id=data.id,
            user_id=data.cashier_id,
        )

    sale = Sale(
        id=data.id,
        store_id=data.store_id,
        cashier_id=data.cashier_id,
        sales_associate_id=associate_id,
        status="completed",
        currency=data.currency,
        payment_method=data.payment_method,
        subtotal_cents=data.subtotal_cents,
        tax_cents=data.tax_cents,
        total_cents=data.total_cents,
        client_sale_id=data.client_sale_id,
        invoice_number=invoice_number,
        device_id=device.id if device is not None else None,
        shift_id=data.shift_id,
        sale_type=data.sale_type,
        customer_id=customer.id if customer is not None else None,
        is_quote_proforma=False,
        payment_status=ledger_service.payment_status(data.total_cents, paid),
        amount_paid_cents=paid,
        due_balance_cents=on_account,
        due_date=ledger_service.due_date_for(customer, sold_at) if customer is not None else None,
        order_id=data.order_id,
        service_charge_cents=data.service_charge_cents,
        service_charge_tax_cents=service_tax,
        tip_cents=data.tip_cents,
        tip_user_id=tip_user.id if tip_user is not None else None,
        created_at=sold_at,
        updated_at=now,
    )
    db.add(sale)
    for line, serial_id in zip(priced.lines, serial_ids, strict=True):
        item = line.item
        db.add(
            SaleItem(
                id=item.id,
                sale_id=data.id,
                product_id=item.product_id,
                serial_number_id=serial_id,
                quantity=item.quantity,
                unit_price_cents=item.unit_price_cents,
                tax_cents=item.tax_cents,
                line_total_cents=item.line_total_cents,
                unit_type=item.unit_type,
                unit_factor=uom_service.factor_of(db, item.unit_type) or 1,
                list_price_cents=item.list_price_cents,
                price_override_by_id=line.approver.id if line.approver is not None else None,
                tax_rate_bps=line.tax_rate_bps,
                description=(item.description or "").strip() or None,
                floor_cents=line.floor_cents,
                below_floor_approved_by_id=line.floor_approver.id if line.floor_approver is not None else None,
                discount_cents=item.discount_cents,
                promotion_id=item.promotion_id,
                manual_discount_cents=item.manual_discount_cents,
                discount_reason=item.discount_reason,
                discount_approved_by_id=line.discount_approver.id if line.discount_approver is not None else None,
                gift_card_code=item.gift_card_code,
                final_sale=bool(line.product.is_final_sale),
                modifiers=line.modifiers,
                components=line.components,
                price_source=line.price_source,
                price_list_id=line.price_list_id,
                tax_treatment=line.tax_treatment,
            )
        )
    for tender in tenders:
        fx_service.check_tender(db, settings, tender, data.currency)
        foreign = tender.currency is not None and tender.currency.upper() != data.currency
        db.add(
            SaleTender(
                sale_id=data.id,
                method=tender.method,
                amount_cents=tender.amount_cents,
                reference=tender.reference,
                currency=tender.currency.upper() if foreign and tender.currency else None,
                foreign_amount_cents=tender.foreign_amount_cents if foreign else None,
                rate_micros=tender.rate_micros if foreign else None,
                change_cents=tender.change_cents if foreign else None,
            )
        )
    db.flush()
    gift_card_service.issue_from_sale(db, sale, priced.lines, customer)
    for tender in tenders:
        if tender.method == "store_credit":
            store_credit_service.redeem(
                db,
                code=tender.store_credit_code,
                sale_id=data.id,
                store_id=data.store_id,
                amount_cents=tender.amount_cents,
                currency=data.currency,
            )
        if tender.method == "gift_card":
            if any(line.item.gift_card_code for line in priced.lines):
                raise SyncRejected("A gift card cannot be bought with another gift card.")
            store_credit_service.redeem(
                db,
                code=tender.gift_card_code,
                sale_id=data.id,
                store_id=data.store_id,
                amount_cents=tender.amount_cents,
                currency=data.currency,
                kind="GIFT_CARD",
            )
        if tender.method == "trade_in":
            trade_in_service.consume_for_sale(
                db, tender.trade_in_id, sale_id=data.id, store_id=data.store_id, amount_cents=tender.amount_cents
            )
        if tender.method == "qr":
            if tender.payment_intent_id is None:
                raise SyncRejected("QR tenders must reference the paid QR payment.")
            payment_service.consume_for_sale(
                db, tender.payment_intent_id, sale_id=data.id, amount_cents=tender.amount_cents, store_id=data.store_id
            )
        if tender.method in ("card", "bnpl") and tender.payment_intent_id is not None:
            payment_service.consume_for_sale(
                db,
                tender.payment_intent_id,
                sale_id=data.id,
                amount_cents=tender.amount_cents,
                store_id=data.store_id,
                method=tender.method,
            )
        if tender.cheque is not None:
            cheque_service.record(
                db,
                details=tender.cheque,
                amount_cents=tender.amount_cents,
                currency=data.currency,
                store_id=data.store_id,
                customer_id=customer.id if customer is not None else None,
                source="SALE",
                sale_id=data.id,
                user_id=data.cashier_id,
            )
    batch_ledger.link_sale(db, data.id)
    costing.cost_sale(db, data.id)
    sold_dishes = [
        recipe_service.SoldDish(line.item.id, line.product, line.item.quantity, line.modifiers)
        for line in priced.lines
        if line.product.id in dishes
    ] + [
        recipe_service.SoldDish(line.item.id, part, line.item.quantity, None)
        for line in priced.lines
        for part in parts.get(line.item.id, ())
        if part.id in dishes
    ]
    if sold_dishes:
        from app.services import fnb_service

        fnb_service.consume_sale(
            db, sale_id=data.id, store_id=data.store_id, user_id=data.cashier_id, dishes=sold_dishes
        )
    if parts:
        _cost_meals(db, priced.lines, parts, dishes)
    if data.order_id is not None:
        from app.services import order_service

        order_service.settle(db, data, sale.id)
    elif except_quote is None:
        from app.services import kitchen_service

        kitchen_service.fire_sale(db, sale, sold_at)
    warranty_service.register_sale(db, sale, customer)
    tax_authority.issue_for_sale(db, settings, sale, customer)

    if customer is not None:
        balance_before = customer.current_balance_cents
        paid_method = next((tender.method for tender in tenders if tender.method != "on_account"), None)
        ledger_service.post_sale(db, customer, sale, paid_method=paid_method, user_id=data.cashier_id)
        earned_on = (
            data.total_cents
            - on_account
            - loyalty_cents
            - sum(tender.amount_cents for tender in tenders if tender.method == "deposit")
        )
        loyalty_service.apply_sale(
            db,
            customer,
            sale_id=sale.id,
            paid_cents=earned_on,
            redeemed=data.loyalty_points_redeemed or 0,
            user_id=data.cashier_id,
        )
        messaging_service.enqueue(
            db,
            template_key="receipt",
            customer=customer,
            context={
                "invoice": sale.invoice_number or sale.client_sale_id[:8].upper(),
                "total": f"{sale.currency} {sale.total_cents / 100:,.2f}",
                "store": store.name,
            },
            dedupe_key=f"receipt:{sale.id}",
            attachment=("invoice", str(sale.id)),
        )
        if on_account and balance_before + on_account > customer.credit_limit_cents:
            audit(
                db,
                store_id=data.store_id,
                actor_id=data.cashier_id,
                approver_id=credit_approver.id if credit_approver is not None else None,
                action="credit_limit_override" if credit_approver is not None else "credit_limit_exceeded",
                entity_id=data.id,
                details={
                    "customer_id": str(customer.id),
                    "credit_limit_cents": customer.credit_limit_cents,
                    "balance_after_cents": customer.current_balance_cents,
                    "note": data.credit_override.note if data.credit_override is not None else "",
                },
            )
    for line in priced.lines:
        if line.approver is not None and line.item.price_override is not None:
            audit(
                db,
                store_id=data.store_id,
                actor_id=data.cashier_id,
                approver_id=line.approver.id,
                action="price_override",
                entity_id=data.id,
                details={
                    "product_id": str(line.product.id),
                    "list_price_cents": line.item.list_price_cents,
                    "unit_price_cents": line.item.unit_price_cents,
                    "note": line.item.price_override.note,
                },
            )
    for line in priced.lines:
        if line.floor_cents is not None:
            audit(
                db,
                store_id=data.store_id,
                actor_id=data.cashier_id,
                approver_id=line.floor_approver.id if line.floor_approver is not None else None,
                action="below_floor_override" if line.floor_approver is not None else "below_floor_unapproved",
                entity_id=data.id,
                details={
                    "product_id": str(line.product.id),
                    "floor_cents": line.floor_cents,
                    "unit_price_cents": line.item.unit_price_cents,
                },
                reason=line.item.below_floor_override.note if line.item.below_floor_override is not None else None,
            )
    for line in priced.lines:
        if line.item.manual_discount_cents:
            audit(
                db,
                store_id=data.store_id,
                actor_id=data.cashier_id,
                approver_id=line.discount_approver.id if line.discount_approver is not None else None,
                action="discount",
                entity_id=data.id,
                details={
                    "product_id": str(line.product.id),
                    "discount_cents": line.item.manual_discount_cents,
                    "reason": line.item.discount_reason,
                },
                reason=line.item.discount_override.note if line.item.discount_override is not None else None,
            )
    if priced.mismatches:
        audit(
            db,
            store_id=data.store_id,
            actor_id=data.cashier_id,
            action="price_list_mismatch",
            entity_id=data.id,
            details={"lines": priced.mismatches, "tier": tier},
        )
    _audit_manual_card(db, data, tenders, sold_at)
    issues = promotion_service.verify_and_redeem(db, data, sold_at=sold_at)
    if issues:
        audit(
            db,
            store_id=data.store_id,
            actor_id=data.cashier_id,
            action="promotion_mismatch",
            entity_id=data.id,
            details={"issues": issues, "coupon_code": data.coupon_code},
        )
    if data.order_id is not None:
        closed_order = db.get(OpenOrder, data.order_id)
        if closed_order is not None and closed_order.status == "SETTLED" and closed_order.table_id is not None:
            from app.models.restaurant import DiningTable
            from app.websockets.table_sync import publish

            table = db.get(DiningTable, closed_order.table_id)
            publish(
                closed_order.store_id,
                {
                    "type": "TABLE_SESSION_CLOSED",
                    "store_id": str(closed_order.store_id),
                    "table_id": str(closed_order.table_id),
                    "table_label": table.label if table is not None else None,
                    "order_id": str(closed_order.id),
                },
            )
    db.flush()
    return sale
