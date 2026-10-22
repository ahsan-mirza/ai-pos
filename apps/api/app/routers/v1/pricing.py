import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.wholesale import BulkPriceResult, BulkPriceUpdate, PricingMatrix, PricingRow, ProductPricingWrite
from app.services import price_service

router = APIRouter()

Db = Annotated[Session, Depends(get_db)]
CanRead = Annotated[Principal, Depends(authorize(Permission.PORTAL_ACCESS))]
CanManage = Annotated[Principal, Depends(authorize(Permission.PORTAL_PRICING_MANAGE))]


@router.get("/matrix", response_model=PricingMatrix)
def pricing_matrix(
    db: Db,
    _: CanRead,
    category_id: uuid.UUID | None = None,
    brand: Annotated[str | None, Query(max_length=80)] = None,
    q: Annotated[str | None, Query(max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> PricingMatrix:
    return price_service.matrix(db, category_id=category_id, brand=brand, query=q, limit=limit)


@router.put("/products/{product_id}", response_model=PricingRow)
def update_product_pricing(product_id: uuid.UUID, payload: ProductPricingWrite, db: Db, _: CanManage) -> PricingRow:
    return price_service.update_product_pricing(db, product_id, payload)


@router.put("/bulk", response_model=BulkPriceResult)
def bulk_update(payload: BulkPriceUpdate, db: Db, _: CanManage) -> BulkPriceResult:
    return price_service.bulk_update(db, payload)
