from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize, require_api_key
from app.core.errors import ApiError
from app.core.pagination import Offset, set_total
from app.core.permissions import Permission
from app.schemas.audit import (
    AuditFacets,
    AuditLogDetail,
    AuditLogPage,
    AuditSummary,
    DesktopAuditBatch,
    DesktopAuditResult,
)
from app.services import audit_query
from app.services.audit_query import AuditFilters

router = APIRouter()

Reader = Annotated[Principal, Depends(authorize(Permission.AUDIT_READ))]
Db = Annotated[Session, Depends(get_db)]


def _filters(
    occurred_from: Annotated[datetime | None, Query(alias="from")] = None,
    occurred_to: Annotated[datetime | None, Query(alias="to")] = None,
    user_id: UUID | None = None,
    store_id: UUID | None = None,
    action_type: Annotated[list[str] | None, Query()] = None,
    target_entity: Annotated[str | None, Query(max_length=40)] = None,
    q: Annotated[str | None, Query(max_length=80)] = None,
    sensitive_only: bool = False,
) -> AuditFilters:
    if occurred_from is not None and occurred_to is not None and occurred_to <= occurred_from:
        raise ApiError(422, "invalid_request", "The end of the date range must be after its start.")
    return AuditFilters(
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        user_id=user_id,
        store_id=store_id,
        action_types=tuple(sorted({value.strip().upper() for value in action_type or [] if value.strip()})),
        target_entity=target_entity or None,
        query=(q or "").strip() or None,
        sensitive_only=sensitive_only,
    )


Filters = Annotated[AuditFilters, Depends(_filters)]


@router.get("", response_model=AuditLogPage)
def list_audit_logs(
    db: Db,
    principal: Reader,
    filters: Filters,
    response: Response,
    offset: Offset,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditLogPage:
    page = audit_query.list_logs(db, principal, filters, limit=limit, offset=offset)
    set_total(response, page.total)
    return page


@router.get("/summary", response_model=AuditSummary)
def audit_summary(
    db: Db,
    principal: Reader,
    settings: Annotated[Settings, Depends(get_settings)],
    since: datetime | None = None,
) -> AuditSummary:
    return audit_query.summary(db, settings, principal, since=since)


@router.get("/facets", response_model=AuditFacets)
def audit_facets(db: Db, principal: Reader) -> AuditFacets:
    return audit_query.facets(db, principal)


@router.get("/export")
def export_audit_logs(
    db: Db,
    principal: Reader,
    filters: Filters,
    format: Literal["csv", "json", "pdf"] = "csv",
) -> Response:
    body, media_type, _ = audit_query.export(db, principal, filters, file_format=format)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return Response(
        content=body,
        media_type=media_type if format == "pdf" else f"{media_type}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="audit-trail-{stamp}.{format}"'},
    )


@router.post("/sync", response_model=DesktopAuditResult)
def sync_desktop_audit(
    batch: DesktopAuditBatch,
    db: Db,
    _: Annotated[None, Depends(require_api_key)],
) -> DesktopAuditResult:
    return audit_query.ingest_desktop(db, batch)


@router.get("/{log_id}", response_model=AuditLogDetail)
def read_audit_log(log_id: UUID, db: Db, principal: Reader) -> AuditLogDetail:
    return audit_query.get_log(db, principal, log_id)
