"""Price lists, customer groups and scheduled price changes, and loading the entries the resolver needs.

Precedence and arithmetic live in services.pricing.resolve_with_lists (mirrored in shared-types). This module
only decides which entries are relevant: business-wide and store lists for a branch, plus the customer's own
and group lists (and the group's blanket discount) when a customer is on the sale."""

import csv
import io
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import Principal
from app.core.errors import ApiError
from app.models.customer import Customer
from app.models.price_list import (
    CustomerGroup,
    PriceList,
    PriceListItem,
    ScheduledPriceChange,
    ScheduledPriceChangeLine,
)
from app.models.product import Product
from app.models.product_price import ProductPrice
from app.models.store import Store
from app.models.user import User
from app.schemas.price_lists import (
    CsvImportIn,
    CsvImportResult,
    CustomerGroupIn,
    CustomerGroupOut,
    CustomerPricingOut,
    PriceChangeIn,
    PriceChangeLineOut,
    PriceChangeOut,
    PriceListEntryOut,
    PriceListIn,
    PriceListItemIn,
    PriceListItemOut,
    PriceListOut,
    PriceListRow,
    ProductEntriesOut,
)
from app.services import audit
from app.services.pricing import ListResolution, effective_tier, resolve_with_lists
from app.services.settings_service import cached_settings

# A register's catalogue carries at most this many store / business-wide entries per product.
ENTRIES_PER_PRODUCT = 20


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    return value if value is None or value.tzinfo is not None else value.replace(tzinfo=UTC)


# --- Entries for the resolver --------------------------------------------------------------------


def _entry(price_list: PriceList, item: PriceListItem) -> dict[str, Any]:
    return {
        "price_list_id": price_list.id,
        "scope": price_list.scope,
        "scope_id": price_list.scope_id,
        "valid_from": _aware(price_list.valid_from),
        "valid_to": _aware(price_list.valid_to),
        "priority": price_list.priority,
        "is_active": price_list.is_active,
        "price_cents": item.price_cents,
        "discount_bps": item.discount_bps,
        "min_qty": item.min_qty,
        "volume_breaks": list(item.volume_breaks or []),
    }


def _group_discount(group: CustomerGroup) -> dict[str, Any] | None:
    if not group.is_active or group.default_discount_bps <= 0:
        return None
    return {
        "price_list_id": None,
        "scope": "group",
        "scope_id": group.id,
        "valid_from": None,
        "valid_to": None,
        "priority": -1,
        "is_active": True,
        "price_cents": None,
        "discount_bps": group.default_discount_bps,
        "min_qty": 1,
        "volume_breaks": [],
    }


