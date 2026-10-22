import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.einvoices import EInvoiceList, EInvoiceOut, EInvoiceStatus, EInvoiceSummary
from app.services import einvoice_service

router = APIRouter()
CanRead = Annotated[Principal, Depends(authorize(Permission.REPORTS_VAT))]


@router.get("/summary", response_model=EInvoiceSummary)
def summary(db: Annotated[Session, Depends(get_db)], principal: CanRead) -> EInvoiceSummary:
    return einvoice_service.summary(db, principal.store_id)


@router.get("", response_model=EInvoiceList)
def list_einvoices(
    db: Annotated[Session, Depends(get_db)],
    principal: CanRead,
    status: EInvoiceStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EInvoiceList:
    return einvoice_service.list_einvoices(
        db, status=status, store_scope=principal.store_id, limit=limit, offset=offset
    )


@router.get("/{einvoice_id}", response_model=EInvoiceOut)
def get_einvoice(einvoice_id: uuid.UUID, db: Annotated[Session, Depends(get_db)], principal: CanRead) -> EInvoiceOut:
    return einvoice_service.out(einvoice_service.get(db, einvoice_id, principal.store_id))


@router.get("/{einvoice_id}/xml", response_class=Response)
def einvoice_xml(einvoice_id: uuid.UUID, db: Annotated[Session, Depends(get_db)], principal: CanRead) -> Response:
    record = einvoice_service.get(db, einvoice_id, principal.store_id)
    return Response(
        content=record.xml,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{record.number}.xml"'},
    )
