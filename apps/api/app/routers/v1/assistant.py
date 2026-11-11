import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile
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
    DocumentAnalysisOut,
)
from app.services import assistant_documents, assistant_scope, assistant_service
from app.services.import_parser import MAX_FILE_BYTES

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


@router.post("/documents", response_model=DocumentAnalysisOut)
async def analyze_document(db: Db, principal: CanAsk, file: Annotated[UploadFile, File()]) -> DocumentAnalysisOut:
    """Reads an attached catalog. The response is calculated from the file. No products are created."""
    del principal
    data = await file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ApiError(413, "file_too_large", "Attachments are limited to 10 MB.")
    found = assistant_documents.analyze(db, file.filename or "upload", data)
    return DocumentAnalysisOut.model_validate(found, from_attributes=True)


@router.get("/documents/{document_id}", response_model=DocumentAnalysisOut)
def read_document(document_id: str, principal: CanAsk) -> DocumentAnalysisOut:
    del principal
    found = assistant_documents.load_analysis(document_id)
    if found is None:
        raise ApiError(404, "document_not_found", "That file analysis does not exist.")
    return DocumentAnalysisOut.model_validate(found, from_attributes=True)


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
