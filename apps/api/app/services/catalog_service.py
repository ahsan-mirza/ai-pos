import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.security import decrypt_value
from app.models.customer import Customer
from app.models.product import Product
from app.models.repair_ticket import RepairTicket
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.store import Store
from app.schemas.payloads import ProductOut, RepairOut, SaleItemOut, SaleOut, SaleTenderOut, StoreOut
from app.services import fashion_attributes
from app.services.inventory import products_out


def _visible(row_store_id: uuid.UUID, scope: uuid.UUID | None) -> bool:
    return scope is None or row_store_id == scope


def list_stores(db: Session, *, limit: int, store_scope: uuid.UUID | None = None) -> list[StoreOut]:
    statement = select(Store).order_by(Store.name).limit(limit)
    if store_scope is not None:
        statement = statement.where(Store.id == store_scope)
    return [StoreOut.model_validate(row) for row in db.scalars(statement).all()]


def list_products(
    db: Session,
    *,
    limit: int,
    store_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    sub_category_id: uuid.UUID | None = None,
    brand_id: uuid.UUID | None = None,
    product_model_id: uuid.UUID | None = None,
    season: str | None = None,
    collection: str | None = None,
    gender: str | None = None,
    after: uuid.UUID | None = None,
) -> list[ProductOut]:
    """Global catalog with stock at `store_id`, or consolidated across active branches when it is None. Pages in
    (name, id) order: pass the last product's id as `after` for the next page, until a page comes back short."""
    statement = select(Product).order_by(Product.name, Product.id).limit(limit)
    if after is not None:
        cursor = db.get(Product, after)
        if cursor is None:
            raise ApiError(422, "bad_cursor", "The product to page after was not found; restart from the first page.")
        statement = statement.where(
            or_(Product.name > cursor.name, and_(Product.name == cursor.name, Product.id > cursor.id))
        )
    if category_id is not None:
        statement = statement.where(Product.category_id == category_id)
    if sub_category_id is not None:
        statement = statement.where(Product.sub_category_id == sub_category_id)
    if brand_id is not None:
        statement = statement.where(Product.brand_id == brand_id)
    if product_model_id is not None:
        statement = statement.where(Product.product_model_id == product_model_id)
    statement = fashion_attributes.filter_products(statement, season=season, collection=collection, gender=gender)
    return products_out(db, list(db.scalars(statement).unique().all()), store_id)


def get_product(db: Session, product_id: uuid.UUID, *, store_id: uuid.UUID | None = None) -> ProductOut:
    row = db.get(Product, product_id)
    if row is None:
        raise ApiError(404, "not_found", "Product was not found.")
    return products_out(db, [row], store_id)[0]


def sale_out(sale: Sale, settings: Settings, customer_name: str | None = None) -> SaleOut:
    items: list[SaleItemOut] = []
    for item in sale.items:
        serial_value = None
        if item.serial_number is not None:
            serial_value = decrypt_value(item.serial_number.value_encrypted, settings)
        items.append(
            SaleItemOut(
                id=item.id,
                sale_id=item.sale_id,
                product_id=item.product_id,
                serial_number_id=item.serial_number_id,
                serial_value=serial_value,
                quantity=item.quantity,
                unit_price_cents=item.unit_price_cents,
                tax_cents=item.tax_cents,
                line_total_cents=item.line_total_cents,
                unit_type=item.unit_type,  # type: ignore[arg-type]
                list_price_cents=item.list_price_cents,
                price_override_by_id=item.price_override_by_id,
                tax_rate_bps=item.tax_rate_bps,
                description=item.description,
                cost_cents=item.cost_cents,
            )
        )
    return SaleOut(
        id=sale.id,
        store_id=sale.store_id,
        cashier_id=sale.cashier_id,
        sales_associate_id=sale.sales_associate_id,
        status=sale.status,  # type: ignore[arg-type]
        currency=sale.currency,
        payment_method=sale.payment_method,  # type: ignore[arg-type]
        subtotal_cents=sale.subtotal_cents,
        tax_cents=sale.tax_cents,
        total_cents=sale.total_cents,
        client_sale_id=sale.client_sale_id,
        invoice_number=sale.invoice_number,
        items=items,
        sale_type=sale.sale_type,  # type: ignore[arg-type]
        customer_id=sale.customer_id,
        customer_name=customer_name,
        is_quote_proforma=sale.is_quote_proforma,
        quote_expiry_date=sale.quote_expiry_date,
        quote_status=sale.quote_status,  # type: ignore[arg-type]
        converted_sale_id=sale.converted_sale_id,
        payment_status=sale.payment_status,  # type: ignore[arg-type]
        amount_paid_cents=sale.amount_paid_cents,
        due_balance_cents=sale.due_balance_cents,
        due_date=sale.due_date,
        tenders=[
            SaleTenderOut(
                method=tender.method,  # type: ignore[arg-type]
                amount_cents=tender.amount_cents,
                reference=tender.reference,
                currency=getattr(tender, "currency", None),
                foreign_amount_cents=getattr(tender, "foreign_amount_cents", None),
            )
            for tender in sale.tenders
        ],
        created_at=sale.created_at,
        updated_at=sale.updated_at,
    )


