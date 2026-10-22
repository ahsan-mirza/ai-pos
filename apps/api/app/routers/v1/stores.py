import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.models.store import Store
from app.routers.v1.deps import assert_store_access, require_device_id, require_idempotency_key
from app.schemas.inventory import StoreUpdate
from app.schemas.payloads import StoreOut, StorePayload
from app.services import catalog_service, inventory
from app.services.sync_service import ingest_one

router = APIRouter()


@router.get("", response_model=list[StoreOut])
def list_stores(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[
        Principal,
        Depends(authorize(Permission.PORTAL_ACCESS, allow_device=True, scopes=("portal", "pos"))),
    ],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[StoreOut]:
    """The branch directory is visible to every signed-in user: transfers and branch lookups need it."""
    return catalog_service.list_stores(db, limit=limit)


@router.patch("/{store_id}", response_model=StoreOut)
def update_store(
    store_id: uuid.UUID,
    payload: StoreUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(authorize(Permission.PORTAL_INVENTORY_MANAGE))],
) -> StoreOut:
    return inventory.update_store(db, principal, store_id, payload)


@router.post("", response_model=StoreOut, status_code=201)
def create_store(
    payload: StorePayload,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(authorize(Permission.PORTAL_INVENTORY_MANAGE, allow_device=True))],
    device_id: Annotated[str, Depends(require_device_id)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> StoreOut:
    assert_store_access(principal, payload.id)
    result = ingest_one(
        db,
        settings,
        device_id=device_id,
        idempotency_key=idempotency_key,
        entity_type="store",
        payload=payload,
    )
    if result.results[0].status == "duplicate":
        response.status_code = 200
    row = db.get(Store, payload.id)
    if row is None:
        raise ApiError(500, "not_persisted", "Store was not stored.")
    return StoreOut.model_validate(row)
