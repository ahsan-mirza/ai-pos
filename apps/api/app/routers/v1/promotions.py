import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.promotions import CouponReportOut, PromotionOut, PromotionWrite
from app.services import coupon_service, promotion_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanManage = Annotated[Principal, Depends(authorize(Permission.PROMOTIONS_MANAGE))]
AtRegister = Annotated[
    Principal, Depends(authorize(Permission.POS_ACCESS, allow_device=True, scopes=("pos", "portal")))
]


@router.get("", response_model=list[PromotionOut])
def list_promotions(db: Db, _: CanManage) -> list[PromotionOut]:
    return promotion_service.list_promotions(db)


@router.get("/coupon-report", response_model=CouponReportOut)
def coupon_report(db: Db, _: CanManage) -> CouponReportOut:
    return CouponReportOut.model_validate(coupon_service.report(db))


@router.get("/active", response_model=list[PromotionOut])
def active(db: Db, principal: AtRegister, store_id: uuid.UUID | None = None) -> list[PromotionOut]:
    return promotion_service.for_register(db, principal.store_id or store_id)


@router.post("", response_model=PromotionOut, status_code=201)
def create(payload: PromotionWrite, db: Db, principal: CanManage) -> PromotionOut:
    return promotion_service.create(db, payload, principal.user.id if principal.user else None)


@router.put("/{promotion_id}", response_model=PromotionOut)
def update(promotion_id: uuid.UUID, payload: PromotionWrite, db: Db, _: CanManage) -> PromotionOut:
    return promotion_service.update(db, promotion_id, payload)