def entries_for(
    db: Session,
    product_ids: set[uuid.UUID],
    *,
    currency: str,
    store_id: uuid.UUID | None,
    customer: Customer | None = None,
    branch_only: bool = False,
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    """Active entries per product. branch_only: business-wide and store lists (what a catalogue carries)."""
    if not product_ids:
        return {}
    scopes = [PriceList.scope == "global"]
    if store_id is not None:
        scopes.append((PriceList.scope == "store") & (PriceList.scope_id == store_id))
    if customer is not None and not branch_only:
        scopes.append((PriceList.scope == "customer") & (PriceList.scope_id == customer.id))
        if customer.group_id is not None:
            scopes.append((PriceList.scope == "group") & (PriceList.scope_id == customer.group_id))
    rows = db.execute(
        select(PriceList, PriceListItem)
        .join(PriceListItem, PriceListItem.price_list_id == PriceList.id)
        .where(
            PriceListItem.product_id.in_(product_ids),
            PriceList.is_active.is_(True),
            PriceList.currency == currency,
            or_(*scopes),
        )
        .order_by(PriceList.priority.desc(), PriceList.created_at)
    ).all()
    found: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
    for price_list, item in rows:
        found[item.product_id].append(_entry(price_list, item))
    if customer is not None and not branch_only and customer.group_id is not None:
        group = db.get(CustomerGroup, customer.group_id)
        blanket = _group_discount(group) if group is not None else None
        if blanket is not None:
            for product_id in product_ids:
                found[product_id].append(blanket)
    return found


def tier_for(sale_type: str, customer: Customer | None, db: Session | None = None) -> str:
    """The customer's tier, or their group's default tier when they have none of their own."""
    tier = effective_tier(sale_type, customer.price_tier if customer is not None else None)
    if sale_type == "WHOLESALE" and customer is not None and tier == "RETAIL" and customer.group_id and db:
        group = db.get(CustomerGroup, customer.group_id)
        if group is not None and group.is_active and group.default_tier:
            return group.default_tier
    return tier


def resolve_for(
    product: Product,
    tier: str,
    pieces: int,
    entries: list[dict[str, Any]],
    *,
    customer: Customer | None,
    store_id: uuid.UUID | None,
    at: datetime | None = None,
) -> ListResolution:
    return resolve_with_lists(
        product.price_cents,
        product.prices,
        tier,
        pieces,
        entries,
        customer_id=customer.id if customer is not None else None,
        group_id=customer.group_id if customer is not None else None,
        store_id=store_id,
        at=at or _now(),
    )


def entry_out(entry: dict[str, Any]) -> PriceListEntryOut:
    return PriceListEntryOut(**entry)


def catalog_entries(
    db: Session, product_ids: set[uuid.UUID], currency: str, store_id: uuid.UUID | None
) -> dict[uuid.UUID, list[PriceListEntryOut]]:
    found = entries_for(db, product_ids, currency=currency, store_id=store_id, branch_only=True)
    return {key: [entry_out(entry) for entry in rows[:ENTRIES_PER_PRODUCT]] for key, rows in found.items()}


def customer_pricing(db: Session, customer_id: uuid.UUID) -> CustomerPricingOut:
    """The customer's own and group lists across the catalogue, for the register's offline cache."""
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise ApiError(404, "not_found", "Customer was not found.")
    currency = cached_settings(db).currency
    scopes = [(PriceList.scope == "customer") & (PriceList.scope_id == customer.id)]
    if customer.group_id is not None:
        scopes.append((PriceList.scope == "group") & (PriceList.scope_id == customer.group_id))
    rows = db.execute(
        select(PriceList, PriceListItem)
        .join(PriceListItem, PriceListItem.price_list_id == PriceList.id)
        .where(PriceList.is_active.is_(True), PriceList.currency == currency, or_(*scopes))
    ).all()
    entries = [ProductEntriesOut(product_id=item.product_id, **_entry(price_list, item)) for price_list, item in rows]
    if customer.group_id is not None:
        group = db.get(CustomerGroup, customer.group_id)
        blanket = _group_discount(group) if group is not None else None
        if blanket is not None:
            entries.append(ProductEntriesOut(product_id=None, **blanket))
    return CustomerPricingOut(
        customer_id=customer.id,
        group_id=customer.group_id,
        tier=tier_for("WHOLESALE", customer, db)  # type: ignore[arg-type]
        if customer.customer_type == "WHOLESALE"
        else "RETAIL",
        tax_treatment=customer.tax_treatment,  # type: ignore[arg-type]
        tax_certificate_expiry=customer.tax_certificate_expiry,
        entries=entries,
        fetched_at=_now(),
    )


# --- Customer groups -----------------------------------------------------------------------------


def _group_out(db: Session, group: CustomerGroup) -> CustomerGroupOut:
    members = db.scalar(select(func.count()).select_from(Customer).where(Customer.group_id == group.id)) or 0
    lists = (
        db.scalar(
            select(func.count())
            .select_from(PriceList)
            .where(PriceList.scope == "group", PriceList.scope_id == group.id)
        )
        or 0
    )
    return CustomerGroupOut(
        id=group.id,
        name=group.name,
        default_tier=group.default_tier,  # type: ignore[arg-type]
        default_discount_bps=group.default_discount_bps,
        payment_terms=group.payment_terms,  # type: ignore[arg-type]
        is_active=group.is_active,
        members=int(members),
        price_lists=int(lists),
    )


def list_groups(db: Session) -> list[CustomerGroupOut]:
    return [_group_out(db, group) for group in db.scalars(select(CustomerGroup).order_by(CustomerGroup.name))]


def save_group(
    db: Session, principal: Principal, data: CustomerGroupIn, group_id: uuid.UUID | None = None
) -> CustomerGroupOut:
    group = db.get(CustomerGroup, group_id) if group_id else CustomerGroup()
    if group is None:
        raise ApiError(404, "not_found", "Customer group was not found.")
    clash = db.scalar(select(CustomerGroup.id).where(func.lower(CustomerGroup.name) == data.name.strip().lower()))
    if clash is not None and clash != group.id:
        raise ApiError(409, "duplicate", "Another group already has that name.")
    group.name = data.name.strip()
    group.default_tier = data.default_tier
    group.default_discount_bps = data.default_discount_bps
    group.payment_terms = data.payment_terms
    group.is_active = data.is_active
    db.add(group)
    db.commit()
    return _group_out(db, group)


# --- Price lists ---------------------------------------------------------------------------------


def _scope_name(db: Session, price_list: PriceList) -> str | None:
    if price_list.scope_id is None:
        return None
    model = {"customer": Customer, "group": CustomerGroup, "store": Store}[price_list.scope]
    row = db.get(model, price_list.scope_id)
    if row is None:
        return None
    return getattr(row, "company_name", None) or row.name


def _status(price_list: PriceList) -> str:
    now = _now()
    if not price_list.is_active:
        return "off"
    start, end = _aware(price_list.valid_from), _aware(price_list.valid_to)
    if end is not None and end <= now:
        return "expired"
    if start is not None and start > now:
        return "scheduled"
    return "active"


def _row(db: Session, price_list: PriceList) -> PriceListRow:
    return PriceListRow(
        id=price_list.id,
        name=price_list.name,
        scope=price_list.scope,  # type: ignore[arg-type]
        scope_id=price_list.scope_id,
        currency=price_list.currency,
        valid_from=price_list.valid_from,
        valid_to=price_list.valid_to,
        priority=price_list.priority,
        is_active=price_list.is_active,
        scope_name=_scope_name(db, price_list),
        items=len(price_list.items),
        status=_status(price_list),  # type: ignore[arg-type]
    )


def _out(db: Session, price_list: PriceList) -> PriceListOut:
    products = {
        row.id: row
        for row in db.scalars(select(Product).where(Product.id.in_([item.product_id for item in price_list.items])))
    }
    lines = [
        PriceListItemOut(
            product_id=item.product_id,
            price_cents=item.price_cents,
            discount_bps=item.discount_bps,
            min_qty=item.min_qty,
            volume_breaks=item.volume_breaks or [],
            sku=products[item.product_id].sku if item.product_id in products else "",
            name=products[item.product_id].name if item.product_id in products else "Removed product",
            retail_price_cents=products[item.product_id].price_cents if item.product_id in products else 0,
        )
        for item in price_list.items
    ]
    lines.sort(key=lambda line: line.name.lower())
    return PriceListOut(**_row(db, price_list).model_dump(), lines=lines)


def list_price_lists(db: Session, scope: str | None = None, scope_id: uuid.UUID | None = None) -> list[PriceListRow]:
    statement = select(PriceList).order_by(PriceList.scope, PriceList.name)
    if scope:
        statement = statement.where(PriceList.scope == scope)
    if scope_id:
        statement = statement.where(PriceList.scope_id == scope_id)
    return [_row(db, row) for row in db.scalars(statement)]


def _list(db: Session, list_id: uuid.UUID) -> PriceList:
    price_list = db.get(PriceList, list_id)
    if price_list is None:
        raise ApiError(404, "not_found", "Price list was not found.")
    return price_list


def get_price_list(db: Session, list_id: uuid.UUID) -> PriceListOut:
    return _out(db, _list(db, list_id))


def _check_target(db: Session, data: PriceListIn) -> None:
    if data.scope_id is None:
        return
    model = {"customer": Customer, "group": CustomerGroup, "store": Store}[data.scope]
    if db.get(model, data.scope_id) is None:
        raise ApiError(422, "invalid_request", f"That {data.scope} does not exist.")


def save_price_list(
    db: Session, principal: Principal, data: PriceListIn, list_id: uuid.UUID | None = None
) -> PriceListOut:
    _check_target(db, data)
    price_list = _list(db, list_id) if list_id else PriceList(currency=cached_settings(db).currency)
    before = _row(db, price_list).model_dump(mode="json") if list_id else None
    price_list.name = data.name.strip()
    price_list.scope = data.scope
    price_list.scope_id = data.scope_id
    price_list.valid_from = data.valid_from
    price_list.valid_to = data.valid_to
    price_list.priority = data.priority
    price_list.is_active = data.is_active
    db.add(price_list)
    db.flush()
    audit.record(
        db,
        action_type="UPDATE" if list_id else "CREATE",
        action="price_list.save",
        target_entity="PriceList",
        target_entity_id=price_list.id,
        user_id=principal.user.id if principal.user else None,
        old_values=before,
        new_values={"name": price_list.name, "scope": price_list.scope, "active": price_list.is_active},
    )
    db.commit()
    return _out(db, price_list)


def _apply_items(db: Session, price_list: PriceList, items: list[PriceListItemIn], *, replace: bool) -> int:
    ids = {item.product_id for item in items}
    known = set(db.scalars(select(Product.id).where(Product.id.in_(ids)))) if ids else set()
    missing = ids - known
    if missing:
        raise ApiError(422, "invalid_request", f"{len(missing)} products on the list do not exist.")
    current = {item.product_id: item for item in price_list.items}
    if replace:
        for product_id, row in list(current.items()):
            if product_id not in ids:
                price_list.items.remove(row)
    for item in items:
        row = current.get(item.product_id)
        if row is None:
            row = PriceListItem(product_id=item.product_id)
            price_list.items.append(row)
        row.price_cents = item.price_cents
        row.discount_bps = item.discount_bps
        row.min_qty = item.min_qty
        row.volume_breaks = [entry.model_dump() for entry in item.volume_breaks] or None
    return len(items)


def put_items(db: Session, principal: Principal, list_id: uuid.UUID, items: list[PriceListItemIn]) -> PriceListOut:
    price_list = _list(db, list_id)
    count = _apply_items(db, price_list, items, replace=True)
    audit.record(
        db,
        action_type="UPDATE",
        action="price_list.items",
        target_entity="PriceList",
        target_entity_id=price_list.id,
        user_id=principal.user.id if principal.user else None,
        details={"items": count},
    )
    db.commit()
    return _out(db, price_list)


def delete_price_list(db: Session, principal: Principal, list_id: uuid.UUID) -> None:
    price_list = _list(db, list_id)
    audit.record(
        db,
        action_type="DELETE",
        action="price_list.delete",
        target_entity="PriceList",
        target_entity_id=price_list.id,
        user_id=principal.user.id if principal.user else None,
        old_values={"name": price_list.name, "items": len(price_list.items)},
    )
    db.delete(price_list)
    db.commit()


def _cents(value: str) -> int:
    return round(float(value.replace(",", "").strip()) * 100)


def import_csv(db: Session, principal: Principal, list_id: uuid.UUID, data: CsvImportIn) -> CsvImportResult:
    price_list = _list(db, list_id)
    reader = csv.DictReader(io.StringIO(data.csv.lstrip("\ufeff")))
    fields = {name.strip().lower() for name in (reader.fieldnames or [])}
    if "sku" not in fields or not ({"price", "discount_percent"} & fields):
        raise ApiError(422, "invalid_csv", "The CSV needs a header with sku and price or discount_percent.")
    rows = [{(key or "").strip().lower(): (value or "").strip() for key, value in row.items()} for row in reader]
    skus = {row.get("sku", "") for row in rows if row.get("sku")}
    by_sku = {product.sku: product for product in db.scalars(select(Product).where(Product.sku.in_(skus)))}
    items: list[PriceListItemIn] = []
    skipped: list[str] = []
    for number, row in enumerate(rows, start=2):
        product = by_sku.get(row.get("sku", ""))
        if product is None:
            skipped.append(f"Row {number}: unknown SKU {row.get('sku') or '(blank)'}")
            continue
        try:
            price = row.get("price") or ""
            discount = row.get("discount_percent") or ""
            items.append(
                PriceListItemIn(
                    product_id=product.id,
                    price_cents=_cents(price) if price else None,
                    discount_bps=round(float(discount) * 100) if discount and not price else None,
                    min_qty=int(row.get("min_qty") or 1),
                )
            )
        except (ValueError, TypeError) as exc:
            skipped.append(f"Row {number}: {str(exc).splitlines()[0][:120]}")
    _apply_items(db, price_list, items, replace=data.replace)
    audit.record(
        db,
        action_type="UPDATE",
        action="price_list.import",
        target_entity="PriceList",
        target_entity_id=price_list.id,
        user_id=principal.user.id if principal.user else None,
        details={"imported": len(items), "skipped": len(skipped)},
    )
    db.commit()
    return CsvImportResult(imported=len(items), skipped=skipped[:100])


def export_csv(db: Session, list_id: uuid.UUID) -> tuple[str, str]:
    out = _out(db, _list(db, list_id))
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["sku", "name", "price", "discount_percent", "min_qty", "retail_price"])
    for line in out.lines:
        writer.writerow(
            [
                line.sku,
                line.name,
                f"{line.price_cents / 100:.2f}" if line.price_cents is not None else "",
                f"{line.discount_bps / 100:g}" if line.discount_bps is not None else "",
                line.min_qty,
                f"{line.retail_price_cents / 100:.2f}",
            ]
        )
    return out.name, buffer.getvalue()


