import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.payloads import ApiModel
from app.services import labels_service
from app.services.labels_service import Layout

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanPrint = Annotated[Principal, Depends(authorize(Permission.PORTAL_INVENTORY_MANAGE))]


class LabelLine(ApiModel):
    product_id: uuid.UUID
    copies: int = Field(default=1, ge=1, le=500)


class LabelRequest(ApiModel):
    items: list[LabelLine] = Field(min_length=1, max_length=500)
    layout: Layout = "a4_3x8"
    show_price: bool = True


def _pdf(body: bytes, name: str) -> Response:
    return Response(body, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}"'})


@router.post("", response_class=Response)
def print_labels(payload: LabelRequest, db: Db, _: CanPrint) -> Response:
    lines = [(line.product_id, line.copies) for line in payload.items]
    return _pdf(
        labels_service.for_products(db, lines, layout=payload.layout, show_price=payload.show_price), "labels.pdf"
    )


@router.get("/batches/{batch_id}", response_class=Response)
def batch_labels(
    batch_id: uuid.UUID, db: Db, _: CanPrint, layout: Layout = "a4_3x8", show_price: bool = True
) -> Response:
    return _pdf(labels_service.for_batch(db, batch_id, layout=layout, show_price=show_price), "batch-labels.pdf")


@router.get("/models/{model_id}", response_class=Response)
def model_labels(
    model_id: uuid.UUID, db: Db, _: CanPrint, layout: Layout = "a4_3x8", show_price: bool = True
) -> Response:
    return _pdf(labels_service.for_model(db, model_id, layout=layout, show_price=show_price), "variant-labels.pdf")
