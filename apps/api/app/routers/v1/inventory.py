import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, require_capability
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.pagination import Offset, set_total
from app.core.permissions import Permission
from app.schemas.inventory import (
    AvailabilityOut,
    LevelUpdate,
    ManualAdjustment,
    ManualAdjustmentOut,
    MovementOut,
    MovementType,
    ProductCreate,
    PurchaseOrderCreate,
    PurchaseOrderOut,
    PurchaseOrderStatus,
    ReceiveRequest,
    SerialTraceOut,
    StockRow,
    StockStatus,
    StockSummary,
    StockView,
    StoreSerial,
    TransferCreate,
    TransferOut,
    TransferShip,
    TransferStatus,
)
from app.schemas.payloads import ProductOut, SerialStatus
from app.schemas.product_history import ProductCosting
from app.services import inventory, product_history
from app.services.settings_service import business_currency

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
CanRead = Annotated[Principal, Depends(authorize(Permission.PORTAL_ACCESS))]
CanManage = Annotated[Principal, Depends(authorize(Permission.PORTAL_INVENTORY_MANAGE))]
CanLookUp = Annotated[
    Principal,
    Depends(authorize(Permission.PORTAL_ACCESS, allow_device=True, scopes=("portal", "pos"))),
]


# --- Stock ---------------------------------------------------------------------------------------


@router.get("/stock", response_model=StockSummary)
def stock(
    db: Db,
    principal: CanRead,
    store_id: Annotated[uuid.UUID | None, Query(description="Omit for all stores (consolidated).")] = None,
    category_id: uuid.UUID | None = None,
    sub_category_id: uuid.UUID | None = None,
    brand_id: uuid.UUID | None = None,
    product_model_id: uuid.UUID | None = None,
    status: StockStatus | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    season: Annotated[str | None, Query(max_length=16)] = None,
    collection: Annotated[str | None, Query(max_length=80)] = None,
    gender: Annotated[str | None, Query(max_length=12)] = None,
    view: StockView = "stock",
) -> StockSummary:
    return inventory.stock_summary(
        db,
        principal,
        store_id=store_id,
        category_id=category_id,
        sub_category_id=sub_category_id,
        brand_id=brand_id,
        product_model_id=product_model_id,
        status=status,
        query=q,
        season=season,
        collection=collection,
        gender=gender,
        view=view,
    )


@router.patch("/levels/{product_id}/{store_id}", response_model=StockRow)
def update_level(product_id: uuid.UUID, store_id: uuid.UUID, payload: LevelUpdate, db: Db, principal: CanManage):
    return inventory.update_level(db, principal, product_id, store_id, payload)


CanAdjust = Annotated[Principal, Depends(authorize(Permission.INVENTORY_ADJUST_STOCK))]
# IMEI / serial lookups need the serial tracking module; availability by product stays open to every register.
SerialModule = [Depends(require_capability(Capability.SERIAL_TRACKING))]


@router.get("/adjust/cost", response_model=ProductCosting)
def adjustment_cost(
    db: Db,
    principal: CanAdjust,
    product_id: uuid.UUID,
    store_id: uuid.UUID,
) -> ProductCosting:
    """Cost layers and valuation for the branch being adjusted. Same figures the product page shows."""
    scope = product_history.scope_for(principal, store_id)
    return product_history.product_costing(db, product_id, store_id=scope)


@router.post("/adjust", response_model=ManualAdjustmentOut, status_code=201)
def adjust(
    payload: ManualAdjustment,
    response: Response,
    db: Db,
    settings: Config,
    principal: CanAdjust,
) -> ManualAdjustmentOut:
    """Manual override at one branch. Requires inventory:adjust_stock; store-bound users only at their own store."""
    result = inventory.manual_adjust(db, settings, principal, payload)
    if result.duplicate:
        response.status_code = 200
    return result


@router.get("/serials", response_model=list[StoreSerial], dependencies=SerialModule)
def store_serials(
    db: Db,
    settings: Config,
    principal: CanAdjust,
    product_id: uuid.UUID,
    store_id: uuid.UUID,
    status: SerialStatus = "in_stock",
) -> list[StoreSerial]:
    return inventory.list_store_serials(
        db, settings, principal, product_id=product_id, store_id=store_id, status=status
    )


