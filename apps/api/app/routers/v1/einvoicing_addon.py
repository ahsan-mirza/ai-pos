"""Portal routes for the UAE e-Invoicing add-on. Tenant id comes from the bound request, never the body."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, has_capability, require_capability
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.tenancy.scoping import active_tenant_id

_PLUGIN = Path(__file__).resolve().parents[5] / "plugins" / "einvoicing"
if str(_PLUGIN) not in sys.path:
    sys.path.insert(0, str(_PLUGIN))

from einvoicing.engine import TransitionError  # noqa: E402
from einvoicing.models import Invoice  # noqa: E402
from einvoicing.service import (  # noqa: E402
    connect_provider,
    dashboard,
    invoice_public,
    list_invoices,
    manual_retry,
    update_settings,
)

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanRead = Annotated[Principal, Depends(authorize(Permission.PORTAL_REPORTS_READ))]


def _guard_write(db: Session, request: Request) -> None:
    require_capability(Capability.UAE_EINVOICING)(db, request)


def _guard_read(db: Session) -> None:
    if has_capability(db, Capability.UAE_EINVOICING):
        return
    tenant_id = active_tenant_id()
    existing = db.scalar(select(func.count()).select_from(Invoice).where(Invoice.tenant_id == tenant_id))
    if existing:
        return
    raise ApiError(403, "capability_disabled", "UAE e-Invoicing is not enabled for this business.")


@router.get("/dashboard")
def einvoicing_dashboard(_principal: CanRead, db: Db) -> dict:
    _guard_read(db)
    return dashboard(db, active_tenant_id())


@router.get("/invoices")
def einvoicing_invoices(
    _principal: CanRead,
    db: Db,
    status: str | None = None,
    store_id: uuid.UUID | None = None,
    number: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[dict]:
    _guard_read(db)
    return list_invoices(
        db,
        active_tenant_id(),
        status=status,
        store_id=store_id,
        number=number,
        offset=offset,
        limit=limit,
    )


@router.get("/invoices/{invoice_id}")
def einvoicing_invoice(invoice_id: uuid.UUID, _principal: CanRead, db: Db) -> dict:
    _guard_read(db)
    row = db.get(Invoice, invoice_id)
    tenant_id = active_tenant_id()
    if row is None or row.tenant_id != tenant_id:
        raise ApiError(404, "not_found", "Invoice was not found.")
    return invoice_public(row)


@router.post("/invoices/{invoice_id}/retry")
def einvoicing_retry(invoice_id: uuid.UUID, request: Request, _principal: CanRead, db: Db) -> dict:
    _guard_write(db, request)
    try:
        row = manual_retry(db, active_tenant_id(), invoice_id)
    except LookupError as exc:
        raise ApiError(404, "not_found", "Invoice was not found.") from exc
    except TransitionError as exc:
        raise ApiError(409, "not_retryable", str(exc)) from exc
    db.commit()
    return invoice_public(row)


@router.get("/configuration")
def einvoicing_configuration(_principal: CanRead, db: Db) -> dict:
    _guard_write_view = has_capability(db, Capability.UAE_EINVOICING)
    if not _guard_write_view:
        raise ApiError(403, "capability_disabled", "UAE e-Invoicing is not enabled for this business.")
    from einvoicing.service import public_settings, settings_row

    return public_settings(settings_row(db, active_tenant_id()))


@router.put("/configuration")
async def einvoicing_configuration_save(request: Request, _principal: CanRead, db: Db) -> dict:
    _guard_write(db, request)
    payload = await request.json()
    payload.pop("tenant_id", None)
    try:
        saved = update_settings(db, active_tenant_id(), payload)
    except ValueError as exc:
        raise ApiError(422, "invalid_request", str(exc)) from exc
    db.commit()
    return saved


@router.post("/providers/test")
async def einvoicing_provider_test(request: Request, _principal: CanRead, db: Db) -> dict:
    _guard_write(db, request)
    payload = await request.json()
    result = connect_provider(db, active_tenant_id(), str(payload.get("provider_code") or ""))
    db.commit()
    return result
