import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.uom import UnitCreate, UnitOut, UnitUpdate
from app.services import uom_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanRead = Annotated[Principal, Depends(authorize(allow_device=True, scopes=("pos", "portal")))]
CanManage = Annotated[Principal, Depends(authorize(Permission.PORTAL_INVENTORY_MANAGE))]


@router.get("", response_model=list[UnitOut])
def list_units(db: Db, _: CanRead) -> list[UnitOut]:
    """Built-in packs (piece, box of 10, carton of 100) and the business's own, smallest first."""
    return uom_service.list_units(db)


@router.post("", response_model=UnitOut, status_code=201)
def create_unit(payload: UnitCreate, db: Db, _: CanManage) -> UnitOut:
    return uom_service.create_unit(db, payload)


@router.patch("/{unit_id}", response_model=UnitOut)
def update_unit(unit_id: uuid.UUID, payload: UnitUpdate, db: Db, _: CanManage) -> UnitOut:
    """Rename a unit or switch it off. Its factor never changes once created."""
    return uom_service.update_unit(db, unit_id, payload)


@router.delete("/{unit_id}", status_code=204)
def delete_unit(unit_id: uuid.UUID, db: Db, _: CanManage) -> Response:
    uom_service.delete_unit(db, unit_id)
    return Response(status_code=204)
