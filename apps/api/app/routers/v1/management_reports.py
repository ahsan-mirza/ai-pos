import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.management import AgedStockReport, DiscountReport, PnlReport, StaffSalesReport, ValuationReport
from app.services import management_reports as reports

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanRead = Annotated[Principal, Depends(authorize(Permission.PORTAL_REPORTS_READ))]
From = Annotated[date, Query(alias="from")]
To = Annotated[date, Query(alias="to")]
SlowDays = Annotated[int, Query(ge=1, le=3650)]
CarryingRate = Annotated[int, Query(ge=0, le=100, description="Annual holding cost as % of stock cost")]


def _scope(principal: Principal, store_id: uuid.UUID | None) -> uuid.UUID | None:
    return principal.store_id or store_id


@router.get("/pnl", response_model=PnlReport)
def pnl(db: Db, principal: CanRead, start: From, end: To, store_id: uuid.UUID | None = None) -> PnlReport:
    return reports.pnl(db, start=start, end=end, store_id=_scope(principal, store_id))


@router.get("/valuation", response_model=ValuationReport)
def valuation(db: Db, principal: CanRead, store_id: uuid.UUID | None = None) -> ValuationReport:
    return reports.valuation(db, store_id=_scope(principal, store_id))


@router.get("/aged-stock", response_model=AgedStockReport)
def aged_stock(
    db: Db,
    principal: CanRead,
    store_id: uuid.UUID | None = None,
    slow_days: SlowDays = 60,
    dead_days: SlowDays = 180,
    carrying_rate_pct: CarryingRate = 25,
) -> AgedStockReport:
    return reports.aged_stock(
        db,
        store_id=_scope(principal, store_id),
        slow_days=slow_days,
        dead_days=dead_days,
        carrying_rate_bps=carrying_rate_pct * 100,
    )


@router.get("/staff", response_model=StaffSalesReport)
def staff(db: Db, principal: CanRead, start: From, end: To, store_id: uuid.UUID | None = None) -> StaffSalesReport:
    return reports.staff_sales(db, start=start, end=end, store_id=_scope(principal, store_id))


@router.get("/discounts", response_model=DiscountReport)
def discounts(db: Db, principal: CanRead, start: From, end: To, store_id: uuid.UUID | None = None) -> DiscountReport:
    return reports.discounts(db, start=start, end=end, store_id=_scope(principal, store_id))


@router.get("/{report}.csv", response_class=Response)
def export(
    report: Literal["pnl", "valuation", "aged-stock", "staff", "discounts"],
    db: Db,
    principal: CanRead,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
    store_id: uuid.UUID | None = None,
    slow_days: SlowDays = 60,
    dead_days: SlowDays = 180,
    carrying_rate_pct: CarryingRate = 25,
) -> Response:
    scope = _scope(principal, store_id)
    today = date.today()
    start, end = start or today.replace(day=1), end or today
    if report == "pnl":
        body = reports.pnl_csv(reports.pnl(db, start=start, end=end, store_id=scope))
    elif report == "valuation":
        body = reports.valuation_csv(reports.valuation(db, store_id=scope))
    elif report == "aged-stock":
        aged = reports.aged_stock(
            db, store_id=scope, slow_days=slow_days, dead_days=dead_days, carrying_rate_bps=carrying_rate_pct * 100
        )
        body = reports.aged_csv(aged)
    elif report == "discounts":
        body = reports.discounts_csv(reports.discounts(db, start=start, end=end, store_id=scope))
    else:
        body = reports.staff_csv(reports.staff_sales(db, start=start, end=end, store_id=scope))
    return Response(
        body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{report}-{start:%Y%m%d}-{end:%Y%m%d}.csv"'},
    )
