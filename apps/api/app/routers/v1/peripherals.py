from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.payments import TerminalCheck
from app.schemas.peripherals import PeripheralSnapshot
from app.services import peripheral_status

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
CanView = Annotated[
    Principal, Depends(authorize(Permission.POS_ACCESS, allow_device=True, scopes=("pos", "portal")))
]


@router.get("", response_model=PeripheralSnapshot)
def peripheral_snapshot(db: Db, principal: CanView) -> PeripheralSnapshot:
    """Companion apps and the branch card terminal. The branch is the caller's, never a query parameter."""
    return peripheral_status.snapshot(db, principal)


@router.post("/card-terminal/check", response_model=TerminalCheck)
def check_card_terminal(db: Db, settings: Config, principal: CanView) -> TerminalCheck:
    return peripheral_status.check_card(db, settings, principal)
