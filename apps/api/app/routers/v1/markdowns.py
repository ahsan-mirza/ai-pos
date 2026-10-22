from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.markdowns import MarkdownCreate, MarkdownEventOut, MarkdownPreview
from app.services import labels_service, markdown_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanManage = Annotated[Principal, Depends(authorize(Permission.PORTAL_INVENTORY_MANAGE))]


@router.get("", response_model=list[MarkdownEventOut])
def list_markdowns(db: Db, _: CanManage) -> list[MarkdownEventOut]:
    return markdown_service.list_events(db)


@router.post("/preview", response_model=MarkdownPreview)
def preview(data: MarkdownCreate, db: Db, _: CanManage) -> MarkdownPreview:
    return markdown_service.preview(db, data)


@router.post("", response_model=MarkdownEventOut)
def create(data: MarkdownCreate, db: Db, principal: CanManage) -> MarkdownEventOut:
    return markdown_service.create(db, data, principal.user.id if principal.user is not None else None)


@router.post("/{event_id}/end", response_model=MarkdownEventOut)
def end(event_id: UUID, db: Db, _: CanManage) -> MarkdownEventOut:
    return markdown_service.end_event(db, event_id)


@router.get("/{event_id}/labels.pdf")
def labels(
    event_id: UUID,
    db: Db,
    _: CanManage,
    layout: Annotated[str, Query()] = "a4_3x8",
) -> Response:
    if layout not in ("a4_3x8", "roll_50x30"):
        layout = "a4_3x8"
    ids = markdown_service.changed_product_ids(db, event_id)
    pdf = labels_service.for_products(db, [(product_id, 1) for product_id in ids], layout=layout, show_price=True)  # type: ignore[arg-type]
    return Response(content=pdf, media_type="application/pdf")
