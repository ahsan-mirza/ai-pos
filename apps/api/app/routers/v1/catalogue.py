"""Product photos and fashion attribute pickers."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.catalogue import CatalogAttributesOut, ProductImageOut, ProductImageUpdate
from app.services import fashion_attributes, product_image_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanRead = Annotated[Principal, Depends(authorize(Permission.POS_ACCESS, allow_device=True, scopes=("pos", "portal")))]
CanManage = Annotated[Principal, Depends(authorize(Permission.PORTAL_INVENTORY_MANAGE))]
Photo = Annotated[UploadFile, File()]
AttributeKey = Annotated[str | None, Form(max_length=32)]
AttributeValue = Annotated[str | None, Form(max_length=64)]


@router.get("/catalog/attributes", response_model=CatalogAttributesOut)
def attributes(db: Db, _: CanRead) -> CatalogAttributesOut:
    return fashion_attributes.catalog_attributes(db)


@router.get("/inventory/products/{product_id}/images", response_model=list[ProductImageOut])
def product_images(product_id: uuid.UUID, db: Db, _: CanRead) -> list[ProductImageOut]:
    return product_image_service.list_images(db, product_id=product_id)


@router.post("/inventory/products/{product_id}/images", response_model=ProductImageOut, status_code=201)
async def upload_product_image(product_id: uuid.UUID, db: Db, principal: CanManage, file: Photo) -> ProductImageOut:
    data = await file.read(product_image_service.MAX_BYTES + 1)
    return product_image_service.upload(db, principal.user, data, file.content_type, product_id=product_id)


@router.get("/product-models/{model_id}/images", response_model=list[ProductImageOut])
def model_images(model_id: uuid.UUID, db: Db, _: CanRead) -> list[ProductImageOut]:
    return product_image_service.list_images(db, model_id=model_id)


@router.post("/product-models/{model_id}/images", response_model=ProductImageOut, status_code=201)
async def upload_model_image(
    model_id: uuid.UUID,
    db: Db,
    principal: CanManage,
    file: Photo,
    attribute_key: AttributeKey = None,
    attribute_value: AttributeValue = None,
) -> ProductImageOut:
    data = await file.read(product_image_service.MAX_BYTES + 1)
    return product_image_service.upload(
        db,
        principal.user,
        data,
        file.content_type,
        model_id=model_id,
        attribute_key=attribute_key,
        attribute_value=attribute_value,
    )


@router.patch("/inventory/images/{image_id}", response_model=ProductImageOut)
def update_image(image_id: uuid.UUID, payload: ProductImageUpdate, db: Db, _: CanManage) -> ProductImageOut:
    return product_image_service.update(db, image_id, payload)


@router.delete("/inventory/images/{image_id}", status_code=204)
def delete_image(image_id: uuid.UUID, db: Db, _: CanManage) -> Response:
    product_image_service.delete(db, image_id)
    return Response(status_code=204)
