import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.core.security import decrypt_value
from app.models.serial_number import SerialNumber
from app.routers.v1.deps import assert_store_access
from app.schemas.payloads import ApiModel, SerialKind
from app.services import serial_service

router = APIRouter()


class RegisterSerial(ApiModel):
    id: uuid.UUID
    product_id: uuid.UUID
    kind: SerialKind
    value: str


@router.get("/register-serials", response_model=list[RegisterSerial])
def register_serials(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[
        Principal, Depends(authorize(Permission.POS_ACCESS, allow_device=True, scopes=("pos", "portal")))
    ],
    store_id: uuid.UUID,
    product_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=20_000)] = 5_000,
) -> list[RegisterSerial]:
    """In-stock units at one branch that no open quote holds, for bulk IMEI assignment at the register."""
    assert_store_access(principal, store_id)
    statement = (
        select(SerialNumber)
        .where(
            SerialNumber.store_id == store_id,
            SerialNumber.status == "in_stock",
            SerialNumber.id.not_in(serial_service.held_by_quotes()),
        )
        .order_by(SerialNumber.product_id, SerialNumber.created_at, SerialNumber.id)
        .limit(limit)
    )
    if product_id is not None:
        statement = statement.where(SerialNumber.product_id == product_id)
    return [
        RegisterSerial(
            id=row.id,
            product_id=row.product_id,
            kind=row.kind,  # type: ignore[arg-type]
            value=decrypt_value(row.value_encrypted, settings),
        )
        for row in db.scalars(statement).all()
    ]
