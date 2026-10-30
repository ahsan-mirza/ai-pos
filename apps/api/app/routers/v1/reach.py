from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.reach import (
    CampaignOut,
    CampaignWrite,
    ChannelOut,
    ChannelWrite,
    OverviewOut,
    PreviewOut,
    PricesWrite,
)
from app.services import reach_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
CanManage = Annotated[Principal, Depends(authorize(Permission.MESSAGING_MANAGE))]


@router.get("/channels", response_model=list[ChannelOut])
def channels(db: Db, settings: Config, _: CanManage) -> list[dict]:
    return reach_service.list_channels(db, settings)


@router.put("/channels", response_model=ChannelOut)
def save_channel(payload: ChannelWrite, db: Db, settings: Config, _: CanManage) -> dict:
    return reach_service.save_channel(db, settings, payload.model_dump())


@router.post("/channels/{channel}/test", response_model=ChannelOut)
def test_channel(channel: str, db: Db, settings: Config, _: CanManage) -> dict:
    return reach_service.test_channel(db, settings, channel)


@router.get("/overview", response_model=OverviewOut)
def overview(db: Db, _: CanManage) -> dict:
    return reach_service.overview(db)


@router.put("/prices")
def prices(payload: PricesWrite, db: Db, _: CanManage) -> dict[str, int]:
    reach_service.require_reach(db)
    return reach_service.save_prices(db, payload.model_dump())


@router.post("/campaigns/preview", response_model=PreviewOut)
def preview(payload: CampaignWrite, db: Db, _: CanManage) -> dict:
    return reach_service.preview(db, payload.model_dump())


@router.post("/campaigns", response_model=CampaignOut, status_code=201)
def launch(payload: CampaignWrite, db: Db, principal: CanManage) -> object:
    return reach_service.launch(db, principal.user.id, payload.model_dump())


@router.post("/campaigns/{campaign_id}/cancel", response_model=CampaignOut)
def cancel(campaign_id: UUID, db: Db, _: CanManage) -> object:
    return reach_service.cancel(db, campaign_id)
