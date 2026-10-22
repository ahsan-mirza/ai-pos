"""Workshop endpoints for repair tickets (board, assignment, approval, deposits, photos, job card, pickup).
Mounted ahead of the repairs router so /repairs/board and /repairs/lookup are not read as ticket ids."""

import base64
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.repairs import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalSent,
    AttachmentKind,
    AttachmentUpload,
    DepositCreate,
    JobCardFile,
    PasscodeOut,
    PickupRequest,
    RepairAssign,
    RepairBoard,
    RepairDetail,
    RepairStatusChange,
)
from app.services import repair_documents, repair_service, repair_workshop_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
CanUpdate = Annotated[Principal, Depends(authorize(Permission.REPAIRS_UPDATE))]
Viewer = Annotated[Principal, Depends(authorize(Permission.PORTAL_ACCESS))]
AtCounter = Annotated[
    Principal,
    Depends(authorize(Permission.REPAIRS_CREATE, allow_device=True, scopes=("portal", "pos"))),
]


def _detail(db: Session, settings: Settings, principal: Principal, ticket_id: uuid.UUID) -> RepairDetail:
    return repair_service.detail(db, settings, ticket_id, principal.store_id)


@router.get("/board", response_model=RepairBoard)
def bench_board(
    db: Db,
    principal: Viewer,
    store_id: uuid.UUID | None = None,
    technician_id: uuid.UUID | None = None,
) -> RepairBoard:
    return repair_workshop_service.board(db, principal.store_id, store_id, technician_id)


@router.get("/lookup", response_model=RepairDetail)
def lookup_job_card(code: str, db: Db, settings: Config, principal: AtCounter) -> RepairDetail:
    """Scanning a job card's barcode (RPR-XXXXXXXX) at the register opens its ticket."""
    ticket = repair_workshop_service.find_by_code(db, code, principal.store_id)
    return _detail(db, settings, principal, ticket.id)


@router.get("/{ticket_id}/workshop", response_model=RepairDetail)
def counter_detail(ticket_id: uuid.UUID, db: Db, settings: Config, principal: AtCounter) -> RepairDetail:
    return _detail(db, settings, principal, ticket_id)


@router.patch("/{ticket_id}", response_model=RepairDetail)
def assign(ticket_id: uuid.UUID, payload: RepairAssign, db: Db, settings: Config, principal: CanUpdate) -> RepairDetail:
    repair_workshop_service.assign(db, principal, ticket_id, payload)
    return _detail(db, settings, principal, ticket_id)


@router.post("/{ticket_id}/approval/request", response_model=ApprovalSent)
def request_approval(
    ticket_id: uuid.UUID, payload: ApprovalRequest, db: Db, settings: Config, principal: CanUpdate
) -> ApprovalSent:
    _, url, status = repair_workshop_service.request_approval(db, settings, principal, ticket_id, payload)
    return ApprovalSent(ticket=_detail(db, settings, principal, ticket_id), approval_url=url, message_status=status)


@router.post("/{ticket_id}/approval", response_model=RepairDetail)
def record_approval(
    ticket_id: uuid.UUID, payload: ApprovalDecision, db: Db, settings: Config, principal: CanUpdate
) -> RepairDetail:
    repair_workshop_service.decide_in_store(db, principal, ticket_id, payload)
    return _detail(db, settings, principal, ticket_id)


@router.post("/{ticket_id}/deposits", response_model=RepairDetail, status_code=201)
def add_deposit(
    ticket_id: uuid.UUID, payload: DepositCreate, db: Db, settings: Config, principal: AtCounter
) -> RepairDetail:
    repair_workshop_service.add_deposit(db, principal, ticket_id, payload)
    return _detail(db, settings, principal, ticket_id)


@router.post("/{ticket_id}/deposits/{deposit_id}/refund", response_model=RepairDetail)
def refund_deposit(
    ticket_id: uuid.UUID,
    deposit_id: uuid.UUID,
    db: Db,
    settings: Config,
    principal: CanUpdate,
    shift_id: uuid.UUID | None = None,
) -> RepairDetail:
    repair_workshop_service.refund_deposit(db, principal, ticket_id, deposit_id, shift_id)
    return _detail(db, settings, principal, ticket_id)


@router.post("/{ticket_id}/attachments", response_model=RepairDetail, status_code=201)
def upload_attachment(
    ticket_id: uuid.UUID,
    db: Db,
    settings: Config,
    principal: AtCounter,
    file: Annotated[UploadFile, File()],
    kind: Annotated[AttachmentKind, Form()] = "INTAKE",
) -> RepairDetail:
    repair_workshop_service.save_attachment(db, principal, ticket_id, file, kind)
    return _detail(db, settings, principal, ticket_id)


@router.get("/{ticket_id}/attachments/{attachment_id}")
def download_attachment(ticket_id: uuid.UUID, attachment_id: uuid.UUID, db: Db, principal: Viewer) -> FileResponse:
    path, row = repair_workshop_service.attachment_file(db, principal, ticket_id, attachment_id)
    return FileResponse(path, media_type=row.content_type, filename=row.file_name)


@router.delete("/{ticket_id}/attachments/{attachment_id}", response_model=RepairDetail)
def delete_attachment(
    ticket_id: uuid.UUID, attachment_id: uuid.UUID, db: Db, settings: Config, principal: CanUpdate
) -> RepairDetail:
    repair_workshop_service.delete_attachment(db, principal, ticket_id, attachment_id)
    return _detail(db, settings, principal, ticket_id)


@router.get("/{ticket_id}/passcode", response_model=PasscodeOut)
def reveal_passcode(ticket_id: uuid.UUID, db: Db, settings: Config, principal: CanUpdate) -> PasscodeOut:
    return PasscodeOut(passcode=repair_workshop_service.reveal_passcode(db, settings, principal, ticket_id))


@router.post("/{ticket_id}/attachments/json", response_model=RepairDetail, status_code=201)
def upload_attachment_json(
    ticket_id: uuid.UUID, payload: AttachmentUpload, db: Db, settings: Config, principal: AtCounter
) -> RepairDetail:
    repair_workshop_service.save_attachment_bytes(
        db, principal, ticket_id, payload.content_type, payload.data_base64, payload.file_name, payload.kind
    )
    return _detail(db, settings, principal, ticket_id)


@router.get("/{ticket_id}/job-card.pdf")
def job_card(ticket_id: uuid.UUID, db: Db, settings: Config, principal: AtCounter) -> Response:
    ref, pdf = repair_documents.render_job_card(db, settings, ticket_id, principal.store_id)
    return Response(
        pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="job-card-{ref}.pdf"'}
    )


@router.get("/{ticket_id}/job-card", response_model=JobCardFile)
def job_card_json(ticket_id: uuid.UUID, db: Db, settings: Config, principal: AtCounter) -> JobCardFile:
    """Base64 PDF for the register, whose passthrough only returns JSON."""
    ref, pdf = repair_documents.render_job_card(db, settings, ticket_id, principal.store_id)
    return JobCardFile(filename=f"job-card-{ref}.pdf", pdf_base64=base64.b64encode(pdf).decode())


@router.post("/{ticket_id}/pickup", response_model=RepairDetail)
def pickup(
    ticket_id: uuid.UUID, payload: PickupRequest, db: Db, settings: Config, principal: AtCounter
) -> RepairDetail:
    """Hand back a device that has nothing to invoice (declined estimate, warranty repair at no charge)."""
    note = payload.note.strip() or "Collected by the customer"
    return repair_service.change_status(
        db, settings, principal, ticket_id, RepairStatusChange(status="closed", note=note)
    )
