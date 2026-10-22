import threading
import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ApiError
from app.schemas.devices import TerminalActivate, TerminalActivation
from app.services import device_service

router = APIRouter()

WINDOW_SECONDS = 600
MAX_ATTEMPTS = 10
_attempts: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def _throttle(request: Request) -> None:
    """Activation keys are short, so guessing is slowed to MAX_ATTEMPTS per address per window."""
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _lock:
        recent = _attempts[client]
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
