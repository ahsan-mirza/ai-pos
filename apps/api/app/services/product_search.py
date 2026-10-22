import uuid

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.serial_number import SerialNumber
from app.schemas.payloads import ProductSearchHit
from app.services.inventory import products_out
from app.services.search_terms import identifier_candidates, token_condition, tokens

__all__ = ["identifier_candidates", "search_products"]


def search_products(
    db: Session,
    query: str,
    *,
    limit: int,
    store_id: uuid.UUID | None = None,
) -> list[ProductSearchHit]:
    """Universal catalog search. Stock figures are for `store_id`, or consolidated when it is None."""
    words = tokens(query)
    if not words:
        return []
    found: list[tuple[Product, str, str | None, str | None]] = []
    seen: set[uuid.UUID] = set()

    candidates = identifier_candidates(query)
    if candidates:
        statement = (
            select(SerialNumber, Product)
            .join(Product, Product.id == SerialNumber.product_id)
            .where(SerialNumber.value_hash.in_(candidates.keys()))
        )
        for serial, product in db.execute(statement).unique().all():
            if product.id not in seen:
                seen.add(product.id)
                found.append((product, "identifier", serial.kind, serial.status))

    whole = query.strip().lower()
    exact = or_(func.lower(Product.barcode) == whole, func.lower(Product.sku) == whole)
    rank = case(
        (exact, 0),
        (func.lower(Product.name).startswith(words[0], autoescape=True), 1),
        else_=2,
    )
    statement = (
        select(Product, exact.label("is_exact"))
        .where(and_(*(token_condition(word) for word in words)))
        .order_by(rank, Product.name)
        .limit(limit)
    )
    for product, is_exact in db.execute(statement).unique().all():
        if product.id not in seen:
            seen.add(product.id)
            found.append((product, "exact" if is_exact else "text", None, None))

    found = found[:limit]
    rows = {row.id: row for row in products_out(db, [item[0] for item in found], store_id)}
    return [
        ProductSearchHit(
            product=rows[product.id],
            match=match,  # type: ignore[arg-type]
            serial_kind=kind,  # type: ignore[arg-type]
            serial_status=status,  # type: ignore[arg-type]
        )
        for product, match, kind, status in found
    ]
