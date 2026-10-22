from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.schemas.store_credit import GiftCardIssue, GiftCardProductOut, GiftCardVoid, StoreCreditList, StoreCreditOut
from app.services import gift_card_service, store_credit_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
AtRegister = Annotated[
    Principal, Depends(authorize(Permission.POS_ACCESS, allow_device=True, scopes=("pos", "portal")))
]
CanManage = Annotated[Principal, Depends(authorize(Permission.GIFT_CARDS_MANAGE))]


@router.get("/product", response_model=GiftCardProductOut)
def gift_card_product(db: Db, _: AtRegister) -> GiftCardProductOut:
    return gift_card_service.product_out(db)


@router.get("", response_model=StoreCreditList)
def list_cards(
    db: Db,
    principal: CanManage,
    open_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> StoreCreditList:
    return gift_card_service.list_cards(db, open_only=open_only, store_scope=principal.store_id, limit=limit)


@router.get("/{code}", response_model=StoreCreditOut)
def lookup(code: str, db: Db, _: AtRegister) -> StoreCreditOut:
    card = store_credit_service.lookup(db, code)
    if card.kind != "GIFT_CARD":
        raise ApiError(404, "not_found", "No gift card with that code.")
    return card


@router.post("/issue", response_model=list[StoreCreditOut], status_code=201)
def issue(payload: GiftCardIssue, db: Db, principal: CanManage) -> list[StoreCreditOut]:
    if principal.user is None:
        raise ApiError(403, "forbidden", "Sign in to issue gift cards.")
    return gift_card_service.issue(db, principal.user, payload)


@router.post("/{code}/void", response_model=StoreCreditOut)
def void(code: str, payload: GiftCardVoid, db: Db, principal: CanManage) -> StoreCreditOut:
    if principal.user is None:
        raise ApiError(403, "forbidden", "Sign in to void gift cards.")
    return gift_card_service.void(db, principal.user, code, payload.note)
