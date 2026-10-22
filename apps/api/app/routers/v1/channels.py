import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.schemas.channels import (
    ChannelDecision,
    ChannelIn,
    ChannelOut,
    ChannelSecretOut,
    ManualChannelOrder,
    PayoutIn,
    PayoutOut,
    SettlementReport,
    WebhookResult,
)
from app.schemas.orders import OrderOut
from app.services import channel_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]
# Registers call these as the device on behalf of the signed-in cashier (user_id in the body).
CanOrder = Annotated[Principal, Depends(authorize(Permission.POS_ORDERS, allow_device=True, scopes=("portal", "pos")))]
CanManage = Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))]
CanReport = Annotated[Principal, Depends(authorize(Permission.PORTAL_REPORTS_READ))]


def _user(principal: Principal):
    if principal.user is None:
        raise ApiError(403, "forbidden", "This action requires a signed-in user.")
    return principal.user


@router.get("", response_model=list[ChannelOut])
def list_channels(db: Db, principal: CanOrder) -> list[ChannelOut]:
    return channel_service.list_channels(db, principal)


@router.post("", response_model=ChannelSecretOut, status_code=201)
def create_channel(payload: ChannelIn, db: Db, settings: AppSettings, principal: CanManage) -> ChannelSecretOut:
    return channel_service.create_channel(db, settings, _user(principal), payload)


@router.get("/settlement", response_model=SettlementReport)
def settlement(
    db: Db,
    principal: CanReport,
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
) -> SettlementReport:
    return channel_service.settlement(db, start=start, end=end)


@router.post("/manual-orders", response_model=OrderOut, status_code=201)
def manual_order(payload: ManualChannelOrder, db: Db, principal: CanOrder) -> OrderOut:
    return channel_service.manual_order(db, principal, payload)


@router.post("/orders/{order_id}/accept", response_model=OrderOut)
def accept(order_id: uuid.UUID, payload: ChannelDecision, db: Db, principal: CanOrder) -> OrderOut:
    return channel_service.accept(db, principal, order_id, payload)


@router.post("/orders/{order_id}/reject", response_model=OrderOut)
def reject(order_id: uuid.UUID, payload: ChannelDecision, db: Db, principal: CanOrder) -> OrderOut:
    return channel_service.reject(db, principal, order_id, payload)


@router.put("/{channel_id}", response_model=ChannelOut)
def update_channel(channel_id: uuid.UUID, payload: ChannelIn, db: Db, principal: CanManage) -> ChannelOut:
    return channel_service.update_channel(db, _user(principal), channel_id, payload)


@router.post("/{channel_id}/rotate-secret", response_model=ChannelSecretOut)
def rotate_secret(channel_id: uuid.UUID, db: Db, settings: AppSettings, principal: CanManage) -> ChannelSecretOut:
    return channel_service.rotate_secret(db, settings, _user(principal), channel_id)


@router.post("/{channel_id}/payouts", response_model=PayoutOut, status_code=201)
def record_payout(channel_id: uuid.UUID, payload: PayoutIn, db: Db, principal: CanManage) -> PayoutOut:
    return channel_service.record_payout(db, _user(principal), channel_id, payload)


@router.post("/{code}/orders", response_model=WebhookResult)
async def webhook(
    code: str,
    request: Request,
    db: Db,
    settings: AppSettings,
    signature: Annotated[str | None, Header(alias="X-Channel-Signature")] = None,
) -> WebhookResult:
    """Public: the delivery app posts the order body signed with HMAC-SHA256 of the channel's secret."""
    body = await request.body()
    return await run_in_threadpool(channel_service.receive_webhook, db, settings, code, body, signature)
