"""Remote manager approvals: the register asks, a manager answers from the portal or their phone."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import Principal
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.models.approval import ApprovalRequest
from app.models.store import Store
from app.models.user import User
from app.schemas.approvals import ApprovalCreate, ApprovalOut, ApproverOut

TTL = timedelta(minutes=10)
KIND_PERMISSION = {
    "PRICE_OVERRIDE": Permission.POS_PRICE_OVERRIDE,
    "BELOW_FLOOR": Permission.POS_BELOW_FLOOR_OVERRIDE,
    "CREDIT_LIMIT": Permission.CUSTOMERS_MANAGE,
    "REFUND": Permission.POS_REFUND,
}


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _expire(request: ApprovalRequest) -> None:
    if request.status == "PENDING" and _aware(request.expires_at) <= _now():
        request.status = "EXPIRED"


def _out(db: Session, request: ApprovalRequest, *, with_approver: bool = False) -> ApprovalOut:
    users = {
        row.id: row
        for row in db.scalars(
            select(User).where(User.id.in_([item for item in (request.requested_by_id, request.decided_by_id) if item]))
        ).unique()
    }
    store = db.get(Store, request.store_id) if request.store_id else None
    decider = users.get(request.decided_by_id) if request.decided_by_id else None
    approver = None
    if with_approver and request.status == "APPROVED" and decider is not None:
        approver = ApproverOut(
            id=decider.id,
            username=decider.username,
            full_name=decider.full_name,
            store_id=decider.store_id,
            role_name=decider.role.name if decider.role else "",
            permissions=sorted(decider.permissions),
        )
    requester = users.get(request.requested_by_id) if request.requested_by_id else None
    return ApprovalOut(
        id=request.id,
        kind=request.kind,  # type: ignore[arg-type]
        status=request.status,  # type: ignore[arg-type]
        store_id=request.store_id,
        store_code=store.code if store else None,
        requested_by_name=requester.full_name if requester else None,
        title=request.title,
        details=list(request.details or []),
        amount_cents=request.amount_cents,
        created_at=request.created_at,
        expires_at=request.expires_at,
        decided_at=request.decided_at,
        decided_by_name=decider.full_name if decider else None,
        note=request.note,
        approver=approver,
    )


def _register_scope(principal: Principal, request: ApprovalRequest) -> None:
    if principal.device is not None and request.device_id not in (None, principal.device.id):
        raise ApiError(404, "not_found", "Approval request was not found.")
    if principal.store_id is not None and request.store_id not in (None, principal.store_id):
        raise ApiError(404, "not_found", "Approval request was not found.")


def create(db: Session, principal: Principal, data: ApprovalCreate) -> ApprovalOut:
    store_id = principal.store_id or data.store_id
    if store_id is not None and db.get(Store, store_id) is None:
        raise ApiError(404, "not_found", "Store was not found.")
    if db.get(User, data.requested_by_id) is None:
        raise ApiError(404, "not_found", "The cashier asking was not found.")
    request = ApprovalRequest(
        kind=data.kind,
        permission=KIND_PERMISSION[data.kind].value,
        store_id=store_id,
        device_id=principal.device.id if principal.device is not None else None,
        requested_by_id=data.requested_by_id,
        title=data.title.strip(),
        details=[line.strip()[:200] for line in data.details if line.strip()],
        amount_cents=data.amount_cents,
        expires_at=_now() + TTL,
    )
    db.add(request)
    db.commit()
    return _out(db, request)


def _get(db: Session, request_id: uuid.UUID) -> ApprovalRequest:
    request = db.get(ApprovalRequest, request_id)
    if request is None:
        raise ApiError(404, "not_found", "Approval request was not found.")
    return request


def status(db: Session, principal: Principal, request_id: uuid.UUID) -> ApprovalOut:
    request = _get(db, request_id)
    _register_scope(principal, request)
    if request.status == "PENDING" and _aware(request.expires_at) <= _now():
        _expire(request)
        db.commit()
    return _out(db, request, with_approver=True)


def cancel(db: Session, principal: Principal, request_id: uuid.UUID) -> ApprovalOut:
    request = _get(db, request_id)
    _register_scope(principal, request)
    if request.status == "PENDING":
        request.status = "CANCELLED"
        request.decided_at = _now()
        db.commit()
    return _out(db, request)


def _can_decide(user: User, request: ApprovalRequest) -> bool:
    if request.permission not in user.permissions:
        return False
    if user.store_id is not None and request.store_id is not None and user.store_id != request.store_id:
        return False
    return not (request.kind == "REFUND" and request.requested_by_id == user.id)


def inbox(db: Session, principal: Principal, include_decided: bool = False) -> list[ApprovalOut]:
    user = principal.user
    if user is None:
        raise ApiError(403, "forbidden", "Sign in to see approval requests.")
    query = select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc())
    if include_decided:
        query = query.where(ApprovalRequest.created_at >= _now() - timedelta(days=1))
    else:
        query = query.where(ApprovalRequest.status == "PENDING")
    rows = []
    changed = False
    for request in db.scalars(query.limit(200)):
        if request.status == "PENDING" and _aware(request.expires_at) <= _now():
            _expire(request)
            changed = True
            if not include_decided:
                continue
        if _can_decide(user, request):
            rows.append(request)
    if changed:
        db.commit()
    return [_out(db, row) for row in rows]


def pending_count(db: Session, user: User) -> int:
    now = _now()
    rows = db.scalars(select(ApprovalRequest).where(ApprovalRequest.status == "PENDING"))
    return sum(1 for row in rows if _aware(row.expires_at) > now and _can_decide(user, row))


def decide(db: Session, principal: Principal, request_id: uuid.UUID, approve: bool, note: str) -> ApprovalOut:
    user = principal.user
    if user is None:
        raise ApiError(403, "forbidden", "Sign in to answer approval requests.")
    request = _get(db, request_id)
    _expire(request)
    if request.status != "PENDING":
        db.commit()
        raise ApiError(409, "approval_closed", f"This request is already {request.status.lower()}.")
    if not _can_decide(user, request):
        raise ApiError(403, "forbidden", "You cannot answer this request.")
    if approve and len(note.strip()) < 3:
        raise ApiError(422, "note_required", "Give a short reason; it goes on the audit trail with the sale.")
    request.status = "APPROVED" if approve else "DECLINED"
    request.decided_by_id = user.id
    request.decided_at = _now()
    request.note = note.strip()
    db.commit()
    return _out(db, request)
