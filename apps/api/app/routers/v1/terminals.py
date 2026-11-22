import threading
import time
import uuid
from collections import defaultdict, deque
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, require_device
from app.core.errors import ApiError
from app.models.store import Store
from app.schemas.devices import EntitlementRequest, SignedEntitlement, TerminalActivate, TerminalActivation
from app.services import bootstrap_service, device_service, entitlement_service

router = APIRouter()

WINDOW_SECONDS = 600
MAX_ATTEMPTS = 10
_attempts: dict[str, deque[float]] = defaultdict(deque)
_issue_attempts: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def _throttle(request: Request, bucket: dict[str, deque[float]] | None = None) -> None:
    """Activation keys are short, so guessing is slowed to MAX_ATTEMPTS per address per window."""
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    recent_bucket = _attempts if bucket is None else bucket
    with _lock:
        recent = recent_bucket[client]
        while recent and recent[0] < now - WINDOW_SECONDS:
            recent.popleft()
        if len(recent) >= MAX_ATTEMPTS:
            raise ApiError(429, "too_many_attempts", "Too many activation attempts. Wait a few minutes and try again.")
        recent.append(now)


@router.post("/activate", response_model=TerminalActivation)
def activate(
    payload: TerminalActivate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> TerminalActivation:
    """Public: a new register sends its store subdomain (X-Tenant-Domain) and one-time key."""
    _throttle(request)
    return device_service.activate_terminal(db, payload)


def _limit_issue(request: Request) -> None:
    """Count the attempt before authentication so a missing token cannot skip the limit."""
    _throttle(request, _issue_attempts)


@router.post("/entitlement", response_model=SignedEntitlement, dependencies=[Depends(_limit_issue)])
def issue_entitlement(
    payload: EntitlementRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_device)],
) -> SignedEntitlement:
    """An already-activated register asks for a permanent entitlement. A new device key needs a new activation key."""
    device = principal.device
    if device is None:
        raise ApiError(401, "unauthorized", "A register device token is required.")
    store = db.get(Store, device.store_id)
    if store is None:
        raise ApiError(401, "unauthorized", "This register is not attached to a branch.")
    signed = entitlement_service.issue(db, device, store, payload.device_public_key, rebind=False)
    db.commit()
    return signed


def _device(principal: Principal):
    device = principal.device
    if device is None:
        raise ApiError(401, "unauthorized", "A register device token is required.")
    return device


@router.post("/bootstrap/sessions")
def start_bootstrap(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_device)],
) -> dict:
    """Freezes this tenant's product ids for the authenticated register's branch."""
    return _session_out(bootstrap_service.start_session(db, _device(principal)))


@router.get("/bootstrap/sessions/{session_id}/pages")
def bootstrap_page(
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_device)],
    dataset: str = "products",
    after_position: int = -1,
    limit: int = 50,
) -> dict:
    try:
        parsed = uuid.UUID(session_id)
    except ValueError as exc:
        raise ApiError(404, "bootstrap_not_found", "That bootstrap session is not available to this register.") from exc
    return bootstrap_service.page(db, _device(principal), parsed, dataset, after_position, limit)


@router.get("/bootstrap/pull")
def bootstrap_pull(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_device)],
    cursor: str,
    limit: int = 50,
) -> dict:
    return bootstrap_service.pull(db, _device(principal), cursor, limit)


def _session_out(row) -> dict:
    return {
        "session_id": str(row.id),
        "schema_version": row.schema_version,
        "status": row.status,
        "dataset": "products",
        "product_count": row.product_count,
        "watermark": row.watermark,
        "since_seq": row.since_seq,
        "branch_id": str(row.store_id),
        "terminal_id": str(row.device_id),
    }
