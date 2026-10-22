import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.exports import GlAccountOut, GlAccountsWrite
from app.schemas.loyalty import (
    LoyaltyAdjust,
    LoyaltyEntryOut,
    LoyaltySettingsOut,
    LoyaltySettingsWrite,
    LoyaltyStanding,
)
from app.services import export_service, loyalty_service
from app.services.settings_service import business_currency

router = APIRouter()
exports_router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
AtRegister = Annotated[
    Principal, Depends(authorize(Permission.POS_ACCESS, allow_device=True, scopes=("pos", "portal")))
]
CanCustomers = Annotated[Principal, Depends(authorize(Permission.CUSTOMERS_MANAGE))]
CanSettings = Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))]
CanReport = Annotated[Principal, Depends(authorize(Permission.REPORTS_VAT))]


@router.get("/settings", response_model=LoyaltySettingsOut)
def loyalty_settings(db: Db, _: AtRegister) -> LoyaltySettingsOut:
    return loyalty_service.settings(db)


@router.put("/settings", response_model=LoyaltySettingsOut)
def update_settings(payload: LoyaltySettingsWrite, db: Db, _: CanSettings) -> LoyaltySettingsOut:
    return loyalty_service.update_settings(db, payload)


@router.get("/customers/{customer_id}", response_model=list[LoyaltyEntryOut])
def ledger(customer_id: uuid.UUID, db: Db, _: CanCustomers) -> list[LoyaltyEntryOut]:
    return loyalty_service.ledger(db, customer_id)


@router.get("/customers/{customer_id}/standing", response_model=LoyaltyStanding)
def standing(customer_id: uuid.UUID, db: Db, _: CanCustomers) -> LoyaltyStanding:
    return loyalty_service.standing(db, customer_id)


@router.post("/customers/{customer_id}/adjust", response_model=list[LoyaltyEntryOut])
def adjust(customer_id: uuid.UUID, payload: LoyaltyAdjust, db: Db, principal: CanCustomers) -> list[LoyaltyEntryOut]:
    return loyalty_service.adjust(
        db, customer_id, payload.points, payload.note.strip(), principal.user.id if principal.user else None
    )


@exports_router.get("/gl.csv", response_class=Response)
def gl_csv(
    db: Db,
    principal: CanReport,
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
) -> Response:
    lines = export_service.journal(db, start, end, principal.store_id)
    return Response(
        export_service.journal_csv(lines, business_currency(db), export_service.chart_of_accounts(db)),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="journal-{start:%Y%m%d}-{end:%Y%m%d}.csv"'},
    )


@exports_router.get("/accounts", response_model=list[GlAccountOut])
def gl_accounts(db: Db, _: CanReport) -> list[GlAccountOut]:
    return export_service.account_rows(db)


@exports_router.put("/accounts", response_model=list[GlAccountOut])
def save_gl_accounts(payload: GlAccountsWrite, db: Db, _: CanSettings) -> list[GlAccountOut]:
    return export_service.save_accounts(db, payload)


@exports_router.get("/einvoices/{sale_id}.xml", response_class=Response)
def einvoice(sale_id: uuid.UUID, db: Db, principal: CanReport) -> Response:
    return Response(
        export_service.pint_ae_invoice(db, sale_id, principal.store_id),
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="invoice-{str(sale_id)[:8]}.xml"'},
    )


@exports_router.get("/einvoices.zip", response_class=Response)
def einvoices(
    db: Db,
    principal: CanReport,
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
) -> Response:
    return Response(
        export_service.pint_ae_zip(db, start, end, principal.store_id),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="pint-ae-{start:%Y%m%d}-{end:%Y%m%d}.zip"'},
    )
