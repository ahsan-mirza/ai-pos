import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.pagination import Offset, set_total
from app.core.permissions import Permission
from app.schemas.sales_orders import (
    BackorderRow,
    CancelLinesIn,
    ConfirmIn,
    DeliverIn,
    DeliveryNoteOut,
    DispatchIn,
    ReasonIn,
    SalesOrderCreate,
    SalesOrderOut,
    SalesOrderRow,
    SalesOrderUpdate,
)
from app.services import sales_order_pdf, sales_order_service

router = APIRouter()

Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
# Registers save a wholesale cart as an order (as the device, naming the cashier) and look orders up.
AtRegister = Annotated[
    Principal, Depends(authorize(Permission.SALES_ORDERS, allow_device=True, scopes=("portal", "pos")))
]
CanFulfil = Annotated[Principal, Depends(authorize(Permission.SALES_ORDERS, scopes=("portal", "pos")))]


def _pdf(name: str, content: bytes) -> Response:
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{name.lower()}.pdf"'},
    )


@router.post("", response_model=SalesOrderOut, status_code=201)
def create_order(payload: SalesOrderCreate, db: Db, principal: AtRegister) -> SalesOrderOut:
    return sales_order_service.create_order(db, principal, payload)


@router.get("", response_model=list[SalesOrderRow])
def list_orders(
    db: Db,
    principal: AtRegister,
    response: Response,
    offset: Offset,
    store_id: uuid.UUID | None = None,
    status: str | None = Query(default=None, max_length=24),
    customer_id: uuid.UUID | None = None,
    q: str | None = Query(default=None, max_length=80),
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[SalesOrderRow]:
    rows, total = sales_order_service.list_orders(
        db,
        principal,
        store_id=store_id,
        status=status,
        customer_id=customer_id,
        query=q,
        offset=offset,
        limit=limit,
    )
    set_total(response, total)
    return rows


@router.get("/backorders", response_model=list[BackorderRow])
def backorders(db: Db, principal: CanFulfil, store_id: uuid.UUID | None = None) -> list[BackorderRow]:
    return sales_order_service.backorders(db, principal, store_id)


@router.post("/from-quote/{quote_id}", response_model=SalesOrderOut, status_code=201)
def from_quote(quote_id: uuid.UUID, db: Db, principal: CanFulfil) -> SalesOrderOut:
    return sales_order_service.from_quote(db, principal, quote_id)


@router.get("/deliveries/{note_id}", response_model=DeliveryNoteOut)
def delivery(note_id: uuid.UUID, db: Db, principal: CanFulfil) -> DeliveryNoteOut:
    return sales_order_service.delivery(db, principal, note_id)


@router.post("/deliveries/{note_id}/deliver", response_model=DeliveryNoteOut)
def deliver(note_id: uuid.UUID, payload: DeliverIn, db: Db, principal: CanFulfil) -> DeliveryNoteOut:
    return sales_order_service.deliver(db, principal, note_id, payload)


@router.get("/deliveries/{note_id}/pdf", response_class=Response)
def delivery_pdf(note_id: uuid.UUID, db: Db, principal: CanFulfil) -> Response:
    return _pdf(*sales_order_pdf.render_delivery_note(db, principal, note_id))


@router.get("/pick-lists/{pick_id}/pdf", response_class=Response)
def pick_list_pdf(pick_id: uuid.UUID, db: Db, principal: CanFulfil) -> Response:
    return _pdf(*sales_order_pdf.render_pick_list(db, principal, pick_id))


@router.get("/{order_id}", response_model=SalesOrderOut)
def get_order(order_id: uuid.UUID, db: Db, principal: AtRegister) -> SalesOrderOut:
    return sales_order_service.get_order(db, principal, order_id)


@router.patch("/{order_id}", response_model=SalesOrderOut)
def update_order(order_id: uuid.UUID, payload: SalesOrderUpdate, db: Db, principal: CanFulfil) -> SalesOrderOut:
    return sales_order_service.update_order(db, principal, order_id, payload)


@router.get("/{order_id}/pdf", response_class=Response)
def order_pdf(order_id: uuid.UUID, db: Db, principal: CanFulfil) -> Response:
    return _pdf(*sales_order_pdf.render_order(db, principal, order_id))


@router.post("/{order_id}/confirm", response_model=SalesOrderOut)
def confirm(order_id: uuid.UUID, payload: ConfirmIn, db: Db, principal: CanFulfil) -> SalesOrderOut:
    return sales_order_service.confirm(db, principal, order_id, payload)


@router.post("/{order_id}/allocate", response_model=SalesOrderOut)
def allocate(order_id: uuid.UUID, db: Db, principal: CanFulfil) -> SalesOrderOut:
    return sales_order_service.allocate(db, principal, order_id)


@router.post("/{order_id}/pick", response_model=SalesOrderOut)
def pick(order_id: uuid.UUID, db: Db, principal: CanFulfil) -> SalesOrderOut:
    return sales_order_service.pick_list(db, principal, order_id)


@router.post("/{order_id}/dispatch", response_model=SalesOrderOut)
def dispatch(order_id: uuid.UUID, payload: DispatchIn, db: Db, settings: Config, principal: CanFulfil) -> SalesOrderOut:
    return sales_order_service.dispatch(db, settings, principal, order_id, payload)


@router.post("/{order_id}/cancel-lines", response_model=SalesOrderOut)
def cancel_lines(order_id: uuid.UUID, payload: CancelLinesIn, db: Db, principal: CanFulfil) -> SalesOrderOut:
    return sales_order_service.cancel_lines(db, principal, order_id, payload)


@router.post("/{order_id}/cancel", response_model=SalesOrderOut)
def cancel(order_id: uuid.UUID, payload: ReasonIn, db: Db, principal: CanFulfil) -> SalesOrderOut:
    return sales_order_service.cancel_order(db, principal, order_id, payload.reason)


@router.post("/{order_id}/close", response_model=SalesOrderOut)
def close(order_id: uuid.UUID, payload: ReasonIn, db: Db, principal: CanFulfil) -> SalesOrderOut:
    return sales_order_service.close_order(db, principal, order_id, payload.reason)
