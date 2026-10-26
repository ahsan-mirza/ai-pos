import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.orders import GuestSuggestionsOut
from app.services import grocery_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanSell = Annotated[Principal, Depends(authorize(Permission.POS_ACCESS, allow_device=True, scopes=("portal", "pos")))]


@router.get("/suggestions", response_model=GuestSuggestionsOut)
def suggestions(
    db: Db,
    principal: CanSell,
    store_id: uuid.UUID,
    product_id: Annotated[list[uuid.UUID] | None, Query(max_length=50)] = None,
) -> GuestSuggestionsOut:
    """Up to three products bought with this basket. Grocery only; the cashier still adds the line."""
    return grocery_service.suggestions(db, principal, store_id=store_id, product_ids=product_id or [])
