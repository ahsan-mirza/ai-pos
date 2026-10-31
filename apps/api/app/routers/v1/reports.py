import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, require_capability
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.schemas.cancellations import CancellationReport
from app.schemas.shifts import TipReport
from app.schemas.size_curve import SizeCurveReport
from app.schemas.vat import VatReport
from app.services import cancellation_report, shift_service, size_curve_service, vat_report

router = APIRouter()
CanReadVat = Annotated[Principal, Depends(authorize(Permission.REPORTS_VAT))]
CanReadReports = Annotated[Principal, Depends(authorize(Permission.PORTAL_REPORTS_READ))]


def _scope(principal: Principal, store_id: uuid.UUID | None) -> uuid.UUID | None:
    return principal.store_id if principal.store_id is not None else store_id


@router.get("/vat", response_model=VatReport)
def vat(
    db: Annotated[Session, Depends(get_db)],
    principal: CanReadVat,
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
    store_id: uuid.UUID | None = None,
) -> VatReport:
    return vat_report.build(db, start=start, end=end, store_id=_scope(principal, store_id))


@router.get(
    "/tips",
    response_model=TipReport,
    dependencies=[Depends(require_capability(Capability.TIPS_SERVICE_CHARGE))],
)
def tips(
    db: Annotated[Session, Depends(get_db)],
    principal: CanReadReports,
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
    store_id: uuid.UUID | None = None,
) -> TipReport:
    return shift_service.tip_report(db, start=start, end=end, store_id=_scope(principal, store_id))


@router.get("/vat/export", response_class=Response)
def vat_export(
    db: Annotated[Session, Depends(get_db)],
    principal: CanReadVat,
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
    file_format: Annotated[Literal["csv", "pdf"], Query(alias="format")] = "csv",
    store_id: uuid.UUID | None = None,
) -> Response:
    report = vat_report.build(db, start=start, end=end, store_id=_scope(principal, store_id))
    name = f"vat-{start:%Y%m%d}-{end:%Y%m%d}.{file_format}"
    if file_format == "pdf":
        return Response(
            vat_report.to_pdf(report),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )
    return Response(
        vat_report.to_csv(report),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get(
    "/size-curve",
    response_model=SizeCurveReport,
    dependencies=[Depends(require_capability(Capability.VARIANTS_MATRIX))],
)
def size_curve(
    db: Annotated[Session, Depends(get_db)],
    principal: CanReadReports,
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
    model_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    season: Annotated[str | None, Query(max_length=16)] = None,
    store_id: uuid.UUID | None = None,
) -> SizeCurveReport:
    return size_curve_service.report(
        db,
        model_id=model_id,
        category_id=category_id,
        season=season,
        store_id=_scope(principal, store_id),
        start=start,
        end=end,
    )


@router.get("/cancellations", response_model=CancellationReport)
def cancellations(
    db: Annotated[Session, Depends(get_db)],
    principal: CanReadReports,
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
    store_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CancellationReport:
    """Orders cancelled in the window. The figures are not added to completed sales."""
    if end < start:
        raise ApiError(422, "invalid_range", "The end date is before the start date.")
    payload = cancellation_report.build(
        db,
        start=start,
        end=end,
        store_id=_scope(principal, store_id),
        limit=limit,
        offset=offset,
    )
    return CancellationReport.model_validate(payload)
