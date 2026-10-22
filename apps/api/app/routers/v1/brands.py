import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, require_capability
from app.core.database import get_db
from app.routers.v1.categories import CanManage, CanRead
from app.schemas.inventory import (
    BrandOut,
    BrandWrite,
    CategoryUpdate,
    ProductModelOut,
    ProductModelUpdate,
    ProductModelWrite,
)
from app.schemas.variants import MatrixOut, MatrixWrite
from app.services import brand_service, variant_matrix_service
from app.services.settings_service import business_currency

router = APIRouter()
models_router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
MatrixModule = Depends(require_capability(Capability.VARIANTS_MATRIX))


@router.get("", response_model=list[BrandOut])
def list_brands(db: Db, _: CanRead, sub_category_id: uuid.UUID | None = None) -> list[BrandOut]:
    return brand_service.list_brands(db, sub_category_id=sub_category_id)


@router.post("", response_model=BrandOut, status_code=201)
def create_brand(payload: BrandWrite, db: Db, _: CanManage) -> BrandOut:
    return brand_service.create_brand(db, payload)


@router.patch("/{brand_id}", response_model=BrandOut)
def update_brand(brand_id: uuid.UUID, payload: CategoryUpdate, db: Db, _: CanManage) -> BrandOut:
    return brand_service.update_brand(db, brand_id, payload)


@router.delete("/{brand_id}", status_code=204)
def delete_brand(brand_id: uuid.UUID, db: Db, _: CanManage) -> Response:
    brand_service.delete_brand(db, brand_id)
    return Response(status_code=204)


@router.post("/{brand_id}/sub-categories/{sub_category_id}", response_model=BrandOut)
def link_sub_category(brand_id: uuid.UUID, sub_category_id: uuid.UUID, db: Db, _: CanManage) -> BrandOut:
    return brand_service.link_sub_category(db, brand_id, sub_category_id)


@router.delete("/{brand_id}/sub-categories/{sub_category_id}", response_model=BrandOut)
def unlink_sub_category(brand_id: uuid.UUID, sub_category_id: uuid.UUID, db: Db, _: CanManage) -> BrandOut:
    return brand_service.unlink_sub_category(db, brand_id, sub_category_id)


@models_router.get("", response_model=list[ProductModelOut])
def list_models(
    db: Db,
    _: CanRead,
    sub_category_id: uuid.UUID | None = None,
    brand_id: uuid.UUID | None = None,
) -> list[ProductModelOut]:
    return brand_service.list_models(db, sub_category_id=sub_category_id, brand_id=brand_id)


@models_router.post("", response_model=ProductModelOut, status_code=201)
def create_model(payload: ProductModelWrite, db: Db, _: CanManage) -> ProductModelOut:
    return brand_service.create_model(db, payload)


@models_router.patch("/{model_id}", response_model=ProductModelOut)
def update_model(model_id: uuid.UUID, payload: ProductModelUpdate, db: Db, _: CanManage) -> ProductModelOut:
    return brand_service.update_model(db, model_id, payload)


@models_router.get("/{model_id}/matrix", response_model=MatrixOut, dependencies=[MatrixModule])
def model_matrix(model_id: uuid.UUID, db: Db, _: CanRead, store_id: uuid.UUID | None = None) -> MatrixOut:
    """The model's variants as a size x colour grid, with stock per branch and units sold in 90 days."""
    return variant_matrix_service.matrix(db, model_id, store_id=store_id)


@models_router.post("/{model_id}/matrix", response_model=MatrixOut, dependencies=[MatrixModule])
def generate_matrix(model_id: uuid.UUID, payload: MatrixWrite, db: Db, _: CanManage) -> MatrixOut:
    """Creates a product for every combination the model does not have yet."""
    return variant_matrix_service.generate(db, model_id, payload, business_currency(db))


@models_router.delete("/{model_id}", status_code=204)
def delete_model(model_id: uuid.UUID, db: Db, _: CanManage) -> Response:
    brand_service.delete_model(db, model_id)
    return Response(status_code=204)
