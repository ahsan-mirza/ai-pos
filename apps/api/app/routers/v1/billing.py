"""Store-facing catalog, quote and go-live checkout.

The public catalog and the Stripe webhook are tenant-free and listed in OPEN_PATHS.
"""

import json
import uuid
from datetime import UTC, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select

from app.console import billing, transfers
from app.core.config import Settings, get_settings
from app.core.deps import Principal, authorize, get_principal
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.schemas.billing import (
    AccessOut,
    AccessSubscription,
    CatalogOut,
    CheckoutIn,
    CheckoutOut,
    CheckoutStatus,
    MarketplaceOut,
    QuoteIn,
    QuoteOut,
)
from app.tenancy import registry
from app.tenancy.context import current_tenant
from app.tenancy.models import Subscription, Tenant

router = APIRouter()
Config = Annotated[Settings, Depends(get_settings)]
RETURN_PAGE = """<!doctype html><html><body style="font-family:sans-serif;padding:2rem">
<p>You can close this window and return to the store.</p></body></html>"""


def _tenant_id(settings: Settings) -> uuid.UUID:
    if not settings.tenancy_enabled:
        raise ApiError(
            404, "billing_unavailable", "Subscriptions are available when the server hosts more than one store."
        )
    ref = current_tenant()
    if ref is None:
        raise ApiError(400, "tenant_required", "Send X-Tenant-Domain or use your store's subdomain.")
    with registry.control_session(settings) as db:
        row = db.get(Tenant, uuid.UUID(ref.id))
        if row is None:
            raise ApiError(404, "tenant_not_found", "This store is not registered.")
        return row.id


def _stores(settings: Settings, tenant_id: uuid.UUID) -> dict[uuid.UUID, str]:
    from app.console.entitlements import tenant_session
    from app.models.store import Store

    with registry.control_session(settings) as db:
        tenant = db.get(Tenant, tenant_id)
        if tenant is None:
            return {}
    with tenant_session(tenant, settings) as store_db:
        return {row.id: row.name for row in store_db.scalars(select(Store))}


def _active_catalog(found: CatalogOut) -> CatalogOut:
    return found.model_copy(
        update={
            "plans": [row for row in found.plans if row.active],
            "cycles": [row for row in found.cycles if row.active],
            "addons": [
                row
                for row in found.addons
                if row.active and (not row.module_keys or row.monthly_fils > 0)
            ],
            "fees": [row for row in found.fees if row.active],
        }
    )


@router.get("/public-catalog", response_model=CatalogOut)
def public_catalog(settings: Config) -> CatalogOut:
    """Active packages, cycles, add-ons, and fees for the marketing site. No store session and no tenant."""
    if not settings.tenancy_enabled:
        raise ApiError(
            404, "billing_unavailable", "Subscriptions are available when the server hosts more than one store."
        )
    with registry.control_session(settings) as db:
        found = billing.catalog(db)
        db.commit()
        return _active_catalog(found)


@router.get("/marketplace", response_model=MarketplaceOut)
def marketplace(
    _: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))], settings: Config
) -> MarketplaceOut:
    """Card state for this store. Activation comes from the subscription and open invoices."""
    tenant_id = _tenant_id(settings)
    with registry.control_session(settings) as db:
        tenant = db.get(Tenant, tenant_id)
        if tenant is None:
            raise ApiError(404, "tenant_not_found", "This store is not registered.")
        from app.console.addon_listing import marketplace_for

        found = marketplace_for(db, settings, tenant)
        db.commit()
        return found


@router.get("/catalog", response_model=CatalogOut)
def catalog(
    _: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))], settings: Config
) -> CatalogOut:
    _tenant_id(settings)
    with registry.control_session(settings) as db:
        found = billing.catalog(db)
        db.commit()
        return found


@router.post("/quote", response_model=QuoteOut)
def quote(
    payload: QuoteIn, _: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))], settings: Config
) -> QuoteOut:
    tenant_id = _tenant_id(settings)
    stores = _stores(settings, tenant_id)
    with registry.control_session(settings) as db:
        return billing.quote_for(db, payload.plan_code, payload.cycle_code, payload.addons, payload.hardware, stores)


@router.post("/addons/{code}/checkout", response_model=CheckoutOut)
def addon_checkout(
    code: str,
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
    settings: Config,
) -> CheckoutOut:
    if principal.user is None:
        raise ApiError(403, "business_wide_only", "Only a business-wide admin can buy an add-on.")
    tenant_id = _tenant_id(settings)
    with registry.control_session(settings) as db:
        row = db.get(Tenant, tenant_id)
        assert row is not None
        return billing.create_addon_checkout(db, settings, row, principal.user.id, code)


@router.post("/checkout", response_model=CheckoutOut)
def checkout(
    payload: CheckoutIn,
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
    settings: Config,
) -> CheckoutOut:
    if principal.user is None:
        raise ApiError(403, "business_wide_only", "Only a business-wide admin can take the store live.")
    tenant_id = _tenant_id(settings)
    with registry.control_session(settings) as db:
        row = db.get(Tenant, tenant_id)
        assert row is not None
        return billing.create_checkout(db, settings, row, principal.user.id, payload, _stores(settings, tenant_id))


