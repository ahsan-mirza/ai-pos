"""Staff routes for the customer-care agent. The webhook stays on the existing Reach route."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from reach.ai_agent import service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
CanManage = Annotated[Principal, Depends(authorize(Permission.MESSAGING_MANAGE))]


class AgentWrite(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    greeting: str | None = Field(default=None, max_length=300)
    language: str | None = None
    tone: str | None = Field(default=None, max_length=24)
    instructions: str | None = Field(default=None, max_length=4000)
    mode: str | None = None
    product_help: bool | None = None
    order_help: bool | None = None
    action_detection: bool | None = None
    handoff: bool | None = None
    response_priority: str | None = None
    human_wait_seconds: int | None = None
    notify_staff: bool | None = None


class KnowledgeWrite(BaseModel):
    kind: str = "faq"
    title: str = Field(max_length=160)
    body: str = Field(max_length=8000)


class TextWrite(BaseModel):
    body: str = Field(max_length=4000)


class AssignWrite(BaseModel):
    user_id: UUID


@router.get("/agent")
def read_agent(db: Db, _: CanManage) -> dict:
    return service.present_agent(db, service.agent_row(db))


@router.get("/agent/health")
def agent_health(db: Db, settings: Config, _: CanManage) -> dict:
    return service.health(db, settings)


@router.put("/agent")
def write_agent(payload: AgentWrite, db: Db, _: CanManage) -> dict:
    return service.save_agent(db, payload.model_dump())


@router.post("/agent/enable")
def enable_agent(db: Db, _: CanManage) -> dict:
    return service.set_enabled(db, True)


@router.post("/agent/disable")
def disable_agent(db: Db, _: CanManage) -> dict:
    return service.set_enabled(db, False)


@router.post("/agent/test")
def test_agent(payload: TextWrite, db: Db, settings: Config, _: CanManage) -> dict:
    return service.preview(db, settings, payload.body)


@router.get("/knowledge")
def knowledge(db: Db, _: CanManage) -> list[dict]:
    return service.list_knowledge(db)


@router.post("/knowledge", status_code=201)
def create_knowledge(payload: KnowledgeWrite, db: Db, _: CanManage) -> dict:
    return service.add_knowledge(db, payload.kind, payload.title, payload.body)


@router.delete("/knowledge/{knowledge_id}", status_code=204)
def remove_knowledge(knowledge_id: UUID, db: Db, _: CanManage) -> None:
    service.delete_knowledge(db, knowledge_id)


@router.get("/conversations")
def conversations(db: Db, _: CanManage, status: str | None = None, handler: str | None = None) -> list[dict]:
    return service.list_conversations(db, status, handler)


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: UUID, db: Db, _: CanManage) -> dict:
    return service.conversation_detail(db, conversation_id)


@router.post("/conversations/{conversation_id}/reply")
def reply(conversation_id: UUID, payload: TextWrite, db: Db, principal: CanManage) -> dict:
    return service.staff_reply(db, conversation_id, payload.body, None if principal.user is None else principal.user.id)


@router.post("/conversations/{conversation_id}/takeover")
def take_over(conversation_id: UUID, db: Db, principal: CanManage) -> dict:
    return service.takeover(db, conversation_id, None if principal.user is None else principal.user.id)


@router.post("/conversations/{conversation_id}/resume")
def resume(conversation_id: UUID, db: Db, principal: CanManage) -> dict:
    return service.resume(db, conversation_id, None if principal.user is None else principal.user.id)


@router.post("/conversations/{conversation_id}/assign")
def assign(conversation_id: UUID, payload: AssignWrite, db: Db, _: CanManage) -> dict:
    return service.assign(db, conversation_id, payload.user_id)


@router.post("/conversations/{conversation_id}/resolve")
def resolve(conversation_id: UUID, db: Db, principal: CanManage) -> dict:
    return service.resolve(db, conversation_id, None if principal.user is None else principal.user.id)


@router.post("/conversations/{conversation_id}/notes")
def notes(conversation_id: UUID, payload: TextWrite, db: Db, principal: CanManage) -> dict:
    return service.add_note(db, conversation_id, payload.body, None if principal.user is None else principal.user.id)


@router.get("/actions")
def actions(db: Db, _: CanManage, status: str | None = None) -> list[dict]:
    return service.list_actions(db, status)


@router.post("/actions/{action_id}/approve")
def approve(action_id: UUID, db: Db, principal: CanManage) -> dict:
    return service.set_action_status(db, action_id, "approved", None if principal.user is None else principal.user.id)


@router.post("/actions/{action_id}/reject")
def reject(action_id: UUID, db: Db, principal: CanManage) -> dict:
    return service.set_action_status(db, action_id, "rejected", None if principal.user is None else principal.user.id)


@router.post("/actions/{action_id}/execute")
def execute(action_id: UUID, db: Db, principal: CanManage) -> dict:
    return service.execute_action(db, action_id, None if principal.user is None else principal.user.id)


@router.get("/analytics")
def analytics(db: Db, _: CanManage) -> dict:
    return service.analytics(db)