# --- Scheduled price changes ---------------------------------------------------------------------


def _tiers(product: Product) -> dict[str, int]:
    return {row.price_tier: row.price_cents for row in product.prices}


def _change_out(db: Session, change: ScheduledPriceChange) -> PriceChangeOut:
    ids = [line.product_id for line in change.lines]
    products = {row.id: row for row in db.scalars(select(Product).where(Product.id.in_(ids)))}
    creator = db.get(User, change.created_by_id) if change.created_by_id else None
    lines = []
    for line in change.lines:
        product = products.get(line.product_id)
        lines.append(
            PriceChangeLineOut(
                product_id=line.product_id,
                sku=product.sku if product else "",
                name=product.name if product else "Removed product",
                current_retail_cents=product.price_cents if product else 0,
                retail_price_cents=line.retail_price_cents,
                current_tier_prices=_tiers(product) if product else {},
                tier_prices=dict(line.tier_prices or {}),
                previous_retail_cents=line.previous_retail_cents,
                previous_tier_prices=line.previous_tier_prices,
            )
        )
    lines.sort(key=lambda row: row.name.lower())
    return PriceChangeOut(
        id=change.id,
        name=change.name,
        run_at=change.run_at,
        status=change.status,  # type: ignore[arg-type]
        note=change.note,
        created_by_name=creator.full_name if creator else None,
        applied_at=change.applied_at,
        lines=lines,
    )


