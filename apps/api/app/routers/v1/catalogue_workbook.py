"""Excel import and export for the shared product and menu catalogue."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import REGISTER_SCOPES, Principal, authorize
from app.core.permissions import Permission
from app.routers.v1.deps import require_idempotency_key
from app.services import catalogue_workbook, catalogue_xlsx

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanManage = Annotated[Principal, Depends(authorize(Permission.PORTAL_INVENTORY_MANAGE, scopes=REGISTER_SCOPES))]
Workbook = Annotated[UploadFile, File()]
MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _file(payload: bytes, filename: str) -> Response:
    return Response(
        content=payload,
        media_type=MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/catalogue/workbook/template")
def template(_: CanManage) -> Response:
    return _file(catalogue_workbook.template_bytes(), catalogue_xlsx.TEMPLATE_NAME)


@router.get("/catalogue/workbook/export")
def export_workbook(
    db: Db,
    principal: CanManage,
    q: Annotated[str | None, Query(max_length=80)] = None,
    id: Annotated[list[uuid.UUID] | None, Query()] = None,
) -> Response:
    payload, filename, _count = catalogue_workbook.export_workbook(
        db, principal, query=q, ids=set(id) if id else None
    )
    return _file(payload, filename)


@router.post("/catalogue/workbook/preview")
async def preview(
    db: Db,
    _: CanManage,
    file: Workbook,
    mode: Annotated[str, Form()],
) -> dict[str, object]:
    data = await file.read(catalogue_xlsx.MAX_FILE_BYTES + 1)
    return catalogue_workbook.preview(db, data, file.filename or "workbook.xlsx", mode)


@router.post("/catalogue/workbook/commit")
async def commit(
    db: Db,
    principal: CanManage,
    file: Workbook,
    mode: Annotated[str, Form()],
    job_id: Annotated[str, Form()],
    confirm: Annotated[bool, Form()],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> Response:
    data = await file.read(catalogue_xlsx.MAX_FILE_BYTES + 1)
    report = catalogue_workbook.commit_workbook(
        db,
        principal,
        data,
        file.filename or "workbook.xlsx",
        mode,
        job_id=job_id,
        confirm=confirm,
        idempotency_key=idempotency_key,
    )
    status = 200 if report.get("committed") else 422
    return JSONResponse(status_code=status, content=report)


@router.post("/catalogue/workbook/error-report")
async def error_report(
    db: Db,
    _: CanManage,
    file: Workbook,
    mode: Annotated[str, Form()],
) -> Response:
    data = await file.read(catalogue_xlsx.MAX_FILE_BYTES + 1)
    payload = catalogue_workbook.error_report(db, data, file.filename or "workbook.xlsx", mode)
    return _file(payload, "AxizPOS_Product_Menu_Errors.xlsx")
