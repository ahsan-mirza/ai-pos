import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.approvals import ApprovalCreate, ApprovalDecision, ApprovalOut
from app.services import approval_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanRegister = Annotated[
    Principal, Depends(authorize(Permission.POS_ACCESS, allow_device=True, scopes=("pos", "portal")))
]
CanPortal = Annotated[Principal, Depends(authorize(Permission.PORTAL_ACCESS))]


@router.post("", response_model=ApprovalOut, status_code=201)
def ask(payload: ApprovalCreate, db: Db, principal: CanRegister) -> ApprovalOut:
    return approval_service.create(db, principal, payload)


@router.get("", response_model=list[ApprovalOut])
def inbox(db: Db, principal: CanPortal, include_decided: bool = False) -> list[ApprovalOut]:
    return approval_service.inbox(db, principal, include_decided)


@router.get("/{request_id}", response_model=ApprovalOut)
def status(request_id: uuid.UUID, db: Db, principal: CanRegister) -> ApprovalOut:
    return approval_service.status(db, principal, request_id)


@router.post("/{request_id}/cancel", response_model=ApprovalOut)
def cancel(request_id: uuid.UUID, db: Db, principal: CanRegister) -> ApprovalOut:
    return approval_service.cancel(db, principal, request_id)


@router.post("/{request_id}/approve", response_model=ApprovalOut)
def approve(request_id: uuid.UUID, payload: ApprovalDecision, db: Db, principal: CanPortal) -> ApprovalOut:
    return approval_service.decide(db, principal, request_id, True, payload.note)


@router.post("/{request_id}/decline", response_model=ApprovalOut)
def decline(request_id: uuid.UUID, payload: ApprovalDecision, db: Db, principal: CanPortal) -> ApprovalOut:
    return approval_service.decide(db, principal, request_id, False, payload.note)