def list_changes(db: Session) -> list[PriceChangeOut]:
    rows = db.scalars(select(ScheduledPriceChange).order_by(ScheduledPriceChange.run_at.desc()).limit(200))
    return [_change_out(db, row) for row in rows]


def _change(db: Session, change_id: uuid.UUID) -> ScheduledPriceChange:
    change = db.get(ScheduledPriceChange, change_id)
    if change is None:
        raise ApiError(404, "not_found", "Price change was not found.")
    return change


def get_change(db: Session, change_id: uuid.UUID) -> PriceChangeOut:
    return _change_out(db, _change(db, change_id))


def create_change(db: Session, principal: Principal, data: PriceChangeIn) -> PriceChangeOut:
    ids = {line.product_id for line in data.lines}
    if len(ids) != len(data.lines):
        raise ApiError(422, "invalid_request", "Each product can appear once per price change.")
    known = set(db.scalars(select(Product.id).where(Product.id.in_(ids))))
    if known != ids:
        raise ApiError(422, "invalid_request", "Some products on the change do not exist.")
    change = ScheduledPriceChange(
        name=data.name.strip(),
        run_at=_aware(data.run_at),
        note=data.note.strip(),
        status="SCHEDULED",
        created_by_id=principal.user.id if principal.user else None,
        lines=[
            ScheduledPriceChangeLine(
                product_id=line.product_id,
                retail_price_cents=line.retail_price_cents,
                tier_prices=dict(line.tier_prices) or None,
            )
            for line in data.lines
        ],
    )
    db.add(change)
    db.commit()
    return _change_out(db, change)


