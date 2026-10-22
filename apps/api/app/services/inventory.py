"""Branch-isolated stock. Every quantity change goes through move_stock, and every IMEI/serial status or
location change goes through transition_serial, so inventory_levels always equals the stock_movements ledger
and a serialized product's on-hand equals its in-stock units at that branch."""

import functools
import secrets
import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, has_capability
from app.core.config import Settings
from app.core.deps import Principal
from app.core.errors import ApiError, SyncRejected
from app.core.pagination import count_rows
from app.core.security import decrypt_value, encrypt_value
from app.models.base import utcnow
from app.models.batch import BatchItem
from app.models.brand import Brand, ProductModel
from app.models.category import Category, SubCategory
from app.models.inventory import InventoryLevel, StockMovement
from app.models.product import Product
from app.models.product_price import ProductPrice
from app.models.purchasing import GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine
from app.models.recipe import Recipe
from app.models.serial_number import SerialNumber
from app.models.store import Store
from app.models.transfer import StockTransfer, StockTransferLine, StockTransferSerial
from app.models.user import User
from app.schemas.inventory import (
    AvailabilityOut,
    BranchStock,
    GoodsReceiptLineOut,
    GoodsReceiptOut,
    LevelUpdate,
    ManualAdjustment,
    ManualAdjustmentOut,
    MovementOut,
    ProductBrief,
    ProductCreate,
    ProductUpdate,
    PurchaseOrderCreate,
    PurchaseOrderLineOut,
    PurchaseOrderOut,
    ReceiveRequest,
    SerialInput,
    SerialLocation,
    SerialTraceOut,
    StockRow,
    StockSummary,
    StoreSerial,
    StoreUpdate,
    TransferBrief,
    TransferCreate,
    TransferLineOut,
    TransferOut,
    TransferSerialOut,
    TransferShip,
)
from app.schemas.payloads import ProductOut, ProductPriceOut, StoreOut, VolumeBreak
from app.services import (
    audit,
    batch_ledger,
    brand_service,
    fashion_attributes,
    product_image_service,
    uom_service,
)
from app.services.identifiers import identifier_hash, identifier_suffix, normalize_identifier
from app.services.search_terms import identifier_candidates, token_condition

MAX_STOCK_ROWS = 500


# --- Errors --------------------------------------------------------------------------------------