def _customer_names(db: Session, sales: list[Sale]) -> dict[uuid.UUID, str]:
    ids = {sale.customer_id for sale in sales if sale.customer_id is not None}
    if not ids:
        return {}
    rows = db.scalars(select(Customer).where(Customer.id.in_(ids))).all()
    return {row.id: row.company_name or row.name for row in rows}


def list_sales(
    db: Session,
    settings: Settings,
    *,
    limit: int,
    store_scope: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
) -> list[SaleOut]:
    statement = (
        select(Sale)
        .options(selectinload(Sale.items).selectinload(SaleItem.serial_number))
        .where(Sale.is_quote_proforma.is_(False))
        .order_by(Sale.created_at.desc())
        .limit(limit)
    )
    if store_scope is not None:
        statement = statement.where(Sale.store_id == store_scope)
    if customer_id is not None:
        statement = statement.where(Sale.customer_id == customer_id)
    sales = list(db.scalars(statement).unique().all())
    names = _customer_names(db, sales)
    return [sale_out(sale, settings, names.get(sale.customer_id) if sale.customer_id else None) for sale in sales]


def get_sale(
    db: Session,
    settings: Settings,
    sale_id: uuid.UUID,
    *,
    store_scope: uuid.UUID | None = None,
) -> SaleOut:
    statement = (
        select(Sale).options(selectinload(Sale.items).selectinload(SaleItem.serial_number)).where(Sale.id == sale_id)
    )
    sale = db.scalars(statement).unique().one_or_none()
    if sale is None or not _visible(sale.store_id, store_scope):
        raise ApiError(404, "not_found", "Sale was not found.")
    names = _customer_names(db, [sale])
    return sale_out(sale, settings, names.get(sale.customer_id) if sale.customer_id else None)


def _repair_out(ticket: RepairTicket, settings: Settings) -> RepairOut:
    return RepairOut(
        id=ticket.id,
        store_id=ticket.store_id,
        customer_name=ticket.customer_name,
        customer_phone=ticket.customer_phone,
        device_model=ticket.device_model,
        identifier_kind=ticket.identifier_kind,  # type: ignore[arg-type]
        identifier_value=decrypt_value(ticket.identifier_encrypted, settings),
        issue=ticket.issue,
        status=ticket.status,  # type: ignore[arg-type]
        estimated_cost_cents=ticket.estimated_cost_cents,
        currency=ticket.currency,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        ownership=ticket.ownership if ticket.ownership in ("customer", "internal") else "customer",  # type: ignore[arg-type]
        product_id=ticket.product_id,
        reference=str(ticket.id)[:8].upper(),
        promised_at=ticket.promised_at,
        warranty_status=ticket.warranty_status,
    )


def list_repairs(
    db: Session,
    settings: Settings,
    *,
    limit: int,
    store_scope: uuid.UUID | None = None,
) -> list[RepairOut]:
    statement = select(RepairTicket).order_by(RepairTicket.created_at.desc()).limit(limit)
    if store_scope is not None:
        statement = statement.where(RepairTicket.store_id == store_scope)
    return [_repair_out(row, settings) for row in db.scalars(statement).all()]


def get_repair(
    db: Session,
    settings: Settings,
    repair_id: uuid.UUID,
    *,
    store_scope: uuid.UUID | None = None,
) -> RepairOut:
    row = db.get(RepairTicket, repair_id)
    if row is None or not _visible(row.store_id, store_scope):
        raise ApiError(404, "not_found", "Repair ticket was not found.")
    return _repair_out(row, settings)