def cancel_change(db: Session, principal: Principal, change_id: uuid.UUID) -> PriceChangeOut:
    change = _change(db, change_id)
    if change.status != "SCHEDULED":
        raise ApiError(409, "not_scheduled", f"This change is already {change.status.lower()}.")
    change.status = "CANCELLED"
    db.commit()
    return _change_out(db, change)


def _apply(db: Session, change: ScheduledPriceChange, user_id: uuid.UUID | None) -> None:
    for line in change.lines:
        product = db.get(Product, line.product_id)
        if product is None:
            continue
        line.previous_retail_cents = product.price_cents
        line.previous_tier_prices = _tiers(product) or None
        if line.retail_price_cents is not None:
            product.price_cents = line.retail_price_cents
        for tier, price in (line.tier_prices or {}).items():
            row = next((item for item in product.prices if item.price_tier == tier), None)
            if row is None:
                product.prices.append(
                    ProductPrice(price_tier=tier, price_cents=price, min_order_quantity=1, volume_discounts=[])
                )
            else:
                row.price_cents = price
    change.status = "APPLIED"
    change.applied_at = _now()
    audit.record(
        db,
        action_type="UPDATE",
        action="price_change.apply",
        target_entity="ScheduledPriceChange",
        target_entity_id=change.id,
        user_id=user_id,
        details={"name": change.name, "products": len(change.lines)},
    )


def apply_now(db: Session, principal: Principal, change_id: uuid.UUID) -> PriceChangeOut:
    change = _change(db, change_id)
    if change.status != "SCHEDULED":
        raise ApiError(409, "not_scheduled", f"This change is already {change.status.lower()}.")
    _apply(db, change, principal.user.id if principal.user else None)
    db.commit()
    return _change_out(db, change)


def apply_due(db: Session) -> str:
    due = db.scalars(
        select(ScheduledPriceChange)
        .where(ScheduledPriceChange.status == "SCHEDULED", ScheduledPriceChange.run_at <= _now())
        .order_by(ScheduledPriceChange.run_at)
    ).all()
    for change in due:
        _apply(db, change, change.created_by_id)
    db.commit()
    return f"{len(due)} price changes applied"


def label_items(db: Session, change_id: uuid.UUID) -> list[tuple[uuid.UUID, int]]:
    """One shelf label per changed product, for the labels PDF."""
    change = _change(db, change_id)
    return [(line.product_id, 1) for line in change.lines]
