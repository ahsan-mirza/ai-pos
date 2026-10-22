import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.kitchen import KitchenStationIn, KitchenStationOut, TicketBoard, TicketOut, TicketStatusIn
from app.services import kitchen_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
# Kitchen screens run on an activated device token, or a signed-in user with kds:operate.
CanOperate = Annotated[
    Principal, Depends(authorize(Permission.KDS_OPERATE, allow_device=True, scopes=("portal", "pos")))
]
# Registers read an order's tickets to print them for stations set to print.
CanRead = Annotated[Principal, Depends(authorize(Permission.POS_ORDERS, allow_device=True, scopes=("portal", "pos")))]
CanManage = Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))]


@router.get("/stations", response_model=list[KitchenStationOut])
def list_stations(store_id: uuid.UUID, db: Db, principal: CanOperate) -> list[KitchenStationOut]:
    return kitchen_service.list_stations(db, principal, store_id)


@router.post("/stations", response_model=KitchenStationOut, status_code=201)
def create_station(payload: KitchenStationIn, db: Db, principal: CanManage) -> KitchenStationOut:
    return kitchen_service.save_station(db, principal, None, payload)


@router.put("/stations/{station_id}", response_model=KitchenStationOut)
def update_station(station_id: uuid.UUID, payload: KitchenStationIn, db: Db, principal: CanManage) -> KitchenStationOut:
    return kitchen_service.save_station(db, principal, station_id, payload)


@router.get("/stations/{station_id}/tickets", response_model=TicketBoard)
def board(
    station_id: uuid.UUID,
    db: Db,
    principal: CanOperate,
    since: Annotated[datetime | None, Query()] = None,
) -> TicketBoard:
    return kitchen_service.board(db, principal, station_id, since)


@router.post("/tickets/{ticket_id}/status", response_model=TicketOut)
def set_status(ticket_id: uuid.UUID, payload: TicketStatusIn, db: Db, principal: CanOperate) -> TicketOut:
    return kitchen_service.set_status(db, principal, ticket_id, payload.status)


@router.post("/tickets/{ticket_id}/recall", response_model=TicketOut)
def recall(ticket_id: uuid.UUID, db: Db, principal: CanOperate) -> TicketOut:
    return kitchen_service.recall(db, principal, ticket_id)


@router.get("/orders/{order_id}/tickets", response_model=list[TicketOut])
def order_tickets(order_id: uuid.UUID, db: Db, principal: CanRead) -> list[TicketOut]:
    return kitchen_service.order_tickets(db, principal, order_id)
