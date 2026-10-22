import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.errors import ApiError
from app.core.pagination import Offset, set_total
from app.core.permissions import Permission
from app.schemas.batches import (
    BatchDetail,
    BatchPage,
    BatchStatus,
    BatchUpdate,
    CommitRequest,
    PreviewOut,
    PreviewRequest,
    RollbackPreview,
    RollbackRequest,
    RollbackResult,
    SupplierCreate,
    SupplierOut,
    TemplateOut,
    TemplateWrite,
    UploadOut,
)
from app.services import import_batch_service as service
from app.services.import_parser import MAX_FILE_BYTES

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
CanImport = Annotated[Principal, Depends(authorize(Permission.PORTAL_INVENTORY_MANAGE))]
CanCorrect = Annotated[Principal, Depends(authorize(Permission.INVENTORY_ADJUST_STOCK))]


# --- Import wizard -------------------------------------------------------------------------------


@router.post("/import/upload", response_model=UploadOut)
async def upload(principal: CanImport, file: Annotated[UploadFile, File()]) -> UploadOut:
    data = await file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ApiError(413, "file_too_large", "Purchase files are limited to 10 MB.")
    return service.upload(principal, file.filename or "purchases", data)


@router.post("/import/preview", response_model=PreviewOut)
def preview(db: Db, principal: CanImport, data: PreviewRequest) -> PreviewOut:
    return service.preview(db, principal, data)


@router.post("/import/commit", response_model=BatchDetail, status_code=201)
def commit(db: Db, settings: Config, principal: CanImport, data: CommitRequest) -> BatchDetail:
    return service.commit(db, settings, principal, data)


@router.get("/import/templates", response_model=list[TemplateOut])
def templates(db: Db, _: CanImport, supplier_id: uuid.UUID | None = None) -> list[TemplateOut]:
    return service.list_templates(db, supplier_id)


@router.post("/import/templates", response_model=TemplateOut)
def save_template(db: Db, principal: CanImport, data: TemplateWrite) -> TemplateOut:
    return service.save_template(db, principal, data)


@router.delete("/import/templates/{template_id}", status_code=204)
def delete_template(db: Db, _: CanImport, template_id: uuid.UUID) -> Response:
    service.delete_template(db, template_id)
    return Response(status_code=204)


# --- Suppliers -----------------------------------------------------------------------------------


@router.get("/suppliers", response_model=list[SupplierOut])
def suppliers(db: Db, _: CanImport) -> list[SupplierOut]:
    return service.list_suppliers(db)


@router.post("/suppliers", response_model=SupplierOut, status_code=201)
def create_supplier(db: Db, _: CanImport, data: SupplierCreate) -> SupplierOut:
    return service.create_supplier(db, data)


# --- Batch hub -----------------------------------------------------------------------------------


@router.get("/batches", response_model=BatchPage)
def batches(
    db: Db,
    principal: CanImport,
    response: Response,
    offset: Offset,
    store_id: uuid.UUID | None = None,
    status: BatchStatus | None = None,
    supplier_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> BatchPage:
    page = service.list_batches(
        db, principal, store_id=store_id, status=status, supplier_id=supplier_id, query=q, offset=offset, limit=limit
    )
    set_total(response, page.total)
    return page


@router.get("/batches/{batch_id}", response_model=BatchDetail)
def batch(db: Db, settings: Config, principal: CanImport, batch_id: uuid.UUID) -> BatchDetail:
    return service.get_batch(db, settings, principal, batch_id)


@router.get("/batches/{batch_id}/file")
def batch_file(db: Db, principal: CanImport, batch_id: uuid.UUID) -> FileResponse:
    path, name = service.batch_file(db, principal, batch_id)
    return FileResponse(path, filename=name)


@router.patch("/batches/{batch_id}", response_model=BatchDetail)
def update_batch(
    db: Db, settings: Config, principal: CanCorrect, batch_id: uuid.UUID, data: BatchUpdate
) -> BatchDetail:
    return service.update_batch(db, settings, principal, batch_id, data)


@router.get("/batches/{batch_id}/rollback-preview", response_model=RollbackPreview)
def rollback_preview(db: Db, principal: CanCorrect, batch_id: uuid.UUID) -> RollbackPreview:
    return service.rollback_preview(db, principal, batch_id)


@router.post("/batches/{batch_id}/rollback", response_model=RollbackResult)
def rollback(
    db: Db, settings: Config, principal: CanCorrect, batch_id: uuid.UUID, data: RollbackRequest
) -> RollbackResult:
    return service.rollback(db, settings, principal, batch_id, data)
