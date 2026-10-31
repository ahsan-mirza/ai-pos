import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.orders import DiningAreaIn, DiningTableIn, FloorOut
from app.services import order_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanRead = Annotated[Principal, Depends(authorize(Permission.POS_ORDERS, allow_device=True, scopes=("portal", "pos")))]
CanManage = Annotated[Principal, Depends(authorize(Permission.PORTAL_INVENTORY_MANAGE))]


@router.get("/floor", response_model=FloorOut)
def floor(store_id: uuid.UUID, db: Db, principal: CanRead) -> FloorOut:
    return order_service.floor(db, principal, store_id)


@router.post("/areas", response_model=FloorOut, status_code=201)
def create_area(payload: DiningAreaIn, db: Db, principal: CanManage) -> FloorOut:
    return order_service.save_area(db, principal, None, payload)


@router.put("/areas/{area_id}", response_model=FloorOut)
def update_area(area_id: uuid.UUID, payload: DiningAreaIn, db: Db, principal: CanManage) -> FloorOut:
    return order_service.save_area(db, principal, area_id, payload)


@router.post("/tables", response_model=FloorOut, status_code=201)
def create_table(payload: DiningTableIn, db: Db, principal: CanManage) -> FloorOut:
    return order_service.save_table(db, principal, None, payload)


@router.put("/tables/{table_id}", response_model=FloorOut)
def update_table(table_id: uuid.UUID, payload: DiningTableIn, db: Db, principal: CanManage) -> FloorOut:
    return order_service.save_table(db, principal, table_id, payload)


@router.delete("/tables/{table_id}", status_code=204)
def delete_table(table_id: uuid.UUID, db: Db, principal: CanManage) -> Response:
    order_service.delete_table(db, principal, table_id)
    return Response(status_code=204)
