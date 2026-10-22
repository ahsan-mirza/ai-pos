"""Margin floors: the lowest unit price that still clears the minimum margin over the next unit's cost."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.category import Category
from app.models.margin import MarginPolicy
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.store import Store
from app.models.user import User
from app.schemas.margin import FloorOut, MarginExceptionOut, MarginPolicyOut, MarginPolicyWrite
from app.services import costing
from app.services.tax import TaxPolicy, div_half_up


@dataclass(frozen=True)
class Floor:
    floor_cents: int
    cost_cents: int
    cost_estimated: bool
    min_margin_bps: int


def active_policies(db: Session) -> tuple[int | None, dict[uuid.UUID, int], dict[uuid.UUID, int]]:
    global_bps: int | None = None
    by_category: dict[uuid.UUID, int] = {}
    by_product: dict[uuid.UUID, int] = {}
    for row in db.scalars(select(MarginPolicy).where(MarginPolicy.is_active.is_(True))):
        if row.scope == "PRODUCT" and row.product_id is not None:
            by_product[row.product_id] = row.min_margin_bps
        elif row.scope == "CATEGORY" and row.category_id is not None:
            by_category[row.category_id] = row.min_margin_bps
        elif row.scope == "GLOBAL":
            global_bps = row.min_margin_bps
    return global_bps, by_category, by_product


def _price_terms(net_floor: int, product: Product, tax: TaxPolicy) -> int:
    """Floors are compared with unit prices, which include VAT when the business prices VAT-inclusive."""
    if not tax.prices_include_vat:
        return net_floor
    rate = tax.rate_for(product.tax_category)
    return net_floor + div_half_up(net_floor * rate, 10_000)


def floor_for(db: Session, product: Product, store_id: uuid.UUID, tax: TaxPolicy, policies=None) -> Floor | None:
    if product.is_open_price:
        return None
    global_bps, by_category, by_product = policies or active_policies(db)
    bps = by_product.get(product.id)
    if bps is None and product.category_id is not None:
        bps = by_category.get(product.category_id)
    if bps is None:
        bps = global_bps
    if bps is None:
        return None
    cost, estimated = costing.next_unit_cost(db, product.id, store_id)
    if cost is None or cost <= 0:
        return None
    net_floor = cost + div_half_up(cost * bps, 10_000)
    return Floor(_price_terms(net_floor, product, tax), cost, estimated, bps)


def floors(db: Session, store_id: uuid.UUID, tax: TaxPolicy) -> list[FloorOut]:
    policies = active_policies(db)
    if policies == (None, {}, {}):
        return []
    out = []
    for product in db.scalars(select(Product).where(Product.is_open_price.is_(False))):
        found = floor_for(db, product, store_id, tax, policies)
        if found is not None:
            out.append(
                FloorOut(
                    product_id=product.id,
                    floor_cents=found.floor_cents,
                    cost_cents=found.cost_cents,
                    cost_estimated=found.cost_estimated,
                    min_margin_bps=found.min_margin_bps,
                )
            )
    return out


def list_policies(db: Session) -> list[MarginPolicyOut]:
    rows = list(db.scalars(select(MarginPolicy).order_by(MarginPolicy.scope, MarginPolicy.created_at)))
    categories = {row.id: row.name for row in db.scalars(select(Category))}
    product_ids = {row.product_id for row in rows if row.product_id}
    products = (
        {row.id: row.name for row in db.scalars(select(Product).where(Product.id.in_(product_ids)))}
        if product_ids
        else {}
    )
    return [
        MarginPolicyOut(
            id=row.id,
            scope=row.scope,  # type: ignore[arg-type]
            category_id=row.category_id,
            category_name=categories.get(row.category_id) if row.category_id else None,
            product_id=row.product_id,
            product_name=products.get(row.product_id) if row.product_id else None,
            min_margin_bps=row.min_margin_bps,
            is_active=row.is_active,
        )
        for row in rows
    ]


def upsert_policy(db: Session, data: MarginPolicyWrite) -> list[MarginPolicyOut]:
    if data.scope == "CATEGORY" and (data.category_id is None or db.get(Category, data.category_id) is None):
        raise ApiError(422, "validation_error", "Choose a category.")
    if data.scope == "PRODUCT" and (data.product_id is None or db.get(Product, data.product_id) is None):
        raise ApiError(422, "validation_error", "Choose a product.")
    category_id = data.category_id if data.scope == "CATEGORY" else None
    product_id = data.product_id if data.scope == "PRODUCT" else None
    row = db.scalar(
        select(MarginPolicy).where(
            MarginPolicy.scope == data.scope,
            MarginPolicy.category_id.is_(None) if category_id is None else MarginPolicy.category_id == category_id,
            MarginPolicy.product_id.is_(None) if product_id is None else MarginPolicy.product_id == product_id,
        )
    )
    if row is None:
        row = MarginPolicy(scope=data.scope, category_id=category_id, product_id=product_id)
        db.add(row)
    row.min_margin_bps = data.min_margin_bps
    row.is_active = data.is_active
    db.commit()
    return list_policies(db)


def delete_policy(db: Session, policy_id: uuid.UUID) -> list[MarginPolicyOut]:
    row = db.get(MarginPolicy, policy_id)
    if row is None:
        raise ApiError(404, "not_found", "Policy was not found.")
    db.delete(row)
    db.commit()
    return list_policies(db)


def exceptions(db: Session, *, store_scope: uuid.UUID | None, days: int, limit: int) -> list[MarginExceptionOut]:
    since = datetime.now(UTC) - timedelta(days=days)
    query = (
        select(SaleItem, Sale, Product)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .join(Product, Product.id == SaleItem.product_id)
        .where(SaleItem.floor_cents.is_not(None), Sale.created_at >= since, Sale.is_quote_proforma.is_(False))
        .order_by(Sale.created_at.desc())
        .limit(limit)
    )
    if store_scope is not None:
        query = query.where(Sale.store_id == store_scope)
    rows = db.execute(query).all()
    people = {item.below_floor_approved_by_id for item, _, _ in rows} | {sale.cashier_id for _, sale, _ in rows}
    people.discard(None)
    names = (
        {row.id: row.full_name for row in db.scalars(select(User).where(User.id.in_(people))).unique()}
        if people
        else {}
    )
    stores = {row.id: row.code for row in db.scalars(select(Store))}
    return [
        MarginExceptionOut(
            sale_id=sale.id,
            invoice=sale.invoice_number or sale.client_sale_id[:8].upper(),
            store_code=stores.get(sale.store_id, ""),
            sold_at=sale.created_at if sale.created_at.tzinfo else sale.created_at.replace(tzinfo=UTC),
            product_name=product.name,
            quantity=item.quantity,
            unit_price_cents=item.unit_price_cents,
            floor_cents=int(item.floor_cents or 0),
            shortfall_cents=(int(item.floor_cents or 0) - item.unit_price_cents) * item.quantity,
            cashier_name=names.get(sale.cashier_id),
            approved_by_name=names.get(item.below_floor_approved_by_id) if item.below_floor_approved_by_id else None,
            currency=sale.currency,
        )
        for item, sale, product in rows
    ]


def exception_total(db: Session, store_scope: uuid.UUID | None, days: int) -> int:
    since = datetime.now(UTC) - timedelta(days=days)
    query = (
        select(func.coalesce(func.sum((SaleItem.floor_cents - SaleItem.unit_price_cents) * SaleItem.quantity), 0))
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(SaleItem.floor_cents.is_not(None), Sale.created_at >= since)
    )
    if store_scope is not None:
        query = query.where(Sale.store_id == store_scope)
    return int(db.scalar(query) or 0)
