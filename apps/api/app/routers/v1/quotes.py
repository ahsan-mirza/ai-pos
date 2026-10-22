import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.errors import ApiError
from app.core.pagination import Offset, set_total
from app.core.permissions import Permission
from app.routers.v1.deps import assert_store_access
from app.schemas.payloads import QuoteStatus
from app.schemas.wholesale import QuoteConvert, QuoteList, QuoteOut, QuotePayload, QuotePaymentIn
from app.services import quote_service

router = APIRouter()

Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
AtRegister = Annotated[
    Principal,
    Depends(authorize(Permission.POS_ACCESS, allow_device=True, scopes=("pos", "portal"))),
]
CanRead = Annotated[
    Principal,
    Depends(authorize(Permission.PORTAL_REPORTS_READ, allow_device=True, scopes=("portal", "pos"))),
]
CanManage = Annotated[Principal, Depends(authorize(Permission.CUSTOMERS_MANAGE))]


@router.post("", response_model=QuoteOut, status_code=201)
def create_quote(payload: QuotePayload, db: Db, settings: Config, principal: AtRegister) -> QuoteOut:
    """Saves a proforma quote and holds its stock. Needs a live connection, unlike sales."""
    if principal.user is not None and principal.user.id != payload.cashier_id:
        raise ApiError(403, "forbidden", "Quotes must be attributed to the signed-in cashier.")
    assert_store_access(principal, payload.store_id)
    return quote_service.create_quote(db, settings, payload)


@router.get("", response_model=QuoteList)
def list_quotes(
    db: Db,
    settings: Config,
    principal: CanRead,
    response: Response,
    offset: Offset,
    status: QuoteStatus | None = None,
    customer_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> QuoteList:
    result = quote_service.list_quotes(
        db,
        settings,
        status=status,
        customer_id=customer_id,
        store_scope=principal.store_id,
        limit=limit,
        offset=offset,
    )
    set_total(response, result.total)
    return result


@router.get("/{quote_id}", response_model=QuoteOut)
def get_quote(quote_id: uuid.UUID, db: Db, settings: Config, principal: CanRead) -> QuoteOut:
    return quote_service.quote_detail(db, settings, quote_id, principal.store_id)


@router.get("/{quote_id}/pdf", response_class=Response)
def quote_pdf(quote_id: uuid.UUID, db: Db, settings: Config, principal: CanRead) -> Response:
    content = quote_service.render_quote_pdf(db, settings, quote_id, principal.store_id)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="quote-{str(quote_id)[:8]}.pdf"'},
    )


@router.post("/{quote_id}/convert", response_model=QuoteOut)
def convert_quote(
    quote_id: uuid.UUID, payload: QuoteConvert, db: Db, settings: Config, principal: CanManage
) -> QuoteOut:
    assert principal.user is not None
    return quote_service.convert_quote(
        db, settings, quote_id, payload, cashier_id=principal.user.id, store_scope=principal.store_id
    )


@router.post("/{quote_id}/payments", response_model=QuoteOut)
def add_payment(
    quote_id: uuid.UUID, payload: QuotePaymentIn, db: Db, settings: Config, principal: AtRegister
) -> QuoteOut:
    """Takes a deposit against a layaway."""
    if principal.user is not None:
        if payload.cashier_id is not None and payload.cashier_id != principal.user.id:
            raise ApiError(403, "forbidden", "Deposits are recorded against the signed-in cashier.")
        received_by = principal.user.id
    else:
        if payload.cashier_id is None:
            raise ApiError(422, "validation_error", "Name the cashier taking the deposit.")
        received_by = payload.cashier_id
    return quote_service.add_payment(
        db, settings, quote_id, payload, received_by_id=received_by, store_scope=principal.store_id
    )


@router.post("/{quote_id}/cancel", response_model=QuoteOut)
def cancel_quote(quote_id: uuid.UUID, db: Db, settings: Config, principal: CanManage) -> QuoteOut:
    return quote_service.cancel_quote(db, settings, quote_id, principal.store_id)
