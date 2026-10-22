import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, get_principal
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.schemas.serials import SerialSearchOut, SerialStatus
from app.services import serial_service

router = APIRouter()


def _searcher(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
    """Registers, cashiers and portal users may search; what they see is decided per row."""
    if principal.kind == "device" or principal.has(Permission.POS_ACCESS) or principal.has(Permission.PORTAL_ACCESS):
        return principal
    raise ApiError(403, "forbidden", "Your role cannot look up serial numbers.")


@router.get("/search", response_model=SerialSearchOut)
def search(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(_searcher)],
    query: Annotated[str | None, Query(max_length=64)] = None,
    product_id: uuid.UUID | None = None,
    store_id: uuid.UUID | None = None,
    status: SerialStatus | Literal["any"] = "in_stock",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> SerialSearchOut:
    return serial_service.search(
        db,
        settings,
        principal,
        query=query,
        product_id=product_id,
        store_id=store_id,
        status=None if status == "any" else status,
        limit=limit,
    )
