import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.schemas.assistant import (
    AssistantAsk,
    AssistantConversation,
    AssistantHealth,
    AssistantInfo,
    AssistantReply,
)
from app.services import assistant_scope, assistant_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
CanAsk = Annotated[Principal, Depends(authorize(Permission.PORTAL_REPORTS_READ))]


@router.get("", response_model=AssistantInfo)
def info(principal: CanAsk, settings: Config) -> AssistantInfo:
    return assistant_service.info(principal, settings)


@router.get("/health", response_model=AssistantHealth)
def assistant_health(principal: CanAsk, settings: Config) -> AssistantHealth:
    return AssistantHealth.model_validate(assistant_service.health(settings))


@router.get("/conversations/{conversation_id}", response_model=AssistantConversation)
def read_conversation(conversation_id: uuid.UUID, principal: CanAsk) -> AssistantConversation:
    messages = assistant_scope.load_conversation(principal, conversation_id)
    if messages is None:
        raise ApiError(404, "conversation_not_found", "That conversation does not exist.")
    return AssistantConversation(id=conversation_id, messages=messages)


@router.delete("/conversations/{conversation_id}", status_code=204)
def remove_conversation(conversation_id: uuid.UUID, principal: CanAsk) -> None:
    if not assistant_scope.delete_conversation(principal, conversation_id):
        raise ApiError(404, "conversation_not_found", "That conversation does not exist.")


@router.post("/ask", response_model=AssistantReply)
def ask(payload: AssistantAsk, request: Request, db: Db, principal: CanAsk, settings: Config) -> AssistantReply:
    from app.console import transfers
    from app.core.errors import ApiError
    from app.tenancy import registry
    from app.tenancy.context import current_tenant

    if settings.tenancy_enabled:
        ref = current_tenant()
        if ref is not None:
            with registry.control_session(settings) as control:
                if not transfers.ai_allowed(control, uuid.UUID(ref.id)):
                    raise ApiError(
                        402,
                        "subscription_required",
                        "AI stays off until the subscription is paid. Submit the transfer receipt from billing.",
                    )
    correlation = request.headers.get("x-request-id") or None
    return assistant_service.ask(db, principal, settings, payload, correlation_id=correlation)
