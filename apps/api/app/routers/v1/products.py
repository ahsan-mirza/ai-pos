import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.models.product import Product
from app.routers.v1.deps import assert_store_access, require_device_id, require_idempotency_key
from app.schemas.inventory import MovementOut, MovementType, ProductUpdate
from app.schemas.payloads import ProductOut, ProductPayload, ProductSearchHit, SerialStatus
from app.schemas.product_history import ProductCosting, ProductPurchaseHistory, ProductSalesHistory, ProductSerials
from app.services import catalog_service, inventory, product_history
from app.services.product_search import search_products
from app.services.sync_service import ingest_one

router = APIRouter()


class CatalogRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updated_at: datetime | None
    count: int

CanRead = Annotated[
    Principal,
    Depends(authorize(Permission.PORTAL_ACCESS, allow_device=True, scopes=("portal", "pos"))),
]
CanManage = Annotated[
    Principal,
    Depends(authorize(Permission.PORTAL_INVENTORY_MANAGE, allow_device=True)),
]
StoreParam = Annotated[uuid.UUID | None, Query(description="Report stock at this branch; omit for all branches.")]


def stock_store(principal: Principal, store_id: uuid.UUID | None) -> uuid.UUID | None:
    """Store-bound users always see their own branch's stock."""
    if principal.store_id is not None:
        if store_id is not None and store_id != principal.store_id:
            raise ApiError(403, "store_scope", "You can only view your own store's stock.")
        return principal.store_id
    return store_id


@router.get("", response_model=list[ProductOut])
def list_products(
    db: Annotated[Session, Depends(get_db)],
    principal: CanRead,
    store_id: StoreParam = None,
    category_id: uuid.UUID | None = None,
    sub_category_id: uuid.UUID | None = None,
    brand_id: uuid.UUID | None = None,
    product_model_id: uuid.UUID | None = None,
    season: Annotated[str | None, Query(max_length=16)] = None,
    collection: Annotated[str | None, Query(max_length=80)] = None,
    gender: Annotated[str | None, Query(max_length=12)] = None,
    after: Annotated[uuid.UUID | None, Query(description="Last product id of the previous page.")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
) -> list[ProductOut]:
    return catalog_service.list_products(
        db,
        limit=limit,
        after=after,
        store_id=stock_store(principal, store_id),
        category_id=category_id,
        sub_category_id=sub_category_id,
        brand_id=brand_id,
        product_model_id=product_model_id,
        season=season,
        collection=collection,
        gender=gender,
    )


@router.get("/revision", response_model=CatalogRevision)
def product_revision(db: Annotated[Session, Depends(get_db)], _: CanRead) -> CatalogRevision:
    """Cheap cursor for registers. The catalog itself is downloaded only when this changes."""
    stamp, count = catalog_service.catalog_revision(db)
    return CatalogRevision(updated_at=stamp if isinstance(stamp, datetime) else None, count=count)


@router.get("/search", response_model=list[ProductSearchHit])
def search(
    db: Annotated[Session, Depends(get_db)],
    principal: CanRead,
    q: Annotated[str, Query(min_length=1, max_length=100)],
    store_id: StoreParam = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[ProductSearchHit]:
    return search_products(db, q, limit=limit, store_id=stock_store(principal, store_id))


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: CanRead,
    store_id: StoreParam = None,
) -> ProductOut:
    return catalog_service.get_product(db, product_id, store_id=stock_store(principal, store_id))


HistoryLimit = Annotated[int, Query(ge=1, le=500)]


@router.get("/{product_id}/sales-history", response_model=ProductSalesHistory)
def sales_history(
    product_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(authorize(Permission.PORTAL_REPORTS_READ))],
    store_id: StoreParam = None,
    limit: HistoryLimit = 100,
) -> ProductSalesHistory:
    scope = product_history.scope_for(principal, store_id)
    return product_history.sales_history(db, product_id, store_id=scope, limit=limit)


@router.get("/{product_id}/purchase-history", response_model=ProductPurchaseHistory)
def purchase_history(
    product_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(authorize(Permission.PORTAL_INVENTORY_MANAGE))],
    store_id: StoreParam = None,
    limit: HistoryLimit = 100,
) -> ProductPurchaseHistory:
    scope = product_history.scope_for(principal, store_id)
    return product_history.purchase_history(db, product_id, store_id=scope, limit=limit)


@router.get("/{product_id}/costing", response_model=ProductCosting)
def product_costing(
    product_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(authorize(Permission.PORTAL_INVENTORY_MANAGE))],
    store_id: StoreParam = None,
) -> ProductCosting:
    scope = product_history.scope_for(principal, store_id)
    return product_history.product_costing(db, product_id, store_id=scope)


@router.get("/{product_id}/serials", response_model=ProductSerials)
def product_serials(
    product_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(authorize(Permission.PORTAL_ACCESS))],
    store_id: StoreParam = None,
    status: SerialStatus | None = None,
    q: Annotated[str | None, Query(max_length=64, description="Full IMEI/serial, or its last 4 digits.")] = None,
    limit: HistoryLimit = 200,
) -> ProductSerials:
    scope = product_history.scope_for(principal, store_id)
    return product_history.serials(db, settings, product_id, store_id=scope, status=status, query=q, limit=limit)


@router.get("/{product_id}/movements", response_model=list[MovementOut])
def product_movements(
    product_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(authorize(Permission.PORTAL_ACCESS))],
    store_id: StoreParam = None,
    movement_type: MovementType | None = None,
    limit: HistoryLimit = 200,
) -> list[MovementOut]:
    product_history.require_product(db, product_id)
    return inventory.list_movements(
        db, principal, product_id=product_id, store_id=store_id, movement_type=movement_type, limit=limit
    )


@router.delete("/{product_id}", status_code=204)
def delete_product(
    product_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(authorize(Permission.PORTAL_INVENTORY_MANAGE))],
) -> Response:
    inventory.delete_product(db, product_id)
    return Response(status_code=204)


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(authorize(Permission.PORTAL_INVENTORY_MANAGE))],
) -> ProductOut:
    return inventory.update_product(
        db, product_id, payload, user_id=principal.user.id if principal.user is not None else None
    )


@router.post("", response_model=ProductOut, status_code=201)
def create_product(
    payload: ProductPayload,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: CanManage,
    device_id: Annotated[str, Depends(require_device_id)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> ProductOut:
    """Sync-compatible upsert (registers and integrations). The admin portal uses POST /inventory/products."""
    assert_store_access(principal, payload.store_id)
    result = ingest_one(
        db,
        settings,
        device_id=device_id,
        idempotency_key=idempotency_key,
        entity_type="product",
        payload=payload,
    )
    if result.results[0].status == "duplicate":
        response.status_code = 200
    if db.get(Product, payload.id) is None:
        raise ApiError(500, "not_persisted", "Product was not stored.")
    return catalog_service.get_product(db, payload.id, store_id=payload.store_id)
