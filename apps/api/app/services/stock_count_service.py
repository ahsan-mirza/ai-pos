"""Stock count sessions: blind counting at a branch, review of the variances, then posting them to the ledger."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import Principal
from app.core.errors import ApiError, SyncRejected
from app.core.permissions import Permission
from app.core.security import decrypt_value
from app.models.brand import ProductModel
from app.models.category import Category
from app.models.inventory import InventoryLevel
from app.models.product import Product
from app.models.serial_number import SerialNumber
from app.models.stock_count import StockCount, StockCountLine
from app.models.store import Store
from app.models.user import User
from app.schemas.stock_counts import (
    StockCountCreate,
    StockCountEntries,
    StockCountLineOut,
    StockCountOut,
    StockCountSummary,
)
from app.services import audit, costing
from app.services.identifiers import identifier_hash, normalize_identifier
from app.services.inventory import level_for, move_stock, portal_errors, transition_serial
from app.services.numbering import next_server_number

REFERENCE = "stock_count"
REASON = "PHYSICAL_COUNT_AUDIT"
ACTIVE = ("OPEN", "SUBMITTED")


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _tail(value: str) -> str:
    return f"…{value[-4:]}"


def _can_review(principal: Principal) -> bool:
    return Permission.INVENTORY_ADJUST_STOCK.value in principal.permissions


def _require_store(principal: Principal, store_id: uuid.UUID) -> None:
    if principal.store_id is not None and principal.store_id != store_id:
        raise ApiError(403, "store_scope", "You can only count your own store's stock.")


def _user(principal: Principal) -> User:
    if principal.user is None:
        raise ApiError(403, "forbidden", "Counting stock requires a signed-in user.")
    return principal.user


def _get(db: Session, principal: Principal, count_id: uuid.UUID) -> StockCount:
    count = db.get(StockCount, count_id)
    if count is None:
        raise ApiError(404, "not_found", "Stock count was not found.")
    _require_store(principal, count.store_id)
    return count


def _in_stock_serials(db: Session, product_id: uuid.UUID, store_id: uuid.UUID) -> list[SerialNumber]:
    return list(
        db.scalars(
            select(SerialNumber).where(
                SerialNumber.product_id == product_id,
                SerialNumber.store_id == store_id,
                SerialNumber.status == "in_stock",
            )
        ).all()
    )


def _serial_gaps(
    db: Session, settings: Settings, line: StockCountLine, store_id: uuid.UUID
) -> tuple[list[SerialNumber], list[str]]:
    """Units the system holds here that were not scanned, and tails of scanned units it does not hold here."""
    held = _in_stock_serials(db, line.product_id, store_id)
    scanned = {entry["hash"]: entry["tail"] for entry in line.scanned_serials or []}
    missing = [serial for serial in held if serial.value_hash not in scanned]
    held_hashes = {serial.value_hash for serial in held}
    unexpected = [tail for hash_, tail in scanned.items() if hash_ not in held_hashes]
    return missing, unexpected


def _line_out(
    db: Session,
    settings: Settings,
    count: StockCount,
    line: StockCountLine,
    product: Product,
    names: dict[uuid.UUID, str],
    visible: bool,
) -> StockCountLineOut:
    counted = line.counted_qty is not None
    variance = line.counted_qty - line.expected_qty if counted and line.expected_qty is not None else None
    unit_cost = costing.next_unit_cost(db, product.id, count.store_id)[0] if variance else None
    missing: list[str] | None = None
    unexpected: list[str] | None = None
    if product.is_serialized and counted and visible:
        if line.serial_result is not None:
            missing, unexpected = line.serial_result.get("missing", []), line.serial_result.get("unexpected", [])
        elif count.status in ACTIVE:
            gone, extra = _serial_gaps(db, settings, line, count.store_id)
            missing = [_tail(decrypt_value(serial.value_encrypted, settings)) for serial in gone]
            unexpected = extra
    return StockCountLineOut(
        product_id=product.id,
        sku=product.sku,
        name=product.name,
        barcode=product.barcode,
        is_serialized=product.is_serialized,
        counted_qty=line.counted_qty,
        expected_qty=line.expected_qty if visible else None,
        variance=variance if visible else None,
        variance_value_cents=variance * unit_cost if visible and variance and unit_cost is not None else None,
        scanned_tails=[entry["tail"] for entry in line.scanned_serials or []],
        missing_serials=missing,
        unexpected_serials=unexpected,
        counted_by_name=names.get(line.counted_by_id) if line.counted_by_id else None,
        counted_at=_aware(line.counted_at),
    )


def _names(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {item for item in ids if item is not None}
    if not wanted:
        return {}
    return {user.id: user.full_name for user in db.scalars(select(User).where(User.id.in_(wanted))).unique().all()}


def _visible(principal: Principal, count: StockCount) -> bool:
    return _can_review(principal) or not count.blind or count.status not in ACTIVE


def _out(db: Session, settings: Settings, principal: Principal, count: StockCount) -> StockCountOut:
    visible = _visible(principal, count)
    products = {
        product.id: product
        for product in db.scalars(select(Product).where(Product.id.in_([line.product_id for line in count.lines])))
        .unique()
        .all()
    }
    names = _names(db, {count.created_by_id, *(line.counted_by_id for line in count.lines)})
    lines = [
        _line_out(db, settings, count, line, products[line.product_id], names, visible)
        for line in count.lines
        if line.product_id in products
    ]
    lines.sort(key=lambda line: (line.counted_qty is not None, line.name.lower()))
    store = db.get(Store, count.store_id)
    category = db.get(Category, count.category_id) if count.category_id else None
    variances = [line.variance for line in lines if line.variance is not None]
    values = [line.variance_value_cents for line in lines if line.variance_value_cents is not None]
    return StockCountOut(
        id=count.id,
        number=count.number,
        store_id=count.store_id,
        store_name=store.name if store else "",
        category_id=count.category_id,
        category_name=category.name if category else None,
        product_model_id=count.product_model_id,
        status=count.status,  # type: ignore[arg-type]
        blind=count.blind,
        note=count.note,
        can_review=_can_review(principal),
        created_by_name=names.get(count.created_by_id) if count.created_by_id else None,
        created_at=_aware(count.created_at),  # type: ignore[arg-type]
        submitted_at=_aware(count.submitted_at),
        closed_at=_aware(count.closed_at),
        lines_total=len(lines),
        lines_counted=sum(1 for line in lines if line.counted_qty is not None),
        net_variance=sum(variances) if visible else None,
        # Unknown (None) when variances exist but none of those products has a purchase cost yet.
        variance_value_cents=sum(values) if visible and (values or not any(variances)) else None,
        lines=lines,
    )


def get_count(db: Session, settings: Settings, principal: Principal, count_id: uuid.UUID) -> StockCountOut:
    return _out(db, settings, principal, _get(db, principal, count_id))


def list_counts(
    db: Session, settings: Settings, principal: Principal, *, store_id: uuid.UUID | None, limit: int
) -> list[StockCountSummary]:
    query = select(StockCount).order_by(StockCount.created_at.desc()).limit(limit)
    scope = principal.store_id or store_id
    if scope is not None:
        query = query.where(StockCount.store_id == scope)
    summaries = []
    for count in db.scalars(query).unique().all():
        detail = _out(db, settings, principal, count)
        summaries.append(
            StockCountSummary(
                id=detail.id,
                number=detail.number,
                store_name=detail.store_name,
                category_name=detail.category_name,
                status=detail.status,
                blind=detail.blind,
                created_by_name=detail.created_by_name,
                created_at=detail.created_at,
                closed_at=detail.closed_at,
                lines_total=detail.lines_total,
                lines_counted=detail.lines_counted,
                net_variance=detail.net_variance,
                variance_value_cents=detail.variance_value_cents,
            )
        )
    return summaries


@portal_errors
def create(db: Session, settings: Settings, principal: Principal, data: StockCountCreate) -> StockCountOut:
    user = _user(principal)
    _require_store(principal, data.store_id)
    store = db.get(Store, data.store_id)
    if store is None or not store.is_active:
        raise ApiError(404, "not_found", "Store was not found.")
    if data.category_id is not None and db.get(Category, data.category_id) is None:
        raise ApiError(404, "not_found", "Category was not found.")
    if data.product_model_id is not None and db.get(ProductModel, data.product_model_id) is None:
        raise ApiError(404, "not_found", "Model was not found.")
    overlapping = select(StockCount.number).where(StockCount.store_id == data.store_id, StockCount.status.in_(ACTIVE))
    if data.category_id is not None:
        # A whole-store count overlaps every category count; two category counts overlap only on the same category.
        overlapping = overlapping.where(
            or_(StockCount.category_id.is_(None), StockCount.category_id == data.category_id)
        )
    clash = db.scalar(overlapping.limit(1))
    if clash is not None:
        raise ApiError(409, "count_open", f"Count {clash} already covers this stock. Post or cancel it first.")
    count = StockCount(
        number=next_server_number(db, store.id, "CNT"),
        store_id=store.id,
        category_id=data.category_id,
        product_model_id=data.product_model_id,
        blind=data.blind,
        note=data.note.strip(),
        created_by_id=user.id,
    )
    db.add(count)
    db.flush()
    products = (
        select(Product.id)
        .join(InventoryLevel, InventoryLevel.product_id == Product.id)
        .where(
            InventoryLevel.store_id == store.id,
            Product.is_service.is_(False),
            Product.is_stock_tracked.is_(True),
        )
    )
    if data.category_id is not None:
        products = products.where(Product.category_id == data.category_id)
    if data.product_model_id is not None:
        products = products.where(Product.product_model_id == data.product_model_id)
    for product_id in db.scalars(products).all():
        db.add(StockCountLine(count_id=count.id, product_id=product_id, scanned_serials=[]))
    db.commit()
    db.refresh(count)
    return _out(db, settings, principal, count)


@portal_errors
def record(
    db: Session, settings: Settings, principal: Principal, count_id: uuid.UUID, data: StockCountEntries
) -> StockCountOut:
    user = _user(principal)
    count = _get(db, principal, count_id)
    if count.status != "OPEN":
        raise ApiError(409, "count_closed", f"Count {count.number} is {count.status.lower()}; counting has stopped.")
    lines = {line.product_id: line for line in count.lines}
    now = datetime.now(UTC)
    for entry in data.entries:
        product = db.get(Product, entry.product_id)
        if product is None or product.is_service or not product.is_stock_tracked:
            raise ApiError(404, "not_found", "Product was not found.")
        if count.category_id is not None and product.category_id != count.category_id:
            raise ApiError(422, "out_of_scope", f"{product.name} is outside this count's category.")
        if count.product_model_id is not None and product.product_model_id != count.product_model_id:
            raise ApiError(422, "out_of_scope", f"{product.name} is outside this count's model.")
        if product.is_serialized != (entry.serials is not None):
            raise ApiError(
                422,
                "count_measure",
                f"Scan each {product.name} unit."
                if product.is_serialized
                else f"Enter the quantity of {product.name}.",
            )
        line = lines.get(product.id)
        if line is None:
            line = StockCountLine(count_id=count.id, product_id=product.id, scanned_serials=[])
            db.add(line)
            lines[product.id] = line
        if entry.serials is not None:
            scanned: dict[str, str] = {}
            for serial in entry.serials:
                normalized = normalize_identifier(serial.kind, serial.value)
                scanned[identifier_hash(normalized)] = _tail(normalized)
            line.scanned_serials = [{"hash": key, "tail": tail} for key, tail in scanned.items()]
            line.counted_qty = len(scanned)
        else:
            line.counted_qty = entry.counted_qty
        line.expected_qty = level_for(db, product.id, count.store_id).quantity_on_hand
        line.counted_by_id = user.id
        line.counted_at = now
    db.commit()
    db.refresh(count)
    return _out(db, settings, principal, count)


def _transition(db: Session, principal: Principal, count_id: uuid.UUID, allowed: tuple[str, ...]) -> StockCount:
    count = _get(db, principal, count_id)
    if count.status not in allowed:
        raise ApiError(409, "count_state", f"Count {count.number} is {count.status.lower()}.")
    return count


def submit(db: Session, settings: Settings, principal: Principal, count_id: uuid.UUID) -> StockCountOut:
    user = _user(principal)
    count = _transition(db, principal, count_id, ("OPEN",))
    if not any(line.counted_qty is not None for line in count.lines):
        raise ApiError(422, "nothing_counted", "Count at least one product before submitting.")
    count.status = "SUBMITTED"
    count.submitted_by_id = user.id
    count.submitted_at = datetime.now(UTC)
    db.commit()
    return _out(db, settings, principal, count)


def reopen(db: Session, settings: Settings, principal: Principal, count_id: uuid.UUID) -> StockCountOut:
    count = _transition(db, principal, count_id, ("SUBMITTED",))
    count.status = "OPEN"
    count.submitted_at = None
    db.commit()
    return _out(db, settings, principal, count)


def cancel(db: Session, settings: Settings, principal: Principal, count_id: uuid.UUID) -> StockCountOut:
    user = _user(principal)
    count = _transition(db, principal, count_id, ACTIVE)
    count.status = "CANCELLED"
    count.posted_by_id = user.id
    count.closed_at = datetime.now(UTC)
    db.commit()
    return _out(db, settings, principal, count)


@portal_errors
def post(db: Session, settings: Settings, principal: Principal, count_id: uuid.UUID) -> StockCountOut:
    """Books every counted variance. Uncounted lines are left alone; missing serialized units go to quarantine
    (recoverable), and scanned units the system places elsewhere are reported for a manual adjustment."""
    user = _user(principal)
    count = _transition(db, principal, count_id, ACTIVE)
    ledger = {
        "movement_type": "AUDIT_ADJUSTMENT",
        "reference_type": REFERENCE,
        "reference_id": count.id,
        "user_id": user.id,
        "reason_code": REASON,
        "note": f"Stock count {count.number}",
    }
    for line in count.lines:
        if line.counted_qty is None or line.expected_qty is None:
            continue
        product = db.get(Product, line.product_id)
        if product is None:
            continue
        level = level_for(db, product.id, count.store_id)
        before = level.quantity_on_hand
        if product.is_serialized:
            missing, unexpected = _serial_gaps(db, settings, line, count.store_id)
            line.serial_result = {
                "missing": [_tail(decrypt_value(serial.value_encrypted, settings)) for serial in missing],
                "unexpected": unexpected,
            }
            for serial in missing:
                transition_serial(db, serial, status="quarantine", store_id=count.store_id, **ledger)
        else:
            change = line.counted_qty - line.expected_qty
            if change == 0:
                continue
            try:
                move_stock(
                    db, product_id=product.id, store_id=count.store_id, quantity=change, allow_reserved=True, **ledger
                )
            except SyncRejected as exc:
                raise SyncRejected(
                    f"{product.name}: {exc.message} Recount it; stock moved since it was counted."
                ) from exc
        if level.quantity_on_hand != before:
            audit.log_stock_adjustment(
                db,
                level_id=level.id,
                product_id=product.id,
                store_id=count.store_id,
                quantity_before=before,
                quantity_after=level.quantity_on_hand,
                reason=f"{REASON} · {count.number}",
                details={"stock_count_id": str(count.id), "sku": product.sku},
            )
    count.status = "POSTED"
    count.posted_by_id = user.id
    count.closed_at = datetime.now(UTC)
    db.commit()
    db.refresh(count)
    return _out(db, settings, principal, count)