@router.get("/movements", response_model=list[MovementOut])
def movements(
    db: Db,
    principal: CanRead,
    product_id: uuid.UUID | None = None,
    store_id: uuid.UUID | None = None,
    movement_type: MovementType | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[MovementOut]:
    return inventory.list_movements(
        db, principal, product_id=product_id, store_id=store_id, movement_type=movement_type, limit=limit
    )


@router.get("/availability", response_model=AvailabilityOut)
def availability(
    db: Db,
    settings: Config,
    _: CanLookUp,
    product_id: uuid.UUID | None = None,
    serial: Annotated[str | None, Query(min_length=4, max_length=64)] = None,
) -> AvailabilityOut:
    return inventory.availability(db, settings, product_id=product_id, serial_value=serial)


@router.get("/serials/trace", response_model=SerialTraceOut, dependencies=SerialModule)
def trace(db: Db, settings: Config, _: CanRead, value: Annotated[str, Query(min_length=4, max_length=64)]):
    return inventory.trace_serial(db, settings, value)


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(payload: ProductCreate, db: Db, principal: CanManage) -> ProductOut:
    return inventory.create_product(db, principal, payload, business_currency(db))


# --- Purchase orders -----------------------------------------------------------------------------


@router.get("/purchase-orders", response_model=list[PurchaseOrderOut])
def purchase_orders(
    db: Db,
    principal: CanRead,
    response: Response,
    offset: Offset,
    status: PurchaseOrderStatus | None = None,
    store_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[PurchaseOrderOut]:
    rows, total = inventory.list_purchase_orders(
        db, principal, status=status, store_id=store_id, limit=limit, offset=offset
    )
    set_total(response, total)
    return rows


@router.post("/purchase-orders", response_model=PurchaseOrderOut, status_code=201)
def create_purchase_order(payload: PurchaseOrderCreate, db: Db, principal: CanManage) -> PurchaseOrderOut:
    return inventory.create_purchase_order(db, principal, payload)


@router.get("/purchase-orders/{order_id}", response_model=PurchaseOrderOut)
def purchase_order(order_id: uuid.UUID, db: Db, principal: CanRead) -> PurchaseOrderOut:
    return inventory.get_purchase_order(db, principal, order_id)


@router.post("/purchase-orders/{order_id}/order", response_model=PurchaseOrderOut)
def place_purchase_order(order_id: uuid.UUID, db: Db, principal: CanManage) -> PurchaseOrderOut:
    return inventory.mark_ordered(db, principal, order_id)


@router.post("/purchase-orders/{order_id}/receive", response_model=PurchaseOrderOut)
def receive_purchase_order(
    order_id: uuid.UUID,
    payload: ReceiveRequest,
    db: Db,
    settings: Config,
    principal: CanManage,
) -> PurchaseOrderOut:
    return inventory.receive_purchase_order(db, settings, principal, order_id, payload)


@router.post("/purchase-orders/{order_id}/cancel", response_model=PurchaseOrderOut)
def cancel_purchase_order(order_id: uuid.UUID, db: Db, principal: CanManage) -> PurchaseOrderOut:
    return inventory.cancel_purchase_order(db, principal, order_id)


# --- Transfers -----------------------------------------------------------------------------------


@router.get("/transfers", response_model=list[TransferOut])
def transfers(
    db: Db,
    settings: Config,
    principal: CanRead,
    response: Response,
    offset: Offset,
    status: TransferStatus | None = None,
    store_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[TransferOut]:
    rows, total = inventory.list_transfers(
        db, settings, principal, status=status, store_id=store_id, limit=limit, offset=offset
    )
    set_total(response, total)
    return rows


@router.post("/transfers", response_model=TransferOut, status_code=201)
def create_transfer(payload: TransferCreate, db: Db, settings: Config, principal: CanManage) -> TransferOut:
    return inventory.create_transfer(db, settings, principal, payload)


@router.get("/transfers/{transfer_id}", response_model=TransferOut)
def transfer(transfer_id: uuid.UUID, db: Db, settings: Config, principal: CanRead) -> TransferOut:
    return inventory.get_transfer(db, settings, principal, transfer_id)


@router.post("/transfers/{transfer_id}/ship", response_model=TransferOut)
def ship_transfer(
    transfer_id: uuid.UUID,
    payload: TransferShip,
    db: Db,
    settings: Config,
    principal: CanManage,
) -> TransferOut:
    return inventory.ship_transfer(db, settings, principal, transfer_id, payload)


@router.post("/transfers/{transfer_id}/receive", response_model=TransferOut)
def receive_transfer(transfer_id: uuid.UUID, db: Db, settings: Config, principal: CanManage) -> TransferOut:
    return inventory.receive_transfer(db, settings, principal, transfer_id)


@router.post("/transfers/{transfer_id}/cancel", response_model=TransferOut)
def cancel_transfer(transfer_id: uuid.UUID, db: Db, settings: Config, principal: CanManage) -> TransferOut:
    return inventory.cancel_transfer(db, settings, principal, transfer_id)
