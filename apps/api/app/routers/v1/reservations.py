import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.reservations import (
    AvailabilityOut,
    CancelReservation,
    CustomerPick,
    NoShowReservation,
    RejectReservation,
    ReleaseTable,
    ReservationCreate,
    ReservationOut,
    ReservationSettingsIn,
    ReservationSettingsOut,
    ReservationUpdate,
    SeatResult,
    TableHistoryOut,
    WalkInCreate,
)
from app.services import reservation_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Read = Annotated[
    Principal,
    Depends(authorize(Permission.RESERVATIONS_VIEW, allow_device=True, scopes=("portal", "pos"))),
]
Create = Annotated[
    Principal,
    Depends(authorize(Permission.RESERVATIONS_CREATE, allow_device=True, scopes=("portal", "pos"))),
]
Update = Annotated[
    Principal,
    Depends(authorize(Permission.RESERVATIONS_UPDATE, allow_device=False, scopes=("portal", "pos"))),
]
Confirm = Annotated[
    Principal,
    Depends(authorize(Permission.RESERVATIONS_CONFIRM, allow_device=False, scopes=("portal", "pos"))),
]
Cancel = Annotated[
    Principal,
    Depends(authorize(Permission.RESERVATIONS_CANCEL, allow_device=False, scopes=("portal", "pos"))),
]
Seat = Annotated[
    Principal,
    Depends(authorize(Permission.RESERVATIONS_SEAT, allow_device=True, scopes=("portal", "pos"))),
]
NoShow = Annotated[
    Principal,
    Depends(authorize(Permission.RESERVATIONS_MARK_NO_SHOW, allow_device=False, scopes=("portal", "pos"))),
]
TableHistory = Annotated[
    Principal,
    Depends(authorize(Permission.TABLE_HISTORY_VIEW, allow_device=False, scopes=("portal", "pos"))),
]
Settings = Annotated[
    Principal,
    Depends(authorize(Permission.RESERVATIONS_MANAGE_SETTINGS, allow_device=False, scopes=("portal",))),
]


def _override(principal: Principal) -> bool:
    return Permission.RESERVATIONS_UPDATE.value in principal.permissions


@router.get("", response_model=list[ReservationOut])
def list_reservations(
    store_id: uuid.UUID,
    db: Db,
    principal: Read,
    status: str | None = None,
    table_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    employee_id: uuid.UUID | None = None,
    area_id: uuid.UUID | None = None,
    starts_from: datetime | None = None,
    starts_to: datetime | None = None,
) -> list[ReservationOut]:
    return reservation_service.list_reservations(
        db,
        principal,
        store_id=store_id,
        status=status,
        table_id=table_id,
        customer_id=customer_id,
        employee_id=employee_id,
        area_id=area_id,
        starts_from=starts_from,
        starts_to=starts_to,
    )


@router.get("/availability", response_model=AvailabilityOut)
def availability(
    store_id: uuid.UUID,
    starts_at: datetime,
    db: Db,
    principal: Read,
    guest_count: int = Query(default=2, ge=1, le=200),
    duration_minutes: int | None = Query(default=None, ge=15, le=360),
) -> AvailabilityOut:
    return reservation_service.availability(
        db,
        principal,
        store_id=store_id,
        starts_at=starts_at,
        duration_minutes=duration_minutes,
        guest_count=guest_count,
    )


@router.get("/customers", response_model=list[CustomerPick])
def search_customers(store_id: uuid.UUID, q: str, db: Db, principal: Read) -> list[CustomerPick]:
    return reservation_service.search_customers(db, principal, store_id, q)


@router.get("/settings", response_model=ReservationSettingsOut)
def get_settings(store_id: uuid.UUID, db: Db, principal: Read) -> ReservationSettingsOut:
    return reservation_service.settings_out(db, principal, store_id)


@router.put("/settings", response_model=ReservationSettingsOut)
def save_settings(
    store_id: uuid.UUID, payload: ReservationSettingsIn, db: Db, principal: Settings
) -> ReservationSettingsOut:
    return reservation_service.save_settings(db, principal, store_id, payload)


@router.get("/tables/{table_id}/history", response_model=TableHistoryOut)
def table_history(
    table_id: uuid.UUID,
    db: Db,
    principal: TableHistory,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
) -> TableHistoryOut:
    return reservation_service.history(db, principal, table_id, start=start, end=end)


@router.post("/walk-ins", response_model=SeatResult, status_code=201)
def walk_in(payload: WalkInCreate, db: Db, principal: Seat) -> SeatResult:
    return reservation_service.walk_in(db, principal, payload)


@router.post("/tables/{table_id}/release", response_model=TableHistoryOut)
def release(table_id: uuid.UUID, payload: ReleaseTable, db: Db, principal: Seat) -> TableHistoryOut:
    return reservation_service.release(db, principal, table_id, payload)


@router.post("", response_model=ReservationOut, status_code=201)
def create_reservation(payload: ReservationCreate, db: Db, principal: Create) -> ReservationOut:
    return reservation_service.create_reservation(db, principal, payload, allow_override=_override(principal))


@router.get("/{reservation_id}", response_model=ReservationOut)
def get_reservation(reservation_id: uuid.UUID, db: Db, principal: Read) -> ReservationOut:
    result = reservation_service.get_reservation(db, principal, reservation_id)
    if principal.kind == "device" or Permission.RESERVATIONS_VIEW_HISTORY.value not in principal.permissions:
        return result.model_copy(update={"events": []})
    return result


@router.patch("/{reservation_id}", response_model=ReservationOut)
def update_reservation(
    reservation_id: uuid.UUID, payload: ReservationUpdate, db: Db, principal: Update
) -> ReservationOut:
    return reservation_service.update_reservation(
        db, principal, reservation_id, payload, allow_override=True
    )


@router.post("/{reservation_id}/confirm", response_model=ReservationOut)
def confirm(reservation_id: uuid.UUID, db: Db, principal: Confirm) -> ReservationOut:
    return reservation_service.confirm(db, principal, reservation_id)


@router.post("/{reservation_id}/arrive", response_model=ReservationOut)
def arrive(reservation_id: uuid.UUID, db: Db, principal: Seat) -> ReservationOut:
    return reservation_service.arrive(db, principal, reservation_id)


@router.post("/{reservation_id}/seat", response_model=SeatResult)
def seat(reservation_id: uuid.UUID, db: Db, principal: Seat) -> SeatResult:
    return reservation_service.seat(db, principal, reservation_id)


@router.post("/{reservation_id}/cancel", response_model=ReservationOut)
def cancel(reservation_id: uuid.UUID, payload: CancelReservation, db: Db, principal: Cancel) -> ReservationOut:
    return reservation_service.cancel(db, principal, reservation_id, payload)


@router.post("/{reservation_id}/no-show", response_model=ReservationOut)
def no_show(reservation_id: uuid.UUID, payload: NoShowReservation, db: Db, principal: NoShow) -> ReservationOut:
    return reservation_service.mark_no_show(db, principal, reservation_id, payload)


@router.post("/{reservation_id}/reject", response_model=ReservationOut)
def reject(reservation_id: uuid.UUID, payload: RejectReservation, db: Db, principal: Confirm) -> ReservationOut:
    return reservation_service.reject(db, principal, reservation_id, payload)
