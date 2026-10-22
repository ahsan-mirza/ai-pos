import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize, verify_user_token
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.routers.v1.deps import assert_store_access, require_device_id, require_idempotency_key
from app.schemas.payloads import ReceiptOut, ReturnOut, ReturnPayload, ReturnsAnalytics
from app.services import invoice_pdf, returns_service
from app.services.settings_service import report_currency
from app.services.sync_service import ingest_one

router = APIRouter()

CanReport = Annotated[Principal, Depends(authorize(Permission.PORTAL_REPORTS_READ, allow_device=True))]
AtRegister = Annotated[
    Principal,
    Depends(authorize(Permission.POS_ACCESS, allow_device=True, scopes=("pos", "portal"))),
]


@router.get("/receipts/{code}", response_model=ReceiptOut)
def lookup_receipt(
    code: str,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: AtRegister,
) -> ReceiptOut:
    return returns_service.find_receipt(db, settings, code, store_scope=principal.store_id)


@router.post("", response_model=ReturnOut, status_code=201)
def create_return(
    payload: ReturnPayload,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: AtRegister,
    device_id: Annotated[str, Depends(require_device_id)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    x_approver_token: Annotated[str | None, Header(alias="X-Approver-Token")] = None,
) -> ReturnOut:
    """Processes one return in one transaction. Offline registers replay the same payload through /sync/push."""
    if principal.user is not None:
        if principal.user.id != payload.cashier_id:
            raise ApiError(403, "forbidden", "Returns must be attributed to the signed-in cashier.")
        if payload.override is not None:
            if x_approver_token is None:
                raise ApiError(403, "approval_required", "Send the approving manager's token in X-Approver-Token.")
            approver = verify_user_token(x_approver_token, db, settings)
            if approver.id != payload.override.approved_by_id:
                raise ApiError(403, "approval_mismatch", "The approval token belongs to a different user.")
    assert_store_access(principal, payload.store_id)
    result = ingest_one(
        db,
        settings,
        device_id=device_id,
        idempotency_key=idempotency_key,
        entity_type="sale_return",
        payload=payload,
        source="register" if principal.kind == "device" else "portal",
        device=principal.device,
    )
    if result.results[0].status == "duplicate":
        response.status_code = 200
    return returns_service.get_return(db, payload.id)


@router.get("", response_model=list[ReturnOut])
def list_returns(
    db: Annotated[Session, Depends(get_db)],
    principal: CanReport,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ReturnOut]:
    return returns_service.list_returns(db, limit=limit, store_scope=principal.store_id)


@router.get("/analytics", response_model=ReturnsAnalytics)
def returns_analytics(
    db: Annotated[Session, Depends(get_db)],
    principal: CanReport,
    timeframe: Annotated[Literal["all_time", "weekly", "monthly"], Query()] = "all_time",
    currency: Annotated[str | None, Query(min_length=3, max_length=3)] = None,
) -> ReturnsAnalytics:
    code = report_currency(db, currency)
    return returns_service.build_returns_analytics(
        db,
        timeframe=timeframe,
        currency=code,
        store_scope=principal.store_id,
    )


@router.get("/{return_id}/credit-note.pdf", response_class=Response)
def credit_note_pdf(
    return_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: AtRegister,
) -> Response:
    content = invoice_pdf.render_credit_note(db, settings, return_id, principal.store_id)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="credit-note-{str(return_id)[:8]}.pdf"'},
    )


@router.get("/{return_id}", response_model=ReturnOut)
def get_return(
    return_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: CanReport,
) -> ReturnOut:
    return returns_service.get_return(db, return_id, store_scope=principal.store_id)
