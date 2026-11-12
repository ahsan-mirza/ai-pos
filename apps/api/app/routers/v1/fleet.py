import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.fleet import (
    AssignIn,
    ConfirmIn,
    DriverIn,
    DriverOut,
    DriverUpdate,
    FleetOrderRow,
    FleetView,
    PlanIn,
    PlanOut,
    PlanUpdate,
    PolicyOut,
    PolicyUpdate,
    ScheduleIn,
    SlotIn,
    VehicleIn,
    VehicleOut,
    VehicleUpdate,
    ZoneIn,
    ZoneOut,
    ZoneUpdate,
)
from app.schemas.sales_orders import SalesOrderOut
from app.services import fleet_service, sales_order_service

router = APIRouter()

Db = Annotated[Session, Depends(get_db)]
CanDispatch = Annotated[Principal, Depends(authorize(Permission.SALES_ORDERS, scopes=("portal", "pos")))]
CanPolicy = Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))]


@router.get("/policy", response_model=PolicyOut)
def read_policy(db: Db, principal: CanDispatch) -> PolicyOut:
    del principal
    return fleet_service.read_policy(db)


@router.put("/policy", response_model=PolicyOut)
def update_policy(payload: PolicyUpdate, db: Db, principal: CanPolicy) -> PolicyOut:
    return fleet_service.set_policy(db, principal, payload.policy)


@router.get("/orders", response_model=list[FleetOrderRow])
def list_orders(
    db: Db,
    principal: CanDispatch,
    view: FleetView,
    store_id: uuid.UUID | None = None,
    promised_on: date | None = None,
    zone_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[FleetOrderRow]:
    return fleet_service.list_board(
        db,
        principal,
        view=view,
        store_id=store_id,
        promised_on=promised_on,
        zone_id=zone_id,
        limit=limit,
    )


@router.post("/orders/{order_id}/schedule", response_model=SalesOrderOut)
def schedule_order(order_id: uuid.UUID, payload: ScheduleIn, db: Db, principal: CanDispatch) -> SalesOrderOut:
    order = fleet_service.schedule_order(db, principal, order_id, payload)
    return sales_order_service.order_out(db, order)


@router.post("/orders/{order_id}/cancel-schedule", response_model=SalesOrderOut)
def cancel_schedule(order_id: uuid.UUID, db: Db, principal: CanDispatch) -> SalesOrderOut:
    order = fleet_service.cancel_schedule(db, principal, order_id)
    return sales_order_service.order_out(db, order)


@router.get("/zones", response_model=list[ZoneOut])
def list_zones(db: Db, principal: CanDispatch, store_id: uuid.UUID | None = None) -> list[ZoneOut]:
    return fleet_service.list_zones(db, principal, store_id)


@router.post("/zones", response_model=ZoneOut, status_code=201)
def create_zone(payload: ZoneIn, db: Db, principal: CanDispatch) -> ZoneOut:
    return fleet_service.create_zone(db, principal, payload)


@router.patch("/zones/{zone_id}", response_model=ZoneOut)
def update_zone(zone_id: uuid.UUID, payload: ZoneUpdate, db: Db, principal: CanDispatch) -> ZoneOut:
    return fleet_service.update_zone(db, principal, zone_id, payload)


@router.post("/zones/{zone_id}/slots", response_model=ZoneOut, status_code=201)
def add_slot(zone_id: uuid.UUID, payload: SlotIn, db: Db, principal: CanDispatch) -> ZoneOut:
    return fleet_service.add_slot(db, principal, zone_id, payload)


@router.delete("/zones/{zone_id}/slots/{slot_id}", response_model=ZoneOut)
def delete_slot(zone_id: uuid.UUID, slot_id: uuid.UUID, db: Db, principal: CanDispatch) -> ZoneOut:
    return fleet_service.delete_slot(db, principal, zone_id, slot_id)


@router.get("/vehicles", response_model=list[VehicleOut])
def list_vehicles(db: Db, principal: CanDispatch, store_id: uuid.UUID | None = None) -> list[VehicleOut]:
    return fleet_service.list_vehicles(db, principal, store_id)


@router.post("/vehicles", response_model=VehicleOut, status_code=201)
def create_vehicle(payload: VehicleIn, db: Db, principal: CanDispatch) -> VehicleOut:
    return fleet_service.create_vehicle(db, principal, payload)


@router.patch("/vehicles/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(vehicle_id: uuid.UUID, payload: VehicleUpdate, db: Db, principal: CanDispatch) -> VehicleOut:
    return fleet_service.update_vehicle(db, principal, vehicle_id, payload)


@router.get("/drivers", response_model=list[DriverOut])
def list_drivers(db: Db, principal: CanDispatch, store_id: uuid.UUID | None = None) -> list[DriverOut]:
    return fleet_service.list_drivers(db, principal, store_id)


@router.post("/drivers", response_model=DriverOut, status_code=201)
def create_driver(payload: DriverIn, db: Db, principal: CanDispatch) -> DriverOut:
    return fleet_service.create_driver(db, principal, payload)


@router.patch("/drivers/{driver_id}", response_model=DriverOut)
def update_driver(driver_id: uuid.UUID, payload: DriverUpdate, db: Db, principal: CanDispatch) -> DriverOut:
    return fleet_service.update_driver(db, principal, driver_id, payload)


@router.get("/plans", response_model=list[PlanOut])
def list_plans(
    db: Db,
    principal: CanDispatch,
    store_id: uuid.UUID | None = None,
    service_date: date | None = None,
    status: str | None = Query(default=None, max_length=16),
) -> list[PlanOut]:
    return fleet_service.list_plans(db, principal, store_id=store_id, service_date=service_date, status=status)


@router.post("/plans", response_model=PlanOut, status_code=201)
def create_plan(payload: PlanIn, db: Db, principal: CanDispatch) -> PlanOut:
    return fleet_service.create_plan(db, principal, payload)


@router.get("/plans/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: uuid.UUID, db: Db, principal: CanDispatch) -> PlanOut:
    return fleet_service.get_plan(db, principal, plan_id)


@router.patch("/plans/{plan_id}", response_model=PlanOut)
def update_plan(plan_id: uuid.UUID, payload: PlanUpdate, db: Db, principal: CanDispatch) -> PlanOut:
    return fleet_service.update_plan(db, principal, plan_id, payload)


@router.post("/plans/{plan_id}/orders", response_model=PlanOut)
def add_order(plan_id: uuid.UUID, payload: AssignIn, db: Db, principal: CanDispatch) -> PlanOut:
    return fleet_service.add_order(db, principal, plan_id, payload)


@router.delete("/plans/{plan_id}/orders/{order_id}", response_model=PlanOut)
def remove_order(plan_id: uuid.UUID, order_id: uuid.UUID, db: Db, principal: CanDispatch) -> PlanOut:
    return fleet_service.remove_order(db, principal, plan_id, order_id)


@router.post("/plans/{plan_id}/confirm", response_model=PlanOut)
def confirm_plan(plan_id: uuid.UUID, payload: ConfirmIn, db: Db, principal: CanDispatch) -> PlanOut:
    return fleet_service.confirm_plan(db, principal, plan_id, payload)


@router.post("/plans/{plan_id}/cancel", response_model=PlanOut)
def cancel_plan(plan_id: uuid.UUID, db: Db, principal: CanDispatch) -> PlanOut:
    return fleet_service.cancel_plan(db, principal, plan_id)
