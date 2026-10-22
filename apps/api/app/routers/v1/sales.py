import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.payloads import SaleOut
from app.services import catalog_service, invoice_pdf

router = APIRouter()

CanRead = Annotated[Principal, Depends(authorize(Permission.PORTAL_REPORTS_READ, allow_device=True))]


@router.get("", response_model=list[SaleOut])
def list_sales(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: CanRead,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[SaleOut]:
    return catalog_service.list_sales(db, settings, limit=limit, store_scope=principal.store_id)


@router.get("/{sale_id}/invoice.pdf", response_class=Response)
def sale_invoice_pdf(
    sale_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: CanRead,
) -> Response:
    content = invoice_pdf.render_sale_invoice(db, settings, sale_id, principal.store_id)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="invoice-{str(sale_id)[:8]}.pdf"'},
    )


@router.get("/{sale_id}/gift-receipt.pdf", response_class=Response)
def sale_gift_receipt_pdf(
    sale_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: CanRead,
) -> Response:
    content = invoice_pdf.render_gift_receipt(db, sale_id, principal.store_id)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="gift-receipt-{str(sale_id)[:8]}.pdf"'},
    )


@router.get("/{sale_id}", response_model=SaleOut)
def get_sale(
    sale_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: CanRead,
) -> SaleOut:
    return catalog_service.get_sale(db, settings, sale_id, store_scope=principal.store_id)
