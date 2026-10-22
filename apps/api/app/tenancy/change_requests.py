"""Change requests a tenant files with IT support: a new business type (needs a data migration) or a module that does
not fit its type. They live in the control database, where the console works the queue."""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import capabilities as capability_catalog
from app.core.config import Settings
from app.core.errors import ApiError
from app.models.customer import Customer
from app.models.product import Product
from app.models.restaurant import OpenOrder
from app.models.sale import Sale
from app.models.store import Store
from app.models.user import User
from app.schemas.governance import ChangeRequestIn, ChangeRequestOut
from app.services import audit, messaging_providers
from app.services.settings_service import cached_settings
from app.tenancy import registry
from app.tenancy.context import current_tenant
from app.tenancy.models import TenantChangeRequest

logger = logging.getLogger("ai_pos.change_requests")


def store_snapshot(db: Session) -> dict[str, int]:
    """How much data a business-type change would touch."""
    return {
        "stores": int(db.scalar(select(func.count(Store.id))) or 0),
        "products": int(db.scalar(select(func.count(Product.id))) or 0),
        "customers": int(db.scalar(select(func.count(Customer.id))) or 0),
        "sales": int(db.scalar(select(func.count(Sale.id)).where(Sale.is_quote_proforma.is_(False))) or 0),
        "open_orders": int(db.scalar(select(func.count(OpenOrder.id)).where(OpenOrder.status == "OPEN")) or 0),
    }


def out(row: TenantChangeRequest) -> ChangeRequestOut:
    return ChangeRequestOut(
        id=row.id,
        tenant_id=row.tenant_id,
        kind=row.kind,  # type: ignore[arg-type]
        requested_value=row.requested_value,
        current_value=row.current_value,
        reason=row.reason,
        snapshot=row.snapshot or {},
        status=row.status,  # type: ignore[arg-type]
        requested_by_email=row.requested_by_email,
        requested_by_name=row.requested_by_name,
        resolution_notes=row.resolution_notes,
        created_at=row.created_at,
        resolved_at=row.resolved_at,
    )


def _tenant_id(settings: Settings) -> uuid.UUID:
    tenant = current_tenant()
    if not settings.tenancy_enabled or tenant is None:
        raise ApiError(
            409,
            "support_contact",
            f"Email {settings.support_email} to request this change; this server has no support desk.",
        )
    return uuid.UUID(tenant.id)


def _check(db: Session, data: ChangeRequestIn) -> str:
    """The value the request would change from."""
    snapshot = cached_settings(db)
    if data.kind == "BUSINESS_TYPE":
        if data.requested_value not in capability_catalog.PROFILES:
            raise ApiError(422, "invalid_request", "Choose one of the business types.")
        if data.requested_value == snapshot.business_profile:
            raise ApiError(422, "invalid_request", "That is already your business type.")
        return snapshot.business_profile
    known = {capability.value for capability in capability_catalog.Capability}
    if data.requested_value not in known:
        raise ApiError(422, "invalid_request", "Choose one of the modules.")
    if data.requested_value in {capability.value for capability in snapshot.capabilities}:
        raise ApiError(422, "invalid_request", "That module is already on.")
    return snapshot.business_profile


def _notify(settings: Settings, tenant_name: str, row: TenantChangeRequest) -> None:
    """Best effort: the request is stored whatever happens to the email."""
    what = "business type" if row.kind == "BUSINESS_TYPE" else "module"
    body = (
        f"{tenant_name} asks to change its {what} from {row.current_value} to {row.requested_value}.\n\n"
        f"Reason: {row.reason}\n\nRequested by {row.requested_by_name} <{row.requested_by_email}>.\n"
        f"Store size: {row.snapshot}\nRequest id: {row.id}"
    )
    provider = "smtp" if settings.smtp_host else "log"
    try:
        messaging_providers.deliver(
            settings,
            provider,
            messaging_providers.Outgoing(
                to=settings.support_email, subject=f"Business Type Change Request - {tenant_name}", body=body
            ),
        )
    except messaging_providers.ProviderError:
        logger.warning("Support was not emailed about change request %s", row.id, exc_info=True)


def create(db: Session, settings: Settings, actor: User, data: ChangeRequestIn) -> ChangeRequestOut:
    tenant_id = _tenant_id(settings)
    current_value = _check(db, data)
    snapshot = store_snapshot(db)
    with registry.control_session(settings) as control:
        pending = control.scalar(
            select(TenantChangeRequest.id).where(
                TenantChangeRequest.tenant_id == tenant_id,
                TenantChangeRequest.kind == data.kind,
                TenantChangeRequest.status == "PENDING",
            )
        )
        if pending is not None:
            raise ApiError(409, "already_requested", "IT Support is already working on a request like this one.")
        row = TenantChangeRequest(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            kind=data.kind,
            requested_value=data.requested_value,
            current_value=current_value,
            reason=data.reason.strip(),
            snapshot=snapshot,
            status="PENDING",
            requested_by_email=actor.email,
            requested_by_name=actor.full_name,
            created_at=datetime.now(UTC),
        )
        control.add(row)
        control.commit()
        control.refresh(row)
        result = out(row)
        tenant = current_tenant()
        _notify(settings, tenant.name if tenant else "Store", row)
    audit.record(
        db,
        action_type="CREATE",
        action="settings.change_request",
        target_entity="Settings",
        target_entity_id=None,
        user=actor,
        new_values={"kind": data.kind, "requested_value": data.requested_value},
        reason_notes=data.reason.strip(),
    )
    db.commit()
    return result


def list_for_tenant(settings: Settings) -> list[ChangeRequestOut]:
    tenant = current_tenant()
    if not settings.tenancy_enabled or tenant is None:
        return []
    with registry.control_session(settings) as control:
        rows = control.scalars(
            select(TenantChangeRequest)
            .where(TenantChangeRequest.tenant_id == uuid.UUID(tenant.id))
            .order_by(TenantChangeRequest.created_at.desc())
            .limit(50)
        ).all()
        return [out(row) for row in rows]
