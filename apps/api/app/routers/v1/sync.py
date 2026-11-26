from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, require_device
from app.schemas.payloads import SyncPushRequest, SyncPushResponse
from app.services.sync_service import push_batch

router = APIRouter()


@router.post("/push", response_model=SyncPushResponse)
def push_sync(
    request: SyncPushRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(require_device)],
    x_sync_attempt: Annotated[str | None, Header(alias="X-Sync-Attempt")] = None,
) -> SyncPushResponse:
    return push_batch(
        db, request, settings, source="register", device=principal.device, attempt_id=x_sync_attempt
    )
