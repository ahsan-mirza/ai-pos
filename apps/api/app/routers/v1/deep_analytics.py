"""Deep Analytics. The business module and the reports permission both have to allow the caller."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.cache import get_value, set_value
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.schemas.deep_analytics import DeepOverview
from app.services import audit, deep_analytics
from app.services.settings_service import report_currency
from app.tenancy.scoping import active_tenant_id

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Reader = Annotated[Principal, Depends(authorize(Permission.PORTAL_REPORTS_READ))]
From = Annotated[date, Query(alias="from")]
To = Annotated[date, Query(alias="to")]
CACHE_SECONDS = 60


def scoped_store(principal: Principal, store_id: uuid.UUID | None) -> uuid.UUID | None:
    home = principal.store_id
    if home is not None and store_id is not None and store_id != home:
        raise ApiError(403, "store_forbidden", "This account can only read its own branch.")
    return home or store_id


def _cache_key(store_id: uuid.UUID | None, start: date, end: date, currency: str, compare: bool) -> str:
    branch = store_id.hex if store_id else "all"
    tenant = active_tenant_id()
    window = f"{start.isoformat()}:{end.isoformat()}:{currency}:{int(compare)}"
    return f"tenant:{tenant}:deep:{branch}:{window}:v2"


def _report(
    db: Session,
    principal: Principal,
    start: date,
    end: date,
    store_id: uuid.UUID | None,
    currency: str | None,
    compare: bool,
) -> DeepOverview:
    branch = scoped_store(principal, store_id)
    code = report_currency(db, currency)
    key = _cache_key(branch, start, end, code, compare)
    cached = get_value(key)
    if cached:
        return DeepOverview.model_validate_json(cached)
    report = deep_analytics.overview(db, start=start, end=end, store_id=branch, currency=code, compare=compare)
    set_value(key, report.model_dump_json(), CACHE_SECONDS)
    return report


@router.get("/overview", response_model=DeepOverview)
def overview(
    db: Db,
    principal: Reader,
    start: From,
    end: To,
    store_id: uuid.UUID | None = None,
    currency: Annotated[str | None, Query(min_length=3, max_length=3)] = None,
    compare: Annotated[bool, Query()] = False,
) -> DeepOverview:
    return _report(db, principal, start, end, store_id, currency, compare)


@router.get("/export")
def export_csv(
    db: Db,
    principal: Reader,
    start: From,
    end: To,
    store_id: uuid.UUID | None = None,
    currency: Annotated[str | None, Query(min_length=3, max_length=3)] = None,
    compare: Annotated[bool, Query()] = False,
) -> Response:
    report = _report(db, principal, start, end, store_id, currency, compare)
    branch = scoped_store(principal, store_id)
    audit.log_export(
        db,
        dataset="deep_analytics",
        row_count=len(report.trend),
        filters={"from": start.isoformat(), "to": end.isoformat(), "store_id": str(branch or "")},
        file_format="csv",
    )
    db.commit()
    body = deep_analytics.export_csv(report)
    return Response(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=deep-analytics.csv"},
    )
