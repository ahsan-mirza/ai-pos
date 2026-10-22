"""Apply and restore markdown events. A product already on a markdown is left alone, and a new price below the
margin floor is skipped and reported."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.inventory import InventoryLevel
from app.models.markdown import MarkdownEvent, PriceChange
from app.models.product import Product
from app.models.store import Store
from app.schemas.markdowns import MarkdownCreate, MarkdownEventOut, MarkdownPreview, MarkdownScope, MarkdownSkip
from app.services import margin_service
from app.services.tax import policy as tax_policy


def marked_price(old: int, percent_bps: int | None, price_cents: int | None) -> int:
    if price_cents is not None:
        return price_cents
    assert percent_bps is not None
    return max(0, old - (old * percent_bps + 5_000) // 10_000)


def record(
    db: Session,
    product: Product,
    new_price: int,
    reason: str,
    *,
    event_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    if new_price == product.price_cents:
        return
    db.add(
        PriceChange(
            product_id=product.id,
            old_price_cents=product.price_cents,
            new_price_cents=new_price,
            reason=reason,
            markdown_event_id=event_id,
            user_id=user_id,
        )
    )


def _scope(raw: dict) -> MarkdownScope:
    return MarkdownScope.model_validate(raw)


def _out(event: MarkdownEvent) -> MarkdownEventOut:
    return MarkdownEventOut(
        id=event.id,
        name=event.name,
        scope=_scope(event.scope),
        percent_bps=event.percent_bps,
        price_cents=event.price_cents,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        final_sale=event.final_sale,
        status=event.status,
        applied_count=event.applied_count,
        skipped_count=event.skipped_count,
        created_at=event.created_at,
    )


def _products(db: Session, scope: MarkdownScope) -> list[Product]:
    statement = select(Product).where(Product.is_service.is_(False), Product.is_open_price.is_(False))
    if scope.product_ids:
        statement = statement.where(Product.id.in_(scope.product_ids))
    else:
        if scope.model_ids:
            statement = statement.where(Product.product_model_id.in_(scope.model_ids))
        if scope.category_ids:
            statement = statement.where(Product.category_id.in_(scope.category_ids))
        if scope.season:
            statement = statement.where(Product.season == scope.season.strip().upper())
        if scope.collection:
            statement = statement.where(Product.collection == scope.collection.strip())
    return list(db.scalars(statement))


def _on_hand(db: Session) -> dict[uuid.UUID, int]:
    rows = db.execute(
        select(InventoryLevel.product_id, func.coalesce(func.sum(InventoryLevel.quantity_on_hand), 0)).group_by(
            InventoryLevel.product_id
        )
    ).all()
    return {product_id: int(quantity) for product_id, quantity in rows}


def _floor_store(db: Session) -> Store | None:
    return db.scalar(select(Store).where(Store.is_active.is_(True)).order_by(Store.is_warehouse, Store.code))


def preview(db: Session, data: MarkdownCreate) -> MarkdownPreview:
    products = _products(db, data.scope)
    stock = _on_hand(db)
    store = _floor_store(db)
    tax = tax_policy(db)
    policies = margin_service.active_policies(db) if store is not None else None
    units = retail = marked = 0
    skipped: list[MarkdownSkip] = []
    counted = 0
    for product in products:
        new_price = marked_price(product.price_cents, data.percent_bps, data.price_cents)
        if product.markdown_event_id is not None:
            skipped.append(MarkdownSkip(sku=product.sku, reason="Already on a markdown"))
            continue
        if store is not None and policies is not None:
            floor = margin_service.floor_for(db, product, store.id, tax, policies)
            if floor is not None and new_price < floor.floor_cents:
                skipped.append(MarkdownSkip(sku=product.sku, reason="Below the margin floor"))
                continue
        quantity = stock.get(product.id, 0)
        units += quantity
        retail += product.price_cents * quantity
        marked += new_price * quantity
        counted += 1
    return MarkdownPreview(products=counted, units=units, retail_cents=retail, marked_cents=marked, skipped=skipped)


def _start(db: Session, event: MarkdownEvent, user_id: uuid.UUID | None) -> None:
    scope = _scope(event.scope)
    products = _products(db, scope)
    store = _floor_store(db)
    tax = tax_policy(db)
    policies = margin_service.active_policies(db) if store is not None else None
    applied = skipped = 0
    for product in products:
        new_price = marked_price(product.price_cents, event.percent_bps, event.price_cents)
        if product.markdown_event_id is not None or new_price == product.price_cents:
            skipped += 1
            continue
        if store is not None and policies is not None:
            floor = margin_service.floor_for(db, product, store.id, tax, policies)
            if floor is not None and new_price < floor.floor_cents:
                skipped += 1
                continue
        record(db, product, new_price, "MARKDOWN", event_id=event.id, user_id=user_id)
        product.compare_at_cents = product.price_cents
        product.price_cents = new_price
        product.markdown_event_id = event.id
        if event.final_sale:
            product.is_final_sale = True
        applied += 1
    event.applied_count = applied
    event.skipped_count = skipped
    event.status = "ACTIVE"


def _restore(db: Session, event: MarkdownEvent) -> None:
    products = list(db.scalars(select(Product).where(Product.markdown_event_id == event.id)))
    for product in products:
        was = product.compare_at_cents if product.compare_at_cents is not None else product.price_cents
        record(db, product, was, "MARKDOWN", event_id=event.id)
        product.price_cents = was
        product.compare_at_cents = None
        product.markdown_event_id = None
        if event.final_sale:
            product.is_final_sale = False


def apply_due(db: Session, now: datetime | None = None) -> str:
    moment = now or datetime.now(UTC)
    started = ended = 0
    due = list(
        db.scalars(select(MarkdownEvent).where(MarkdownEvent.status == "SCHEDULED", MarkdownEvent.starts_at <= moment))
    )
    for event in due:
        if event.ends_at <= moment:
            event.status = "CANCELLED"
            continue
        _start(db, event, event.created_by_id)
        started += 1
    finishing = list(
        db.scalars(select(MarkdownEvent).where(MarkdownEvent.status == "ACTIVE", MarkdownEvent.ends_at <= moment))
    )
    for event in finishing:
        _restore(db, event)
        event.status = "ENDED"
        ended += 1
    db.commit()
    return f"{started} markdowns started, {ended} restored"


def create(db: Session, data: MarkdownCreate, user_id: uuid.UUID | None) -> MarkdownEventOut:
    event = MarkdownEvent(
        name=data.name.strip(),
        scope=data.scope.model_dump(mode="json"),
        percent_bps=data.percent_bps,
        price_cents=data.price_cents,
        starts_at=data.starts_at,
        ends_at=data.ends_at,
        final_sale=data.final_sale,
        created_by_id=user_id,
    )
    db.add(event)
    db.flush()
    apply_due(db)
    db.refresh(event)
    return _out(event)


def list_events(db: Session) -> list[MarkdownEventOut]:
    rows = db.scalars(select(MarkdownEvent).order_by(MarkdownEvent.starts_at.desc())).all()
    return [_out(row) for row in rows]


def end_event(db: Session, event_id: uuid.UUID) -> MarkdownEventOut:
    event = db.get(MarkdownEvent, event_id)
    if event is None:
        raise ApiError(404, "not_found", "Markdown was not found.")
    if event.status == "SCHEDULED":
        event.status = "CANCELLED"
    elif event.status == "ACTIVE":
        _restore(db, event)
        event.status = "ENDED"
    else:
        raise ApiError(409, "conflict", "This markdown has already ended.")
    db.commit()
    return _out(event)


def changed_product_ids(db: Session, event_id: uuid.UUID) -> list[uuid.UUID]:
    event = db.get(MarkdownEvent, event_id)
    if event is None:
        raise ApiError(404, "not_found", "Markdown was not found.")
    return list(db.scalars(select(Product.id).where(Product.markdown_event_id == event_id)))