def portal_errors[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    """Portal writes: business-rule failures become 422s and constraint races 409s, always rolled back."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        db = next((arg for arg in args if isinstance(arg, Session)), None)
        try:
            return fn(*args, **kwargs)
        except SyncRejected as exc:
            if db is not None:
                db.rollback()
            raise ApiError(422, "inventory_rejected", exc.message) from exc
        except IntegrityError as exc:
            if db is not None:
                db.rollback()
            raise ApiError(409, "conflict", "The change conflicts with existing data. Refresh and try again.") from exc
        except ApiError:
            if db is not None:
                db.rollback()
            raise

    return wrapper


# --- Core ledger ---------------------------------------------------------------------------------


def _locked_level(db: Session, product_id: uuid.UUID, store_id: uuid.UUID) -> InventoryLevel | None:
    statement = select(InventoryLevel).where(
        InventoryLevel.product_id == product_id, InventoryLevel.store_id == store_id
    )
    if db.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    return db.scalar(statement)


def level_for(db: Session, product_id: uuid.UUID, store_id: uuid.UUID) -> InventoryLevel:
    level = _locked_level(db, product_id, store_id)
    if level is None:
        level = InventoryLevel(
            product_id=product_id,
            store_id=store_id,
            quantity_on_hand=0,
            quantity_reserved=0,
            min_reorder_level=0,
        )
        db.add(level)
        db.flush()
    return level


def move_stock(
    db: Session,
    *,
    product_id: uuid.UUID,
    store_id: uuid.UUID,
    quantity: int,
    movement_type: str,
    reference_type: str,
    reference_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    serial_number_id: uuid.UUID | None = None,
    note: str = "",
    allow_reserved: bool = False,
    reason_code: str | None = None,
    batch_item_id: uuid.UUID | None = None,
    allocate_batches: bool = True,
) -> InventoryLevel:
    """Applies a signed quantity at one branch and appends the ledger row. Raises SyncRejected on shortfall.
    Outgoing units are drawn from purchase batches FIFO (batch_item_id first, when given)."""
    if quantity == 0:
        raise SyncRejected("A stock movement needs a non-zero quantity.")
    level = level_for(db, product_id, store_id)
    if quantity < 0:
        usable = level.quantity_on_hand if allow_reserved else level.available
        if usable + quantity < 0:
            raise SyncRejected(f"Insufficient stock: {max(usable, 0)} available at this branch.")
    level.quantity_on_hand += quantity
    movement = StockMovement(
        product_id=product_id,
        store_id=store_id,
        serial_number_id=serial_number_id,
        movement_type=movement_type,
        quantity=quantity,
        quantity_after=level.quantity_on_hand,
        reference_type=reference_type,
        reference_id=reference_id,
        reason_code=reason_code,
        user_id=user_id,
        note=note[:1000],
    )
    db.add(movement)
    db.flush()
    batch_ledger.on_movement(db, movement, batch_item_id=batch_item_id, allocate=allocate_batches)
    return level


def reserve(db: Session, product_id: uuid.UUID, store_id: uuid.UUID, quantity: int) -> None:
    level = level_for(db, product_id, store_id)
    if level.available < quantity:
        raise SyncRejected(f"Only {max(level.available, 0)} available to reserve at the source branch.")
    level.quantity_reserved += quantity
    db.flush()


def release(db: Session, product_id: uuid.UUID, store_id: uuid.UUID, quantity: int) -> None:
    level = level_for(db, product_id, store_id)
    level.quantity_reserved = max(0, level.quantity_reserved - quantity)
    db.flush()


def transition_serial(
    db: Session,
    serial: SerialNumber,
    *,
    status: str,
    store_id: uuid.UUID,
    movement_type: str,
    reference_type: str,
    reference_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    note: str = "",
    reason_code: str | None = None,
) -> None:
    """Moves one unit between statuses/branches, booking -1/+1 wherever its in-stock branch changes."""
    was = serial.store_id if serial.status == "in_stock" else None
    will = store_id if status == "in_stock" else None
    serial.status = status
    serial.store_id = store_id
    db.flush()
    if was == will:
        return
    common: dict[str, Any] = {
        "product_id": serial.product_id,
        "movement_type": movement_type,
        "reference_type": reference_type,
        "reference_id": reference_id,
        "user_id": user_id,
        "serial_number_id": serial.id,
        "note": note,
        "reason_code": reason_code,
    }
    if was is not None:
        move_stock(db, store_id=was, quantity=-1, allow_reserved=True, **common)
    if will is not None:
        move_stock(db, store_id=will, quantity=1, **common)


def find_serial(db: Session, kind: str, value: str) -> tuple[str, SerialNumber | None]:
    normalized = normalize_identifier(kind, value)
    return normalized, db.scalar(select(SerialNumber).where(SerialNumber.value_hash == identifier_hash(normalized)))


def register_serial(
    db: Session,
    settings: Settings,
    *,
    product: Product,
    store_id: uuid.UUID,
    kind: str,
    value: str,
    movement_type: str,
    reference_type: str,
    reference_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    reason_code: str | None = None,
    note: str = "",
) -> SerialNumber:
    if not product.is_serialized:
        raise SyncRejected(f"{product.name} does not track IMEI or serial numbers.")
    normalized, existing = find_serial(db, kind, value)
    if existing is not None:
        raise SyncRejected(f"{normalized} is already registered.")
    serial = SerialNumber(
        product_id=product.id,
        store_id=store_id,
        kind=kind,
        value_hash=identifier_hash(normalized),
        value_encrypted=encrypt_value(normalized, settings),
        value_suffix=identifier_suffix(normalized),
        status="received",
    )
    db.add(serial)
    db.flush()
    transition_serial(
        db,
        serial,
        status="in_stock",
        store_id=store_id,
        movement_type=movement_type,
        reference_type=reference_type,
        reference_id=reference_id,
        user_id=user_id,
        reason_code=reason_code,
        note=note,
    )
    return serial


# --- Lookups and scoping -------------------------------------------------------------------------


def _store(db: Session, store_id: uuid.UUID, *, active: bool = True) -> Store:
    store = db.get(Store, store_id)
    if store is None:
        raise ApiError(404, "not_found", "Store was not found.")
    if active and not store.is_active:
        raise ApiError(422, "store_inactive", f"{store.name} is inactive.")
    return store


def _product(db: Session, product_id: uuid.UUID) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise ApiError(404, "not_found", "Product was not found.")
    return product


def _scope(principal: Principal, store_id: uuid.UUID | None) -> uuid.UUID | None:
    """Store-bound users always see their own branch; global users may pick one or none (consolidated)."""
    if principal.store_id is not None:
        if store_id is not None and store_id != principal.store_id:
            raise ApiError(403, "store_scope", "You can only work with your own store's stock.")
        return principal.store_id
    return store_id


def _require_store_access(principal: Principal, store_id: uuid.UUID) -> None:
    if principal.store_id is not None and principal.store_id != store_id:
        raise ApiError(403, "store_scope", "You can only work with your own store's stock.")


def _user_id(principal: Principal) -> uuid.UUID | None:
    return principal.user.id if principal.user is not None else None


def _actor(principal: Principal) -> User:
    if principal.user is None:
        raise ApiError(403, "forbidden", "This action requires a signed-in user.")
    return principal.user


def _names(db: Session, ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {item for item in ids if item is not None}
    if not wanted:
        return {}
    return {user.id: user.full_name for user in db.scalars(select(User).where(User.id.in_(wanted))).unique().all()}


def _stores(db: Session, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Store]:
    wanted = set(ids)
    if not wanted:
        return {}
    return {store.id: store for store in db.scalars(select(Store).where(Store.id.in_(wanted))).all()}


def _number(db: Session, prefix: str, model: type[PurchaseOrder] | type[StockTransfer] | type[GoodsReceipt]) -> str:
    stamp = datetime.now(UTC).strftime("%y%m%d")
    for _ in range(10):
        candidate = f"{prefix}-{stamp}-{secrets.token_hex(2).upper()}"
        if db.scalar(select(model.id).where(model.number == candidate)) is None:
            return candidate
    raise ApiError(409, "conflict", "Could not allocate a document number. Try again.")


def _last4(serial: SerialNumber, settings: Settings) -> str:
    return decrypt_value(serial.value_encrypted, settings)[-4:]


# --- Products and stock rows ---------------------------------------------------------------------


def products_out(db: Session, products: list[Product], store_id: uuid.UUID | None) -> list[ProductOut]:
    """Catalog rows with stock at `store_id`, or summed over active branches when store_id is None."""
    ids = [product.id for product in products]
    totals: dict[uuid.UUID, tuple[int, int]] = {}
    if ids:
        statement = (
            select(
                InventoryLevel.product_id,
                func.coalesce(func.sum(InventoryLevel.quantity_on_hand), 0),
                func.coalesce(func.sum(InventoryLevel.quantity_reserved), 0),
            )
            .join(Store, Store.id == InventoryLevel.store_id)
            .where(InventoryLevel.product_id.in_(ids))
            .group_by(InventoryLevel.product_id)
        )
        if store_id is not None:
            statement = statement.where(InventoryLevel.store_id == store_id)
        else:
            statement = statement.where(Store.is_active.is_(True))
        totals = {row[0]: (int(row[1]), int(row[2])) for row in db.execute(statement).all()}
    expiries: dict[uuid.UUID, date] = {}
    if ids and store_id is not None and has_capability(db, Capability.FEFO):
        expiry_rows = db.execute(
            select(BatchItem.product_id, func.min(BatchItem.expiry_date))
            .where(
                BatchItem.product_id.in_(ids),
                BatchItem.store_id == store_id,
                BatchItem.quantity_remaining > 0,
                BatchItem.expiry_date.is_not(None),
            )
            .group_by(BatchItem.product_id)
        ).all()
        expiries = {row[0]: row[1] for row in expiry_rows if row[1] is not None}
    dishes = (
        set(db.scalars(select(Recipe.product_id).where(Recipe.product_id.in_(ids))).all())
        if ids and has_capability(db, Capability.RECIPES)
        else set()
    )
    from app.services.price_list_service import catalog_entries

    currency = products[0].currency if products else ""
    lists = catalog_entries(db, set(ids), currency, store_id) if ids else {}
    covers = product_image_service.cover_urls(db, products)
    out = []
    for product in products:
        on_hand, reserved = totals.get(product.id, (0, 0))
        image_url, thumb_url = covers.get(product.id, (None, None))
        out.append(
            ProductOut(
                id=product.id,
                store_id=store_id,
                sku=product.sku,
                barcode=product.barcode,
                name=product.name,
                model_number=product.model_number,
                brand=product.brand,
                category=product.category,
                category_id=product.category_id,
                sub_category=product.sub_category_ref.name if product.sub_category_ref is not None else None,
                sub_category_id=product.sub_category_id,
                brand_id=product.brand_id,
                product_model_id=product.product_model_id,
                model_name=product.product_model.name if product.product_model is not None else None,
                variant_attributes=product.variant_attributes or {},
                price_cents=product.price_cents,
                compare_at_cents=product.compare_at_cents,
                currency=product.currency,
                is_serialized=product.is_serialized,
                stock_quantity=on_hand,
                quantity_reserved=reserved,
                min_order_quantity=product.min_order_quantity,
                sellable_units=product.sellable_units or ["PIECE"],
                unit_options=uom_service.options_for(db, product.sellable_units),
                prices=[price_out(row) for row in product.prices],
                tax_category=product.tax_category,  # type: ignore[arg-type]
                is_open_price=product.is_open_price,
                is_service=product.is_service,
                sold_by_weight=product.sold_by_weight,
                plu_code=product.plu_code,
                tare_grams=product.tare_grams,
                nearest_expiry=expiries.get(product.id),
                has_recipe=product.id in dishes,
                is_ingredient=product.is_ingredient,
                price_lists=lists.get(product.id, []),
                image_url=image_url,
                thumb_url=thumb_url,
                season=product.season,
                collection=product.collection,
                gender=product.gender,
                material=product.material,
                fit=product.fit,
                care=product.care,
                created_at=product.created_at,
                updated_at=product.updated_at,
            )
        )
    return out


def price_out(row: ProductPrice) -> ProductPriceOut:
    return ProductPriceOut(
        price_tier=row.price_tier,  # type: ignore[arg-type]
        price_cents=row.price_cents,
        min_order_quantity=row.min_order_quantity,
        volume_discounts=[VolumeBreak(**item) for item in row.volume_discounts or []],
    )


def _status(on_hand: int, minimum: int, maximum: int | None) -> str:
    if on_hand <= 0:
        return "out"
    if minimum and on_hand <= minimum:
        return "low"
    if maximum is not None and on_hand > maximum:
        return "over"
    return "ok"


def _stock_row(product: Product, store: Store | None, levels: list[InventoryLevel]) -> StockRow:
    on_hand = sum(level.quantity_on_hand for level in levels)
    reserved = sum(level.quantity_reserved for level in levels)
    minimum = sum(level.min_reorder_level for level in levels)
    maxima = [level.max_stock_level for level in levels if level.max_stock_level is not None]
    maximum = sum(maxima) if maxima and len(maxima) == len(levels) else None
    single = levels[0] if store is not None and levels else None
    return StockRow(
        product_id=product.id,
        sku=product.sku,
        name=product.name,
        brand=product.brand,
        model_number=product.model_number,
        is_serialized=product.is_serialized,
        sold_by_weight=product.sold_by_weight,
        category=product.category,
        category_id=product.category_id,
        sub_category=product.sub_category_ref.name if product.sub_category_ref is not None else None,
        sub_category_id=product.sub_category_id,
        brand_id=product.brand_id,
        product_model_id=product.product_model_id,
        model_name=product.product_model.name if product.product_model is not None else None,
        store_id=store.id if store is not None else None,
        store_code=store.code if store is not None else None,
        store_name=store.name if store is not None else None,
        store_count=sum(1 for level in levels if level.quantity_on_hand > 0),
        quantity_on_hand=on_hand,
        quantity_reserved=reserved,
        quantity_available=on_hand - reserved,
        min_reorder_level=minimum,
        max_stock_level=maximum,
        aisle_shelf_location=single.aisle_shelf_location if single is not None else None,
        status=_status(on_hand, minimum, maximum),  # type: ignore[arg-type]
    )


def stock_summary(
    db: Session,
    principal: Principal,
    *,
    store_id: uuid.UUID | None,
    category_id: uuid.UUID | None,
    sub_category_id: uuid.UUID | None,
    brand_id: uuid.UUID | None = None,
    product_model_id: uuid.UUID | None = None,
    status: str | None,
    query: str | None,
    season: str | None = None,
    collection: str | None = None,
    gender: str | None = None,
) -> StockSummary:
    scope = _scope(principal, store_id)
    store = _store(db, scope, active=False) if scope is not None else None
    statement = select(Product).order_by(Product.name).limit(MAX_STOCK_ROWS)
    statement = fashion_attributes.filter_products(statement, season=season, collection=collection, gender=gender)
    if category_id is not None:
        statement = statement.where(Product.category_id == category_id)
    if sub_category_id is not None:
        statement = statement.where(Product.sub_category_id == sub_category_id)
    if brand_id is not None:
        statement = statement.where(Product.brand_id == brand_id)
    if product_model_id is not None:
        statement = statement.where(Product.product_model_id == product_model_id)
    tokens = (query or "").strip().lower().split()[:6]
    for token in tokens:
        statement = statement.where(token_condition(token))
    products = list(db.scalars(statement).unique().all())

    levels_by_product: dict[uuid.UUID, list[InventoryLevel]] = defaultdict(list)
    if products:
        level_query = (
            select(InventoryLevel)
            .join(Store, Store.id == InventoryLevel.store_id)
            .where(InventoryLevel.product_id.in_([product.id for product in products]))
        )
        if scope is not None:
            level_query = level_query.where(InventoryLevel.store_id == scope)
        else:
            level_query = level_query.where(Store.is_active.is_(True))
        for level in db.scalars(level_query).all():
            levels_by_product[level.product_id].append(level)

    rows = [_stock_row(product, store, levels_by_product.get(product.id, [])) for product in products]
    if status is not None:
        rows = [row for row in rows if row.status == status]
    return StockSummary(
        consolidated=scope is None,
        store_id=scope,
        rows=rows,
        units_on_hand=sum(row.quantity_on_hand for row in rows),
        low_count=sum(1 for row in rows if row.status == "low"),
        out_count=sum(1 for row in rows if row.status == "out"),
    )


def _single_row(db: Session, product: Product, store: Store) -> StockRow:
    level = db.scalar(
        select(InventoryLevel).where(InventoryLevel.product_id == product.id, InventoryLevel.store_id == store.id)
    )
    return _stock_row(product, store, [level] if level is not None else [])


@portal_errors
def update_level(
    db: Session,
    principal: Principal,
    product_id: uuid.UUID,
    store_id: uuid.UUID,
    data: LevelUpdate,
) -> StockRow:
    _require_store_access(principal, store_id)
    product = _product(db, product_id)
    store = _store(db, store_id, active=False)
    level = level_for(db, product.id, store.id)
    if data.min_reorder_level is not None:
        level.min_reorder_level = data.min_reorder_level
    if data.max_stock_level is not None:
        level.max_stock_level = data.max_stock_level
    if data.clear_max:
        level.max_stock_level = None
    if level.max_stock_level is not None and level.max_stock_level < level.min_reorder_level:
        raise ApiError(422, "invalid_request", "Max stock level must be at least the reorder level.")
    if "aisle_shelf_location" in data.model_fields_set:
        location = (data.aisle_shelf_location or "").strip()
        level.aisle_shelf_location = location or None
    db.commit()
    return _single_row(db, product, store)


MANUAL_REFERENCE = "manual_adjustment"
DAMAGE_REASONS = frozenset({"DAMAGED_OR_EXPIRED", "STOLEN_SHRINKAGE"})
INBOUND_ONLY_REASONS = frozenset({"SUPPLIER_SAMPLE_IN"})
# Where a written-off IMEI/serial unit goes. Demo units can come back; everything else leaves sellable stock for good.
WRITE_OFF_STATUS = {"DAMAGED_OR_EXPIRED": "defective", "INTERNAL_DEMO_USE": "quarantine"}


def _adjustment_result(
    db: Session,
    product: Product,
    store: Store,
    adjustment_id: uuid.UUID,
    *,
    duplicate: bool,
) -> ManualAdjustmentOut:
    movements = list(
        db.scalars(
            select(StockMovement)
            .where(StockMovement.reference_type == MANUAL_REFERENCE, StockMovement.reference_id == adjustment_id)
            .order_by(StockMovement.created_at)
        ).all()
    )
    return ManualAdjustmentOut(
        adjustment_id=adjustment_id,
        duplicate=duplicate,
        quantity_change=sum(movement.quantity for movement in movements),
        row=_single_row(db, product, store),
        movements=_movements_out(db, movements),
    )


@portal_errors
def manual_adjust(db: Session, settings: Settings, principal: Principal, data: ManualAdjustment) -> ManualAdjustmentOut:
    """Manual override of one branch's stock. Every unit change is an immutable ledger row carrying the reason code,
    the explanation, and the user; replaying the same adjustment_id returns the original result unchanged."""
    actor = _actor(principal)
    _require_store_access(principal, data.store_id)
    product = _product(db, data.product_id)
    store = _store(db, data.store_id)
    already = db.scalar(
        select(StockMovement.id).where(
            StockMovement.reference_type == MANUAL_REFERENCE, StockMovement.reference_id == data.adjustment_id
        )
    )
    if already is not None:
        return _adjustment_result(db, product, store, data.adjustment_id, duplicate=True)

    level = level_for(db, product.id, store.id)
    if data.mode == "add":
        change = data.quantity
    elif data.mode == "remove":
        change = -data.quantity
    else:
        change = data.quantity - level.quantity_on_hand
    if change == 0:
        held = level.quantity_on_hand
        raise ApiError(422, "no_change", f"{store.code} already holds {held} units. Nothing to adjust.")
    if change > 0 and data.reason_code in DAMAGE_REASONS:
        raise ApiError(422, "reason_mismatch", "Damage and shrinkage reasons can only remove stock.")
    if change < 0 and data.reason_code in INBOUND_ONLY_REASONS:
        raise ApiError(422, "reason_mismatch", "Supplier samples can only add stock.")
    movement_type = "DAMAGE_SHRINKAGE" if data.reason_code in DAMAGE_REASONS else "AUDIT_ADJUSTMENT"
    ledger: dict[str, Any] = {
        "movement_type": movement_type,
        "reference_type": MANUAL_REFERENCE,
        "reference_id": data.adjustment_id,
        "user_id": actor.id,
        "reason_code": data.reason_code,
        "note": data.note,
    }

    if not product.is_serialized:
        if data.new_serials or data.remove_serial_ids:
            raise ApiError(422, "invalid_request", f"{product.name} does not track IMEI or serial numbers.")
        move_stock(db, product_id=product.id, store_id=store.id, quantity=change, **ledger)
    elif change > 0:
        if data.remove_serial_ids or len(data.new_serials) != change:
            raise ApiError(
                422,
                "serials_required",
                f"Scan {change} IMEI/serial number{'s' if change != 1 else ''} for the units being added.",
            )
        for entry in data.new_serials:
            normalized, serial = find_serial(db, entry.kind, entry.value)
            if serial is None:
                register_serial(
                    db,
                    settings,
                    product=product,
                    store_id=store.id,
                    kind=entry.kind,
                    value=normalized,
                    **ledger,
                )
                continue
            if serial.product_id != product.id:
                raise ApiError(422, "serial_mismatch", f"{normalized} belongs to a different product.")
            if serial.status == "in_stock":
                where = "here" if serial.store_id == store.id else "at another branch"
                raise ApiError(422, "serial_state", f"{normalized} is already in stock {where}.")
            if serial.status in {"sold", "in_transit"}:
                raise ApiError(422, "serial_state", f"{normalized} is {serial.status.replace('_', ' ')}.")
            transition_serial(db, serial, status="in_stock", store_id=store.id, **ledger)
    else:
        if data.new_serials or len(set(data.remove_serial_ids)) != -change:
            raise ApiError(
                422,
                "serials_required",
                f"Select the {-change} IMEI/serial unit{'s' if change != -1 else ''} being written off.",
            )
        status = WRITE_OFF_STATUS.get(data.reason_code, "scrapped")
        for serial_id in set(data.remove_serial_ids):
            serial = db.get(SerialNumber, serial_id)
            if serial is None or serial.product_id != product.id:
                raise ApiError(422, "serial_mismatch", f"A selected unit is not a registered {product.name}.")
            if serial.status != "in_stock" or serial.store_id != store.id:
                raise ApiError(422, "serial_state", f"A selected unit is no longer in stock at {store.name}. Refresh.")
            transition_serial(db, serial, status=status, store_id=store.id, **ledger)

    audit.log_stock_adjustment(
        db,
        level_id=level.id,
        product_id=product.id,
        store_id=store.id,
        quantity_before=level.quantity_on_hand - change,
        quantity_after=level.quantity_on_hand,
        reason=" · ".join(part for part in (data.reason_code, data.note.strip()) if part),
        details={"adjustment_id": data.adjustment_id, "sku": product.sku, "mode": data.mode},
    )
    db.commit()
    return _adjustment_result(db, product, store, data.adjustment_id, duplicate=False)


def list_store_serials(
    db: Session,
    settings: Settings,
    principal: Principal,
    *,
    product_id: uuid.UUID,
    store_id: uuid.UUID,
    status: str,
) -> list[StoreSerial]:
    """Units of one product at one branch, decrypted so a manager can pick the exact device to write off."""
    _require_store_access(principal, store_id)
    rows = db.scalars(
        select(SerialNumber)
        .where(
            SerialNumber.product_id == product_id,
            SerialNumber.store_id == store_id,
            SerialNumber.status == status,
        )
        .order_by(SerialNumber.created_at)
    ).all()
    return [
        StoreSerial(
            id=row.id,
            kind=row.kind,  # type: ignore[arg-type]
            value=decrypt_value(row.value_encrypted, settings),
            status=row.status,  # type: ignore[arg-type]
            updated_at=row.updated_at,
        )
        for row in rows
    ]


def list_movements(
    db: Session,
    principal: Principal,
    *,
    product_id: uuid.UUID | None,
    store_id: uuid.UUID | None,
    movement_type: str | None,
    limit: int,
) -> list[MovementOut]:
    scope = _scope(principal, store_id)
    statement = select(StockMovement).order_by(StockMovement.created_at.desc()).limit(limit)
    if scope is not None:
        statement = statement.where(StockMovement.store_id == scope)
    if product_id is not None:
        statement = statement.where(StockMovement.product_id == product_id)
    if movement_type is not None:
        statement = statement.where(StockMovement.movement_type == movement_type)
    return _movements_out(db, list(db.scalars(statement).all()))


def _movements_out(db: Session, rows: list[StockMovement]) -> list[MovementOut]:
    products = (
        {
            product.id: product
            for product in db.scalars(select(Product).where(Product.id.in_({row.product_id for row in rows}))).unique()
        }
        if rows
        else {}
    )
    stores = _stores(db, {row.store_id for row in rows})
    names = _names(db, (row.user_id for row in rows))
    return [
        MovementOut(
            id=row.id,
            product_id=row.product_id,
            sku=products[row.product_id].sku if row.product_id in products else "",
            product_name=products[row.product_id].name if row.product_id in products else "Unknown product",
            store_id=row.store_id,
            store_code=stores[row.store_id].code if row.store_id in stores else "",
            serial_number_id=row.serial_number_id,
            movement_type=row.movement_type,  # type: ignore[arg-type]
            quantity=row.quantity,
            quantity_after=row.quantity_after,
            reference_type=row.reference_type,
            reference_id=row.reference_id,
            reason_code=row.reason_code,  # type: ignore[arg-type]
            user_name=names.get(row.user_id) if row.user_id is not None else None,
            note=row.note,
            created_at=row.created_at,
        )
        for row in rows
    ]


# --- Cross-branch availability and IMEI tracing --------------------------------------------------


def _resolve_serial(db: Session, value: str) -> SerialNumber | None:
    hashes = identifier_candidates(value)
    if not hashes:
        return None
    return db.scalar(select(SerialNumber).where(SerialNumber.value_hash.in_(hashes.keys())).limit(1))


def _location(db: Session, settings: Settings, serial: SerialNumber) -> SerialLocation:
    store = _store(db, serial.store_id, active=False)
    level = db.scalar(
        select(InventoryLevel).where(
            InventoryLevel.product_id == serial.product_id, InventoryLevel.store_id == store.id
        )
    )
    return SerialLocation(
        serial_number_id=serial.id,
        kind=serial.kind,  # type: ignore[arg-type]
        last4=_last4(serial, settings),
        status=serial.status,  # type: ignore[arg-type]
        store_id=store.id,
        store_code=store.code,
        store_name=store.name,
        is_warehouse=store.is_warehouse,
        aisle_shelf_location=level.aisle_shelf_location if level is not None else None,
    )


def _brief(product: Product) -> ProductBrief:
    return ProductBrief(id=product.id, sku=product.sku, name=product.name, is_serialized=product.is_serialized)


def availability(
    db: Session,
    settings: Settings,
    *,
    product_id: uuid.UUID | None,
    serial_value: str | None,
) -> AvailabilityOut:
    """What every active branch and warehouse holds. Read-only, so cashiers may look beyond their store."""
    serial = _resolve_serial(db, serial_value) if serial_value else None
    if serial_value and serial is None:
        raise ApiError(404, "not_found", "No product is registered with that IMEI or serial number.")
    target = serial.product_id if serial is not None else product_id
    if target is None:
        raise ApiError(422, "invalid_request", "Provide a product_id or an IMEI/serial number.")
    product = _product(db, target)
    rows = db.execute(
        select(InventoryLevel, Store)
        .join(Store, Store.id == InventoryLevel.store_id)
        .where(InventoryLevel.product_id == product.id, Store.is_active.is_(True))
    ).all()
    branches = [
        BranchStock(
            store_id=store.id,
            store_code=store.code,
            store_name=store.name,
            is_warehouse=store.is_warehouse,
            address=store.address,
            phone=store.phone,
            quantity_on_hand=level.quantity_on_hand,
            quantity_reserved=level.quantity_reserved,
            quantity_available=level.available,
            aisle_shelf_location=level.aisle_shelf_location,
        )
        for level, store in rows
    ]
    branches.sort(key=lambda row: (row.quantity_available <= 0, row.is_warehouse, row.store_code))
    return AvailabilityOut(
        product=_brief(product),
        branches=branches,
        serial=_location(db, settings, serial) if serial is not None else None,
    )


def trace_serial(db: Session, settings: Settings, value: str) -> SerialTraceOut:
    serial = _resolve_serial(db, value)
    if serial is None:
        raise ApiError(404, "not_found", "No unit is registered with that IMEI or serial number.")
    product = _product(db, serial.product_id)
    history = list(
        db.scalars(
            select(StockMovement)
            .where(StockMovement.serial_number_id == serial.id)
            .order_by(StockMovement.created_at.desc())
        ).all()
    )
    transfers = list(
        db.scalars(
            select(StockTransfer)
            .join(StockTransferSerial, StockTransferSerial.transfer_id == StockTransfer.id)
            .where(StockTransferSerial.serial_number_id == serial.id)
            .order_by(StockTransfer.created_at.desc())
        ).unique()
    )
    stores = _stores(db, {t.source_store_id for t in transfers} | {t.destination_store_id for t in transfers})
    return SerialTraceOut(
        product=_brief(product),
        location=_location(db, settings, serial),
        history=_movements_out(db, history),
        transfers=[
            TransferBrief(
                id=transfer.id,
                number=transfer.number,
                status=transfer.status,  # type: ignore[arg-type]
                source_store_code=stores[transfer.source_store_id].code,
                destination_store_code=stores[transfer.destination_store_id].code,
                shipped_at=transfer.shipped_at,
                received_at=transfer.received_at,
            )
            for transfer in transfers
        ],
    )


# --- Catalog writes ------------------------------------------------------------------------------


def _category_pair(
    db: Session,
    category_id: uuid.UUID,
    sub_category_id: uuid.UUID | None,
) -> tuple[Category, SubCategory | None]:
    category = db.get(Category, category_id)
    if category is None:
        raise ApiError(422, "unknown_category", "Category does not exist.")
    sub = None
    if sub_category_id is not None:
        sub = db.get(SubCategory, sub_category_id)
        if sub is None or sub.category_id != category.id:
            raise ApiError(422, "unknown_sub_category", "Sub-category does not belong to that category.")
    return category, sub


def _brand_for(db: Session, brand_id: uuid.UUID | None, brand_name: str | None) -> Brand | None:
    if brand_id is not None:
        brand = db.get(Brand, brand_id)
        if brand is None:
            raise ApiError(422, "unknown_brand", "Brand does not exist.")
        return brand
    name = (brand_name or "").strip()
    return brand_service.resolve_brand(db, name) if name else None


def _classify(
    db: Session,
    product: Product,
    *,
    model_id: uuid.UUID | None,
    category_id: uuid.UUID | None,
    sub_category_id: uuid.UUID | None,
    brand: Brand | None,
) -> None:
    """A variant inherits brand, sub-category, and category from its model; anything sent alongside must agree."""
    if model_id is not None:
        model = db.get(ProductModel, model_id)
        if model is None:
            raise ApiError(422, "unknown_model", "Model does not exist.")
        sub = model.sub_category
        if (
            (category_id is not None and category_id != sub.category_id)
            or (sub_category_id is not None and sub_category_id != sub.id)
            or (brand is not None and brand.id != model.brand_id)
        ):
            raise ApiError(422, "model_mismatch", "The brand, category, and sub-category must match the model.")
        product.product_model_id = model.id
        fashion_attributes.copy_from_model(model, product)
        category, brand = sub.category, model.brand
    else:
        if category_id is None:
            raise ApiError(422, "unknown_category", "Choose a category.")
        product.product_model_id = None
        category, sub = _category_pair(db, category_id, sub_category_id)
    product.category_id = category.id
    product.category = category.name
    product.sub_category_id = sub.id if sub is not None else None
    product.brand_id = brand.id if brand is not None else None
    product.brand = brand.name if brand is not None else None
    if brand is not None:
        brand_service.link(brand, sub)


@portal_errors
def create_product(db: Session, principal: Principal, data: ProductCreate, currency: str) -> ProductOut:
    if db.scalar(select(Product.id).where(Product.sku == data.sku.strip())) is not None:
        raise ApiError(409, "conflict", "SKU is already in use.")
    if db.scalar(select(Product.id).where(Product.barcode == data.barcode.strip())) is not None:
        raise ApiError(409, "conflict", "Barcode is already in use.")
    store = None
    if data.opening_store_id is not None:
        _require_store_access(principal, data.opening_store_id)
        store = _store(db, data.opening_store_id)
    product = Product(
        sku=data.sku.strip(),
        barcode=data.barcode.strip(),
        name=data.name.strip(),
        model_number=(data.model_number or "").strip() or None,
        variant_attributes=data.variant_attributes,
        price_cents=data.price_cents,
        currency=currency,
        is_serialized=data.is_serialized,
        tax_category=data.tax_category,
        is_open_price=data.is_open_price and not data.is_serialized,
        sold_by_weight=data.sold_by_weight,
        plu_code=data.plu_code if data.sold_by_weight else None,
        tare_grams=data.tare_grams if data.sold_by_weight else 0,
        is_ingredient=data.is_ingredient and not data.is_serialized,
    )
    fashion_attributes.apply(product, data, only_sent=False)
    if product.plu_code and db.scalar(select(Product.id).where(Product.plu_code == product.plu_code)) is not None:
        raise ApiError(409, "conflict", f"PLU {product.plu_code} is already in use.")
    product.sellable_units = uom_service.check_sellable(
        db, data.sellable_units, serialized=data.is_serialized, weighed=data.sold_by_weight
    )
    _classify(
        db,
        product,
        model_id=data.product_model_id,
        category_id=data.category_id,
        sub_category_id=data.sub_category_id,
        brand=_brand_for(db, data.brand_id, data.brand),
    )
    db.add(product)
    db.flush()
    if store is not None:
        level = level_for(db, product.id, store.id)
        level.min_reorder_level = data.min_reorder_level
        if data.opening_quantity:
            move_stock(
                db,
                product_id=product.id,
                store_id=store.id,
                quantity=data.opening_quantity,
                movement_type="AUDIT_ADJUSTMENT",
                reference_type="opening_balance",
                reference_id=product.id,
                user_id=_user_id(principal),
                note="Opening stock",
            )
    db.commit()
    db.refresh(product)
    return products_out(db, [product], store.id if store is not None else None)[0]


def _update_weighing(db: Session, product: Product, data: ProductUpdate) -> None:
    fields = data.model_fields_set
    if data.sold_by_weight is not None and data.sold_by_weight != product.sold_by_weight:
        if data.sold_by_weight and (product.is_serialized or product.is_open_price):
            raise ApiError(422, "invalid_request", "Serialized and open-price products cannot be sold by weight.")
        held = db.scalar(
            select(func.coalesce(func.sum(InventoryLevel.quantity_on_hand), 0)).where(
                InventoryLevel.product_id == product.id
            )
        )
        if held:
            raise ApiError(
                422, "stock_on_hand", "Stock is counted differently by weight; switch only while nothing is on hand."
            )
        product.sold_by_weight = data.sold_by_weight
        if not product.sold_by_weight:
            product.plu_code, product.tare_grams = None, 0
    if "plu_code" in fields and data.plu_code != product.plu_code:
        if data.plu_code is not None:
            if not product.sold_by_weight:
                raise ApiError(422, "invalid_request", "Only weighed products carry a scale PLU code.")
            taken = db.scalar(select(Product.id).where(Product.plu_code == data.plu_code, Product.id != product.id))
            if taken is not None:
                raise ApiError(409, "conflict", f"PLU {data.plu_code} is already in use.")
        product.plu_code = data.plu_code
    if data.tare_grams is not None and product.sold_by_weight:
        product.tare_grams = data.tare_grams


@portal_errors
def update_product(db: Session, product_id: uuid.UUID, data: ProductUpdate) -> ProductOut:
    product = _product(db, product_id)
    if data.name is not None:
        product.name = data.name.strip()
    if "model_number" in data.model_fields_set:
        product.model_number = (data.model_number or "").strip() or None
    if data.variant_attributes is not None:
        product.variant_attributes = data.variant_attributes
    if data.price_cents is not None and data.price_cents != product.price_cents:
        from app.services import markdown_service

        markdown_service.record(db, product, data.price_cents, "MANUAL")
        product.price_cents = data.price_cents
    if data.tax_category is not None:
        product.tax_category = data.tax_category
    if data.is_open_price is not None:
        if data.is_open_price and product.is_serialized:
            raise ApiError(422, "invalid_request", "Serialized products cannot be open-price.")
        product.is_open_price = data.is_open_price
    if data.is_ingredient is not None:
        if data.is_ingredient and db.scalar(select(Recipe.id).where(Recipe.product_id == product.id)):
            raise ApiError(422, "invalid_request", "A dish with a recipe cannot be an ingredient.")
        product.is_ingredient = data.is_ingredient and not product.is_serialized
    _update_weighing(db, product, data)
    if data.sellable_units is not None:
        product.sellable_units = uom_service.check_sellable(
            db, data.sellable_units, serialized=product.is_serialized, weighed=product.sold_by_weight
        )
    elif product.sold_by_weight and product.sellable_units not in (None, ["PIECE"]):
        product.sellable_units = ["PIECE"]
    fields = data.model_fields_set
    category_change = data.category_id is not None or data.sub_category_id is not None or data.clear_sub_category
    brand_change = "brand_id" in fields or "brand" in fields
    if "product_model_id" in fields or category_change or brand_change:
        model_id = data.product_model_id if "product_model_id" in fields else product.product_model_id
        category_id = data.category_id or product.category_id
        if data.clear_sub_category:
            sub_id = None
        elif data.sub_category_id is not None:
            sub_id = data.sub_category_id
        elif category_id != product.category_id:
            sub_id = None
        else:
            sub_id = product.sub_category_id
        if brand_change:
            brand = _brand_for(db, data.brand_id, data.brand)
        else:
            brand = db.get(Brand, product.brand_id) if product.brand_id is not None else None
        if model_id is not None and "product_model_id" in fields and not category_change and not brand_change:
            category_id, sub_id, brand = None, None, None
        _classify(db, product, model_id=model_id, category_id=category_id, sub_category_id=sub_id, brand=brand)
    if product.product_model_id is None:
        fashion_attributes.apply(product, data, only_sent=True)
    db.commit()
    db.refresh(product)
    return products_out(db, [product], None)[0]


@portal_errors
def update_store(db: Session, principal: Principal, store_id: uuid.UUID, data: StoreUpdate) -> StoreOut:
    store = _store(db, store_id, active=False)
    _require_store_access(principal, store.id)
    if principal.store_id is not None and (data.is_warehouse is not None or data.is_active is not None):
        raise ApiError(403, "forbidden", "Only Super Admins can change a branch's type or status.")
    if data.name is not None:
        store.name = data.name.strip()
    for field in ("address", "phone"):
        if field in data.model_fields_set:
            setattr(store, field, (getattr(data, field) or "").strip() or None)
    if "emirate" in data.model_fields_set:
        store.emirate = data.emirate
    if data.is_warehouse is not None:
        store.is_warehouse = data.is_warehouse
    if data.is_active is not None:
        store.is_active = data.is_active
    db.commit()
    db.refresh(store)
    return StoreOut.model_validate(store)


# --- Purchase orders -----------------------------------------------------------------------------


def _po_out(db: Session, order: PurchaseOrder) -> PurchaseOrderOut:
    store = _store(db, order.destination_store_id, active=False)
    products = {
        product.id: product
        for product in db.scalars(select(Product).where(Product.id.in_([line.product_id for line in order.lines])))
        .unique()
        .all()
    }
    names = _names(db, [order.created_by_id, *(receipt.received_by_id for receipt in order.receipts)])
    return PurchaseOrderOut(
        id=order.id,
        number=order.number,
        supplier_name=order.supplier_name,
        destination_store_id=store.id,
        destination_store_code=store.code,
        destination_store_name=store.name,
        status=order.status,  # type: ignore[arg-type]
        notes=order.notes,
        expected_at=order.expected_at,
        ordered_at=order.ordered_at,
        received_at=order.received_at,
        created_at=order.created_at,
        created_by_name=names.get(order.created_by_id),
        total_cost_cents=sum(line.unit_cost_cents * line.quantity_ordered for line in order.lines),
        lines=[
            PurchaseOrderLineOut(
                id=line.id,
                product_id=line.product_id,
                sku=products[line.product_id].sku,
                name=products[line.product_id].name,
                is_serialized=products[line.product_id].is_serialized,
                quantity_ordered=line.quantity_ordered,
                quantity_received=line.quantity_received,
                unit_cost_cents=line.unit_cost_cents,
            )
            for line in order.lines
        ],
        receipts=[
            GoodsReceiptOut(
                id=receipt.id,
                number=receipt.number,
                store_id=receipt.store_id,
                received_by_name=names.get(receipt.received_by_id),
                note=receipt.note,
                created_at=receipt.created_at,
                lines=[
                    GoodsReceiptLineOut(
                        purchase_order_line_id=line.purchase_order_line_id,
                        product_id=line.product_id,
                        quantity=line.quantity,
                    )
                    for line in receipt.lines
                ],
            )
            for receipt in order.receipts
        ],
    )


def _order(db: Session, principal: Principal, order_id: uuid.UUID, *, lock: bool = False) -> PurchaseOrder:
    statement = select(PurchaseOrder).where(PurchaseOrder.id == order_id)
    if lock and db.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    order = db.scalar(statement)
    if order is None or (principal.store_id is not None and order.destination_store_id != principal.store_id):
        raise ApiError(404, "not_found", "Purchase order was not found.")
    return order


def list_purchase_orders(
    db: Session,
    principal: Principal,
    *,
    status: str | None,
    store_id: uuid.UUID | None,
    limit: int,
    offset: int = 0,
) -> tuple[list[PurchaseOrderOut], int]:
    """One page of purchase orders, newest first, and the total matching the filters."""
    scope = _scope(principal, store_id)
    statement = select(PurchaseOrder)
    if scope is not None:
        statement = statement.where(PurchaseOrder.destination_store_id == scope)
    if status is not None:
        statement = statement.where(PurchaseOrder.status == status)
    total = count_rows(db, statement)
    page = statement.order_by(PurchaseOrder.created_at.desc(), PurchaseOrder.id).offset(offset).limit(limit)
    return [_po_out(db, order) for order in db.scalars(page).unique().all()], total


def get_purchase_order(db: Session, principal: Principal, order_id: uuid.UUID) -> PurchaseOrderOut:
    return _po_out(db, _order(db, principal, order_id))


@portal_errors
def create_purchase_order(db: Session, principal: Principal, data: PurchaseOrderCreate) -> PurchaseOrderOut:
    actor = _actor(principal)
    _require_store_access(principal, data.destination_store_id)
    _store(db, data.destination_store_id)
    order = PurchaseOrder(
        number=_number(db, "PO", PurchaseOrder),
        supplier_name=data.supplier_name.strip(),
        destination_store_id=data.destination_store_id,
        status="draft",
        notes=data.notes.strip(),
        expected_at=data.expected_at,
        created_by_id=actor.id,
    )
    for position, line in enumerate(data.lines):
        _product(db, line.product_id)
        order.lines.append(
            PurchaseOrderLine(
                position=position,
                product_id=line.product_id,
                quantity_ordered=line.quantity_ordered,
                quantity_received=0,
                unit_cost_cents=line.unit_cost_cents,
            )
        )
    db.add(order)
    db.commit()
    db.refresh(order)
    return _po_out(db, order)


@portal_errors
def mark_ordered(db: Session, principal: Principal, order_id: uuid.UUID) -> PurchaseOrderOut:
    order = _order(db, principal, order_id, lock=True)
    if order.status != "draft":
        raise ApiError(422, "po_state", "Only draft purchase orders can be placed.")
    order.status = "ordered"
    order.ordered_at = utcnow()
    db.commit()
    return _po_out(db, order)


@portal_errors
def cancel_purchase_order(db: Session, principal: Principal, order_id: uuid.UUID) -> PurchaseOrderOut:
    order = _order(db, principal, order_id, lock=True)
    if order.status not in {"draft", "ordered"} or any(line.quantity_received for line in order.lines):
        raise ApiError(422, "po_state", "Only orders with nothing received can be cancelled.")
    order.status = "cancelled"
    db.commit()
    return _po_out(db, order)


def _serial_inputs(serials: list[SerialInput]) -> list[SerialInput]:
    keys = [(serial.kind, serial.value.strip().upper()) for serial in serials]
    if len(set(keys)) != len(keys):
        raise SyncRejected("The same IMEI or serial number is listed twice.")
    return serials


@portal_errors
def receive_purchase_order(
    db: Session,
    settings: Settings,
    principal: Principal,
    order_id: uuid.UUID,
    data: ReceiveRequest,
) -> PurchaseOrderOut:
    """Goods receipt (GRN): books PURCHASE_IN at the order's destination store and registers IMEIs there."""
    actor = _actor(principal)
    order = _order(db, principal, order_id, lock=True)
    if order.status not in {"ordered", "partially_received"}:
        raise ApiError(422, "po_state", "Place the purchase order before receiving goods.")
    store = _store(db, order.destination_store_id)
    lines = {line.id: line for line in order.lines}
    receipt = GoodsReceipt(
        number=_number(db, "GRN", GoodsReceipt),
        purchase_order_id=order.id,
        store_id=store.id,
        received_by_id=actor.id,
        note=data.note.strip(),
    )
    db.add(receipt)
    db.flush()
    seen: set[uuid.UUID] = set()
    for entry in data.lines:
        line = lines.get(entry.purchase_order_line_id)
        if line is None:
            raise ApiError(422, "invalid_request", "Receipt line is not on this purchase order.")
        if line.id in seen:
            raise ApiError(422, "invalid_request", "Each purchase order line can appear once per receipt.")
        seen.add(line.id)
        outstanding = line.quantity_ordered - line.quantity_received
        if entry.quantity > outstanding:
            raise ApiError(422, "over_receipt", f"Only {outstanding} left to receive on this line.")
        product = _product(db, line.product_id)
        if product.is_serialized:
            serials = _serial_inputs(entry.serials)
            if len(serials) != entry.quantity:
                raise ApiError(
                    422,
                    "serials_required",
                    f"Scan {entry.quantity} IMEI/serial numbers for {product.name}; got {len(serials)}.",
                )
            for serial in serials:
                register_serial(
                    db,
                    settings,
                    product=product,
                    store_id=store.id,
                    kind=serial.kind,
                    value=serial.value,
                    movement_type="PURCHASE_IN",
                    reference_type="goods_receipt",
                    reference_id=receipt.id,
                    user_id=actor.id,
                )
        else:
            if entry.serials:
                raise ApiError(422, "invalid_request", f"{product.name} does not track serial numbers.")
            move_stock(
                db,
                product_id=product.id,
                store_id=store.id,
                quantity=entry.quantity,
                movement_type="PURCHASE_IN",
                reference_type="goods_receipt",
                reference_id=receipt.id,
                user_id=actor.id,
                note=f"{order.number} from {order.supplier_name}",
            )
        if entry.aisle_shelf_location:
            level_for(db, product.id, store.id).aisle_shelf_location = entry.aisle_shelf_location.strip()
        line.quantity_received += entry.quantity
        db.add(
            GoodsReceiptLine(
                goods_receipt_id=receipt.id,
                purchase_order_line_id=line.id,
                product_id=product.id,
                quantity=entry.quantity,
            )
        )
    complete = all(line.quantity_received >= line.quantity_ordered for line in order.lines)
    order.status = "received" if complete else "partially_received"
    if complete:
        order.received_at = utcnow()
    if has_capability(db, Capability.SALES_ORDERS):
        from app.services.sales_order_service import allocate_store

        allocate_store(db, store.id)
    db.commit()
    db.refresh(order)
    return _po_out(db, order)


# --- Transfers -----------------------------------------------------------------------------------


def _transfer_out(db: Session, settings: Settings, transfer: StockTransfer) -> TransferOut:
    stores = _stores(db, [transfer.source_store_id, transfer.destination_store_id])
    source, destination = stores[transfer.source_store_id], stores[transfer.destination_store_id]
    products = {
        product.id: product
        for product in db.scalars(select(Product).where(Product.id.in_([line.product_id for line in transfer.lines])))
        .unique()
        .all()
    }
    serials = (
        {
            serial.id: serial
            for serial in db.scalars(
                select(SerialNumber).where(SerialNumber.id.in_([row.serial_number_id for row in transfer.serials]))
            ).all()
        }
        if transfer.serials
        else {}
    )
    names = _names(db, [transfer.requested_by_id, transfer.shipped_by_id, transfer.received_by_id])
    return TransferOut(
        id=transfer.id,
        number=transfer.number,
        source_store_id=source.id,
        source_store_code=source.code,
        source_store_name=source.name,
        destination_store_id=destination.id,
        destination_store_code=destination.code,
        destination_store_name=destination.name,
        status=transfer.status,  # type: ignore[arg-type]
        note=transfer.note,
        requested_by_name=names.get(transfer.requested_by_id),
        shipped_by_name=names.get(transfer.shipped_by_id) if transfer.shipped_by_id else None,
        received_by_name=names.get(transfer.received_by_id) if transfer.received_by_id else None,
        created_at=transfer.created_at,
        shipped_at=transfer.shipped_at,
        received_at=transfer.received_at,
        lines=[
            TransferLineOut(
                id=line.id,
                product_id=line.product_id,
                sku=products[line.product_id].sku,
                name=products[line.product_id].name,
                is_serialized=products[line.product_id].is_serialized,
                quantity=line.quantity,
            )
            for line in transfer.lines
        ],
        serials=[
            TransferSerialOut(
                serial_number_id=row.serial_number_id,
                transfer_line_id=row.transfer_line_id,
                kind=serials[row.serial_number_id].kind,  # type: ignore[arg-type]
                last4=_last4(serials[row.serial_number_id], settings),
                status=serials[row.serial_number_id].status,  # type: ignore[arg-type]
            )
            for row in transfer.serials
            if row.serial_number_id in serials
        ],
    )


def _transfer(db: Session, principal: Principal, transfer_id: uuid.UUID, *, lock: bool = False) -> StockTransfer:
    statement = select(StockTransfer).where(StockTransfer.id == transfer_id)
    if lock and db.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    transfer = db.scalar(statement)
    if transfer is None or (
        principal.store_id is not None
        and principal.store_id not in {transfer.source_store_id, transfer.destination_store_id}
    ):
        raise ApiError(404, "not_found", "Transfer was not found.")
    return transfer


def list_transfers(
    db: Session,
    settings: Settings,
    principal: Principal,
    *,
    status: str | None,
    store_id: uuid.UUID | None,
    limit: int,
    offset: int = 0,
) -> tuple[list[TransferOut], int]:
    """One page of transfers touching the scope, newest first, and the total matching the filters."""
    scope = _scope(principal, store_id)
    statement = select(StockTransfer)
    if scope is not None:
        statement = statement.where(
            (StockTransfer.source_store_id == scope) | (StockTransfer.destination_store_id == scope)
        )
    if status is not None:
        statement = statement.where(StockTransfer.status == status)
    total = count_rows(db, statement)
    page = statement.order_by(StockTransfer.created_at.desc(), StockTransfer.id).offset(offset).limit(limit)
    return [_transfer_out(db, settings, transfer) for transfer in db.scalars(page).unique().all()], total


def get_transfer(db: Session, settings: Settings, principal: Principal, transfer_id: uuid.UUID) -> TransferOut:
    return _transfer_out(db, settings, _transfer(db, principal, transfer_id))


@portal_errors
def create_transfer(db: Session, settings: Settings, principal: Principal, data: TransferCreate) -> TransferOut:
    actor = _actor(principal)
    if principal.store_id is not None and principal.store_id not in {data.source_store_id, data.destination_store_id}:
        raise ApiError(403, "store_scope", "Transfers must start or end at your own store.")
    _store(db, data.source_store_id)
    _store(db, data.destination_store_id)
    transfer = StockTransfer(
        number=_number(db, "TR", StockTransfer),
        source_store_id=data.source_store_id,
        destination_store_id=data.destination_store_id,
        status="requested",
        note=data.note.strip(),
        requested_by_id=actor.id,
    )
    db.add(transfer)
    for position, line in enumerate(data.lines):
        product = _product(db, line.product_id)
        if product.is_serialized:
            in_stock = (
                db.scalar(
                    select(func.count())
                    .select_from(SerialNumber)
                    .where(
                        SerialNumber.product_id == product.id,
                        SerialNumber.store_id == data.source_store_id,
                        SerialNumber.status == "in_stock",
                    )
                )
                or 0
            )
            if in_stock < line.quantity:
                raise ApiError(422, "insufficient_stock", f"Only {in_stock} {product.name} units at the source.")
        else:
            reserve(db, product.id, data.source_store_id, line.quantity)
        transfer.lines.append(StockTransferLine(position=position, product_id=product.id, quantity=line.quantity))
    db.commit()
    db.refresh(transfer)
    return _transfer_out(db, settings, transfer)


@portal_errors
def ship_transfer(
    db: Session,
    settings: Settings,
    principal: Principal,
    transfer_id: uuid.UUID,
    data: TransferShip,
) -> TransferOut:
    """Stock leaves the source branch (TRANSFER_OUT); IMEIs are marked in transit."""
    actor = _actor(principal)
    transfer = _transfer(db, principal, transfer_id, lock=True)
    if transfer.status != "requested":
        raise ApiError(422, "transfer_state", "Only requested transfers can be shipped.")
    _require_store_access(principal, transfer.source_store_id)
    serials_by_line = {entry.transfer_line_id: _serial_inputs(entry.serials) for entry in data.serial_lines}
    for line in transfer.lines:
        product = _product(db, line.product_id)
        if not product.is_serialized:
            if line.id in serials_by_line:
                raise ApiError(422, "invalid_request", f"{product.name} does not track serial numbers.")
            release(db, product.id, transfer.source_store_id, line.quantity)
            move_stock(
                db,
                product_id=product.id,
                store_id=transfer.source_store_id,
                quantity=-line.quantity,
                movement_type="TRANSFER_OUT",
                reference_type="stock_transfer",
                reference_id=transfer.id,
                user_id=actor.id,
                note=transfer.number,
            )
            continue
        entries = serials_by_line.get(line.id, [])
        if len(entries) != line.quantity:
            raise ApiError(
                422,
                "serials_required",
                f"Scan {line.quantity} IMEI/serial numbers for {product.name}; got {len(entries)}.",
            )
        for entry in entries:
            normalized, serial = find_serial(db, entry.kind, entry.value)
            if serial is None or serial.product_id != product.id:
                raise ApiError(422, "serial_mismatch", f"{normalized} is not a registered {product.name}.")
            if serial.status != "in_stock" or serial.store_id != transfer.source_store_id:
                raise ApiError(422, "serial_state", f"{normalized} is not in stock at the source branch.")
            transition_serial(
                db,
                serial,
                status="in_transit",
                store_id=transfer.source_store_id,
                movement_type="TRANSFER_OUT",
                reference_type="stock_transfer",
                reference_id=transfer.id,
                user_id=actor.id,
                note=transfer.number,
            )
            transfer.serials.append(StockTransferSerial(serial_number_id=serial.id, transfer_line_id=line.id))
    transfer.status = "in_transit"
    transfer.shipped_by_id = actor.id
    transfer.shipped_at = utcnow()
    db.commit()
    db.refresh(transfer)
    return _transfer_out(db, settings, transfer)


@portal_errors
def receive_transfer(db: Session, settings: Settings, principal: Principal, transfer_id: uuid.UUID) -> TransferOut:
    """Stock arrives at the destination (TRANSFER_IN); IMEIs are re-homed to the destination branch."""
    actor = _actor(principal)
    transfer = _transfer(db, principal, transfer_id, lock=True)
    if transfer.status != "in_transit":
        raise ApiError(422, "transfer_state", "Only shipped transfers can be received.")
    _require_store_access(principal, transfer.destination_store_id)
    _store(db, transfer.destination_store_id)
    serial_lines = {row.transfer_line_id for row in transfer.serials}
    for line in transfer.lines:
        if line.id in serial_lines:
            continue
        move_stock(
            db,
            product_id=line.product_id,
            store_id=transfer.destination_store_id,
            quantity=line.quantity,
            movement_type="TRANSFER_IN",
            reference_type="stock_transfer",
            reference_id=transfer.id,
            user_id=actor.id,
            note=transfer.number,
        )
    for row in transfer.serials:
        serial = db.get(SerialNumber, row.serial_number_id)
        if serial is None or serial.status != "in_transit":
            raise ApiError(422, "serial_state", "A unit on this transfer is no longer in transit.")
        transition_serial(
            db,
            serial,
            status="in_stock",
            store_id=transfer.destination_store_id,
            movement_type="TRANSFER_IN",
            reference_type="stock_transfer",
            reference_id=transfer.id,
            user_id=actor.id,
            note=transfer.number,
        )
    transfer.status = "received"
    transfer.received_by_id = actor.id
    transfer.received_at = utcnow()
    db.commit()
    db.refresh(transfer)
    return _transfer_out(db, settings, transfer)


@portal_errors
def cancel_transfer(db: Session, settings: Settings, principal: Principal, transfer_id: uuid.UUID) -> TransferOut:
    transfer = _transfer(db, principal, transfer_id, lock=True)
    if transfer.status != "requested":
        raise ApiError(422, "transfer_state", "Only transfers that have not shipped can be cancelled.")
    for line in transfer.lines:
        product = _product(db, line.product_id)
        if not product.is_serialized:
            release(db, product.id, transfer.source_store_id, line.quantity)
    transfer.status = "cancelled"
    db.commit()
    db.refresh(transfer)
    return _transfer_out(db, settings, transfer)