@router.get("/checkout/return", response_class=HTMLResponse)
def checkout_return() -> HTMLResponse:
    return HTMLResponse(RETURN_PAGE)


@router.get("/checkout/{checkout_id}", response_model=CheckoutStatus)
def checkout_state(
    checkout_id: uuid.UUID,
    _: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
    settings: Config,
) -> CheckoutStatus:
    tenant_id = _tenant_id(settings)
    with registry.control_session(settings) as db:
        return billing.checkout_status(db, tenant_id, checkout_id)


@router.post("/checkout/{checkout_id}/simulate", response_model=CheckoutStatus)
def simulate(
    checkout_id: uuid.UUID,
    _: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
    settings: Config,
) -> CheckoutStatus:
    tenant_id = _tenant_id(settings)
    with registry.control_session(settings) as db:
        return billing.simulate_checkout(db, settings, tenant_id, checkout_id)


@router.get("/access", response_model=AccessOut)
def access_status(principal: Annotated[Principal, Depends(get_principal)], settings: Config) -> AccessOut:
    """Request-time entitlement. A delayed job cannot extend access past this answer."""
    del principal
    tenant_id = _tenant_id(settings)
    with registry.control_session(settings) as db:
        tenant = db.get(Tenant, tenant_id)
        summary = billing.subscription_out(db, tenant) if tenant is not None else None
        row = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
        subscription = None
        if summary is not None and row is not None:
            end = summary.current_period_end
            grace_end = None
            if end is not None:
                moment = end if end.tzinfo is not None else end.replace(tzinfo=UTC)
                grace_end = moment + timedelta(days=transfers.grace_days(db))
            subscription = AccessSubscription(
                id=row.id,
                plan_code=summary.plan_code,
                plan_name=summary.plan_name,
                cycle_name=summary.cycle_name,
                status=summary.status,
                price_fils=summary.next_recurring_fils,
                currency="AED",
                trial_ends_at=summary.trial_ends_at,
                current_period_end=summary.current_period_end,
                grace_ends_at=grace_end,
            )
        return AccessOut(
            state=transfers.access_state(db, tenant_id),
            ai_allowed=transfers.ai_allowed(db, tenant_id),
            operational=transfers.operational_block(db, tenant_id) is None,
            attention=transfers.attention(db, tenant_id),
            subscription=subscription,
        )


@router.post("/transfers")
async def submit_transfer(
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
    settings: Config,
    invoice_id: Annotated[uuid.UUID, Form()],
    amount_fils: Annotated[int, Form()],
    transferred_on: Annotated[str, Form()],
    idempotency_key: Annotated[str, Form()],
    receipt: Annotated[UploadFile, File()],
    bank_reference: Annotated[str, Form()] = "",
    sending_bank: Annotated[str, Form()] = "",
    note: Annotated[str, Form()] = "",
) -> dict[str, str]:
    """Stores the receipt for review. The invoice stays unpaid until an administrator approves it."""
    del principal
    tenant_id = _tenant_id(settings)
    body = await receipt.read()
    with registry.control_session(settings) as db:
        row = transfers.submit_transfer(
            db,
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            amount_fils=amount_fils,
            transferred_on=transferred_on,
            bank_reference=bank_reference,
            sending_bank=sending_bank,
            note=note,
            idempotency_key=idempotency_key,
            filename=receipt.filename or "receipt",
            body=body,
        )
        return {"id": str(row.id), "status": row.status}


@router.get("/transfers/{transfer_id}/receipt")
def own_receipt(
    transfer_id: uuid.UUID,
    _: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
    settings: Config,
) -> Response:
    tenant_id = _tenant_id(settings)
    with registry.control_session(settings) as db:
        row = transfers.receipt_bytes(db, transfer_id, tenant_id)
        return Response(content=row.body, media_type=row.content_type)


@router.post("/stripe-webhook")
async def stripe_webhook(request: Request, settings: Config) -> dict[str, bool]:
    secret = (settings.stripe_webhook_secret or "").strip()
    if not secret:
        raise ApiError(404, "billing_unavailable", "Card checkout is not configured on this server.")
    body = await request.body()
    header = request.headers.get("stripe-signature", "")
    if not billing.verify_stripe_signature(body, header, secret):
        raise ApiError(401, "invalid_signature", "The payment notice could not be verified.")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ApiError(400, "invalid_body", "The payment notice was not JSON.") from exc
    with registry.control_session(settings) as db:
        tenant_id = billing.complete_stripe_event(db, settings, payload if isinstance(payload, dict) else {})
        db.commit()
    if tenant_id is not None:
        from app.console.entitlements import publish_purchased

        publish_purchased(settings, tenant_id)
    return {"ok": True}
