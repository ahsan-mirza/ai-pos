"""Store-facing catalog, quote and go-live checkout.

The public catalog and the Stripe webhook are tenant-free and listed in OPEN_PATHS.
"""

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.console import billing
from app.core.config import Settings, get_settings
from app.core.deps import Principal, authorize
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.schemas.billing import CatalogOut, CheckoutIn, CheckoutOut, CheckoutStatus, QuoteIn, QuoteOut
from app.tenancy import registry
from app.tenancy.context import current_tenant
from app.tenancy.models import Tenant

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


def _active_catalog(found: CatalogOut) -> CatalogOut:
    return found.model_copy(
        update={
            "plans": [row for row in found.plans if row.active],
            "cycles": [row for row in found.cycles if row.active],
            "addons": [row for row in found.addons if row.active],
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
    _tenant_id(settings)
    with registry.control_session(settings) as db:
        return billing.quote_for(db, payload.plan_code, payload.cycle_code, payload.addons)


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
        return billing.create_checkout(db, settings, row, principal.user.id, payload)


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
        billing.complete_stripe_event(db, settings, payload if isinstance(payload, dict) else {})
        db.commit()
    return {"ok": True}
