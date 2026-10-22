from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.payloads import AnalyticsSummary
from app.services.analytics_service import build_summary
from app.services.settings_service import report_currency

router = APIRouter()
Timeframe = Literal["all_time", "weekly", "monthly"]


@router.get("/summary", response_model=AnalyticsSummary)
def analytics_summary(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(authorize(Permission.PORTAL_REPORTS_READ, allow_device=True))],
    timeframe: Annotated[Timeframe, Query()] = "all_time",
    currency: Annotated[str | None, Query(min_length=3, max_length=3)] = None,
) -> AnalyticsSummary:
    code = report_currency(db, currency)
    return build_summary(db, timeframe=timeframe, currency=code, store_scope=principal.store_id)
