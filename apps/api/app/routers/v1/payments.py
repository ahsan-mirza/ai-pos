import json
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, require_capability
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.schemas.payments import (
    BnplIntentCreate,
    CardIntentCreate,
    IntentCreate,
    IntentOut,
    PaymentList,
    PaymentsConfig,
    ProviderOut,
    RefundOut,
    SimulateOutcome,
    TerminalCheck,
    TerminalIn,
    TerminalOut,
    TerminalPatch,
)
from app.services import integrated_payment_service, payment_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
AtRegister = Annotated[
    Principal, Depends(authorize(Permission.POS_ACCESS, allow_device=True, scopes=("pos", "portal")))
]
Reports = Annotated[Principal, Depends(authorize(Permission.PORTAL_REPORTS_READ))]
Terminals = Annotated[Principal, Depends(authorize(Permission.DEVICES_MANAGE))]
Refunds = Annotated[Principal, Depends(authorize(Permission.POS_REFUND))]
CardsOn = Depends(require_capability(Capability.CARD_TERMINALS))
BnplOn = Depends(require_capability(Capability.BNPL))


@router.post("/intents", response_model=IntentOut, status_code=201)
def create_intent(payload: IntentCreate, db: Db, settings: Config, principal: AtRegister) -> IntentOut:
    return payment_service.create_intent(db, settings, payload, principal.store_id)


@router.get("/intents/{intent_id}", response_model=IntentOut)
def get_intent(intent_id: uuid.UUID, db: Db, settings: Config, principal: AtRegister) -> IntentOut:
    return payment_service.get_intent(db, intent_id, principal.store_id, settings)


@router.post("/intents/{intent_id}/cancel", response_model=IntentOut)
def cancel_intent(intent_id: uuid.UUID, db: Db, settings: Config, principal: AtRegister) -> IntentOut:
    return payment_service.cancel_intent(db, intent_id, principal.store_id, settings)


@router.post("/intents/{intent_id}/simulate", response_model=IntentOut)
def simulate_intent(
    intent_id: uuid.UUID, payload: SimulateOutcome, db: Db, settings: Config, principal: AtRegister
) -> IntentOut:
    """Simulated card terminal or pay-later provider: approve or decline from the till (never in live production)."""
    return integrated_payment_service.simulate(db, settings, intent_id, payload.outcome, principal.store_id)


@router.post("/card-intents", response_model=IntentOut, status_code=201, dependencies=[CardsOn])
def create_card_intent(payload: CardIntentCreate, db: Db, settings: Config, principal: AtRegister) -> IntentOut:
    """Push the amount to the store's card terminal; poll the intent until the terminal approves or declines."""
    return integrated_payment_service.create_card(db, settings, payload, principal)


@router.post("/bnpl-intents", response_model=IntentOut, status_code=201, dependencies=[BnplOn])
def create_bnpl_intent(payload: BnplIntentCreate, db: Db, settings: Config, principal: AtRegister) -> IntentOut:
    """Open a Tabby or Tamara checkout for the customer's phone; poll until it is captured or declined."""
    return integrated_payment_service.create_bnpl(db, settings, payload, principal)


@router.get("/config", response_model=PaymentsConfig)
def payments_config(
    db: Db, settings: Config, principal: AtRegister, store_id: uuid.UUID | None = None
) -> PaymentsConfig:
    return integrated_payment_service.config(
        db,
        settings,
        store_scope=principal.store_id,
        store_id=store_id,
        device_id=principal.device.id if principal.device is not None else None,
    )


@router.get("/providers", response_model=list[ProviderOut])
def list_providers(settings: Config, principal: Terminals) -> list[ProviderOut]:
    return integrated_payment_service.providers(settings)


@router.get("/list", response_model=PaymentList)
def list_payments(
    db: Db,
    principal: Reports,
    channel: Literal["QR", "CARD", "BNPL"] | None = None,
    status: Literal["PENDING", "AUTHORIZED", "PAID", "DECLINED", "EXPIRED", "CANCELLED"] | None = None,
    store_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaymentList:
    return integrated_payment_service.list_payments(
        db,
        channel=channel,
        status=status,
        store_id=store_id,
        store_scope=principal.store_id,
        limit=limit,
        offset=offset,
    )


@router.get("/refunds", response_model=list[RefundOut])
def list_refunds(
    db: Db, principal: Reports, status: Literal["PENDING", "SUCCEEDED", "FAILED"] | None = None
) -> list[RefundOut]:
    return integrated_payment_service.list_refunds(db, status=status, store_scope=principal.store_id)


@router.post("/refunds/{refund_id}/retry", response_model=RefundOut)
def retry_refund(refund_id: uuid.UUID, db: Db, settings: Config, principal: Refunds) -> RefundOut:
    return integrated_payment_service.retry_refund(db, settings, refund_id, principal.user)


@router.get("/terminals", response_model=list[TerminalOut])
def list_terminals(db: Db, principal: Terminals) -> list[TerminalOut]:
    return integrated_payment_service.list_terminals(db, principal.store_id)


@router.post("/terminals", response_model=TerminalOut, status_code=201, dependencies=[CardsOn])
def create_terminal(payload: TerminalIn, db: Db, principal: Terminals) -> TerminalOut:
    return integrated_payment_service.create_terminal(db, payload, principal.store_id, principal.user)


@router.patch("/terminals/{terminal_id}", response_model=TerminalOut)
def update_terminal(terminal_id: uuid.UUID, payload: TerminalPatch, db: Db, principal: Terminals) -> TerminalOut:
    return integrated_payment_service.update_terminal(db, terminal_id, payload, principal.store_id)


@router.post("/terminals/{terminal_id}/check", response_model=TerminalCheck)
def check_terminal(terminal_id: uuid.UUID, db: Db, settings: Config, principal: Terminals) -> TerminalCheck:
    return integrated_payment_service.check_terminal(db, settings, terminal_id, principal.store_id)


@router.get("/dev/{intent_id}/pay", response_model=IntentOut, operation_id="simulate_qr_payment_get")
@router.post("/dev/{intent_id}/pay", response_model=IntentOut, operation_id="simulate_qr_payment_post")
def simulate(intent_id: uuid.UUID, db: Db, settings: Config) -> IntentOut:
    """Dev provider only: scanning the QR opens this link, which plays the customer paying."""
    return payment_service.simulate_payment(db, settings, intent_id)


@router.post("/webhooks/{provider}", response_model=IntentOut)
async def webhook(
    provider: str,
    request: Request,
    db: Db,
    settings: Config,
    x_signature: Annotated[str | None, Header()] = None,
) -> IntentOut:
    body = await request.body()
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError as exc:
        raise ApiError(422, "invalid_request", "Webhook body is not JSON.") from exc
    if provider != settings.payment_provider:
        raise ApiError(404, "not_found", "Unknown payment provider.")
    return payment_service.handle_webhook(db, settings, body, x_signature, payload)
