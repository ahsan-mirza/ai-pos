"""Store-facing catalog, quote and go-live checkout.

The public catalog and the Stripe webhook are tenant-free and listed in OPEN_PATHS.
"""

import json
import uuid
from datetime import UTC, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select

from app.console import billing, commercial_payments, subscription_changes, transfers
from app.core.config import Settings, get_settings
from app.core.deps import Principal, authorize, get_principal
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.schemas.billing import (
    AccessOut,
    AccessSubscription,
    CatalogOut,
    ChangeCheckoutOut,
    ChangeCreateIn,
    ChangeOut,
    ChangePage,
    CheckoutIn,
    CheckoutOut,
    CheckoutStatus,
    CommercialPaymentIn,
    CommercialPaymentOut,
    EcOrderIn,
    FeatureAccessList,
    MarketplaceOut,
    PaymentMethodOut,
    PromotionalTrialOut,
    QuoteIn,
    QuoteOut,
    UsageOut,
)
from app.schemas.hardware import EcAssignIn, EcRegisterIn
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
    """Published rows only. Operator price notes stay off the public payload."""
    return found.model_copy(
        update={
            "plans": [row for row in found.plans if row.active],
            "cycles": [row for row in found.cycles if row.active],
            "addons": [
                row.model_copy(update={"price_history": []})
                for row in found.addons
                if row.active and row.listing.publication == "published"
            ],
            "fees": [row for row in found.fees if row.active],
        }
    )


@router.get("/public-catalog", response_model=CatalogOut)
def public_catalog(response: Response, settings: Config) -> CatalogOut:
    """Active packages, cycles, add-ons, and fees for the marketing site. No store session and no tenant."""
    response.headers["Cache-Control"] = "public, max-age=60"
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
        return found.model_copy(update={"plans": [row for row in found.plans if row.active]})


@router.get("/ec-machines")
def ec_machines(
    _: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))], settings: Config
) -> list:
    _tenant_id(settings)
    with registry.control_session(settings) as db:
        return hardware_items(db)


def hardware_items(db):
    from app.console import hardware as hardware_catalog

    return hardware_catalog.list_ec_items(db)


@router.post("/ec-quote", response_model=QuoteOut)
def ec_quote(
    payload: EcOrderIn,
    _: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
    settings: Config,
) -> QuoteOut:
    tenant_id = _tenant_id(settings)
    with registry.control_session(settings) as db:
        tenant = db.get(Tenant, tenant_id)
        if tenant is None:
            raise ApiError(404, "tenant_not_found", "This store is not registered.")
        return billing.quote_ec_machines(db, tenant, payload.hardware, _stores(settings, tenant_id))


@router.post("/ec-checkout", response_model=CheckoutOut)
def ec_checkout(
    payload: EcOrderIn,
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
    settings: Config,
) -> CheckoutOut:
    if principal.user is None:
        raise ApiError(403, "business_wide_only", "Only a business-wide admin can buy a terminal.")
    tenant_id = _tenant_id(settings)
    with registry.control_session(settings) as db:
        tenant = db.get(Tenant, tenant_id)
        if tenant is None:
            raise ApiError(404, "tenant_not_found", "This store is not registered.")
        return billing.create_ec_checkout(
            db, tenant, principal.user.id, payload.hardware, _stores(settings, tenant_id)
        )


@router.get("/ec-orders")
def ec_orders(
    _: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))], settings: Config
) -> list:
    tenant_id = _tenant_id(settings)
    with registry.control_session(settings) as db:
        from app.console import hardware as hardware_catalog

        return hardware_catalog.orders_for_tenant(db, tenant_id)


def _register_rows(settings: Settings, tenant_id: uuid.UUID) -> list[dict[str, object]]:
    from app.console.entitlements import tenant_session
    from app.models.device import Device

    with registry.control_session(settings) as db:
        tenant = db.get(Tenant, tenant_id)
        if tenant is None:
            return []
    with tenant_session(tenant, settings) as store_db:
        return [
            {
                "id": row.id,
                "name": row.name,
                "code": row.code,
                "store_id": row.store_id,
                "active": row.revoked_at is None,
            }
            for row in store_db.scalars(select(Device))
        ]


def _registers(settings: Settings, tenant_id: uuid.UUID) -> dict[uuid.UUID, tuple[uuid.UUID, bool]]:
    return {row["id"]: (row["store_id"], bool(row["active"])) for row in _register_rows(settings, tenant_id)}  # type: ignore[misc]


@router.get("/ec-registers")
def ec_registers(
    _: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))], settings: Config
) -> list[dict[str, object]]:
    return _register_rows(settings, _tenant_id(settings))


@router.get("/ec-devices")
def ec_devices(
    _: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))], settings: Config
) -> list:
    tenant_id = _tenant_id(settings)
    with registry.control_session(settings) as db:
        from app.console import hardware as hardware_catalog

        return hardware_catalog.ec_devices_for_tenant(db, tenant_id)


@router.post("/ec-devices/{assignment_id}/register")
def ec_register(
    assignment_id: uuid.UUID,
    payload: EcRegisterIn,
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
    settings: Config,
):
    if principal.user is None:
        raise ApiError(403, "business_wide_only", "Only a business-wide admin can register a terminal.")
    tenant_id = _tenant_id(settings)
    with registry.control_session(settings) as db:
        from app.console import hardware as hardware_catalog

        return hardware_catalog.confirm_ec_registration(db, tenant_id, assignment_id, payload, principal.user.id)


@router.put("/ec-devices/{assignment_id}/assignment")
def ec_assign(
    assignment_id: uuid.UUID,
    payload: EcAssignIn,
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
    settings: Config,
):
    if principal.user is None:
        raise ApiError(403, "business_wide_only", "Only a business-wide admin can assign a terminal.")
    tenant_id = _tenant_id(settings)
    with registry.control_session(settings) as db:
        from app.console import hardware as hardware_catalog

        return hardware_catalog.assign_ec_register(
            db,
            tenant_id,
            assignment_id,
            payload,
            stores=_stores(settings, tenant_id),
            registers=_registers(settings, tenant_id),
            actor_id=principal.user.id,
        )


@router.delete("/ec-devices/{assignment_id}/assignment")
def ec_unassign(
    assignment_id: uuid.UUID,
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
    settings: Config,
):
    if principal.user is None:
        raise ApiError(403, "business_wide_only", "Only a business-wide admin can unassign a terminal.")
    tenant_id = _tenant_id(settings)
    with registry.control_session(settings) as db:
        from app.console import hardware as hardware_catalog

        return hardware_catalog.unassign_ec_register(db, tenant_id, assignment_id, principal.user.id)


@router.get("/ec-devices/{assignment_id}/readiness")
def ec_device_readiness(
    assignment_id: uuid.UUID,
    _: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
    settings: Config,
):
    tenant_id = _tenant_id(settings)
    with registry.control_session(settings) as db:
        from app.console import hardware as hardware_catalog

        return hardware_catalog.ec_readiness(db, tenant_id, assignment_id)


@router.post("/quote", response_model=QuoteOut)
def quote(
    payload: QuoteIn, _: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))], settings: Config
) -> QuoteOut:
    tenant_id = _tenant_id(settings)
    stores = _stores(settings, tenant_id)
    with registry.control_session(settings) as db:
        tenant = db.get(Tenant, tenant_id)
        assert tenant is not None
        return billing.quote_for(
            db,
            payload.plan_code,
            payload.cycle_code,
            payload.addons,
            payload.hardware,
            stores,
            country=billing._store_country(settings, tenant),
            onboarding=payload.onboarding,
            tenant_id=tenant.id,
        )


@router.get("/payment-methods", response_model=list[PaymentMethodOut])
def payment_methods(
    _: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
    settings: Config,
    purpose: str = "PLUGIN_PURCHASE",
) -> list[PaymentMethodOut]:
    with registry.control_session(settings) as db:
        return [
            PaymentMethodOut(**row)
            for row in commercial_payments.list_methods(
                db, purpose, sandbox_card=commercial_payments.sandbox_card_allowed(settings)
            )
        ]


@router.get("/addons/{code}/quote", response_model=QuoteOut)
def addon_quote(
    code: str,
    _: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
    settings: Config,
) -> QuoteOut:
    tenant_id = _tenant_id(settings)
    with registry.control_session(settings) as db:
        tenant = db.get(Tenant, tenant_id)
        assert tenant is not None
        return billing.quote_addon(db, settings, tenant, code)


@router.post("/payments", response_model=CommercialPaymentOut)
def start_payment(
    payload: CommercialPaymentIn,
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
    settings: Config,
) -> CommercialPaymentOut:
    if principal.user is None:
        raise ApiError(403, "business_wide_only", "Only a business-wide admin can buy an add-on.")
    tenant_id = _tenant_id(settings)
    with registry.control_session(settings) as db:
        tenant = db.get(Tenant, tenant_id)
        assert tenant is not None
        found = commercial_payments.start_plugin_payment(
            db,
            settings,
            tenant,
            principal.user.id,
            purpose_type=payload.purpose_type,
            addon_code=payload.purpose_ref,
            method_code=payload.method_code,
            idempotency_key=payload.idempotency_key,
            scenario=payload.scenario,
        )
        return CommercialPaymentOut(**found)


@router.get("/payment-environment")
def payment_environment(
    _: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
    settings: Config,
) -> dict[str, object]:
    sandbox = commercial_payments.sandbox_card_allowed(settings)
    return {
        "sandbox": sandbox,
        "live_card": False,
        "banner": "Test payments only. No real money will be charged." if sandbox else "",
    }


@router.post("/sandbox-events", response_model=CommercialPaymentOut)
async def sandbox_event(request: Request, settings: Config) -> CommercialPaymentOut:
    body = await request.body()
    with registry.control_session(settings) as db:
        found = commercial_payments.accept_sandbox_event(
            db,
            settings,
            body,
            request.headers.get("x-axiz-sandbox-signature"),
            request.headers.get("x-axiz-sandbox-timestamp"),
        )
        return CommercialPaymentOut(**found)


@router.get("/payments/{payment_id}", response_model=CommercialPaymentOut)
def payment_status(
    payment_id: uuid.UUID,
    _: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
    settings: Config,
) -> CommercialPaymentOut:
    tenant_id = _tenant_id(settings)
    with registry.control_session(settings) as db:
        return CommercialPaymentOut(**commercial_payments.payment_for_tenant(db, tenant_id, payment_id))


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


def _business_wide(principal: Principal) -> None:
    if principal.user is None or principal.store_id is not None:
        raise ApiError(403, "business_wide_only", "Only a business-wide admin can change the subscription.")


@router.post("/subscription-changes", response_model=ChangeOut)
def create_subscription_change(
    payload: ChangeCreateIn,
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
    settings: Config,
) -> ChangeOut:
    _business_wide(principal)
    assert principal.user is not None
    tenant_id = _tenant_id(settings)
    stores = _stores(settings, tenant_id)
    with registry.control_session(settings) as db:
        tenant = db.get(Tenant, tenant_id)
        assert tenant is not None
        row = subscription_changes.create_request(
            db,
            tenant,
            payload.plan_code,
            payload.cycle_code,
            principal.user.id,
            stores=stores,
            country=billing._store_country(settings, tenant),
            onboarding=payload.onboarding,
        )
        return subscription_changes.present(db, row)


@router.get("/subscription-changes", response_model=ChangePage)
def list_subscription_changes(
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
    settings: Config,
    status: Annotated[str | None, Query(max_length=32)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ChangePage:
    _business_wide(principal)
    with registry.control_session(settings) as db:
        rows, total = subscription_changes.list_requests(
            db, _tenant_id(settings), status=status, limit=limit, offset=offset
        )
        return ChangePage(items=[subscription_changes.present(db, row) for row in rows], total=total)


@router.get("/subscription-changes/{request_id}", response_model=ChangeOut)
def get_subscription_change(
    request_id: uuid.UUID,
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
    settings: Config,
) -> ChangeOut:
    _business_wide(principal)
    with registry.control_session(settings) as db:
        return subscription_changes.present(db, subscription_changes.get_request(db, _tenant_id(settings), request_id))


@router.post("/subscription-changes/{request_id}/cancel", response_model=ChangeOut)
def cancel_subscription_change(
    request_id: uuid.UUID,
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
    settings: Config,
) -> ChangeOut:
    _business_wide(principal)
    assert principal.user is not None
    with registry.control_session(settings) as db:
        row = subscription_changes.cancel_request(db, _tenant_id(settings), request_id, principal.user.id)
        return subscription_changes.present(db, row)


@router.post("/subscription-changes/{request_id}/checkout", response_model=ChangeCheckoutOut)
def checkout_subscription_change(
    request_id: uuid.UUID,
    payload: CheckoutIn,
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
    settings: Config,
) -> ChangeCheckoutOut:
    _business_wide(principal)
    assert principal.user is not None
    tenant_id = _tenant_id(settings)
    stores = _stores(settings, tenant_id)
    with registry.control_session(settings) as db:
        tenant = db.get(Tenant, tenant_id)
        assert tenant is not None
        row, checkout = subscription_changes.issue_invoice(
            db,
            settings,
            tenant,
            principal.user.id,
            request_id,
            payload,
            stores,
            billing._store_country(settings, tenant),
        )
        return ChangeCheckoutOut(request=subscription_changes.present(db, row), checkout=checkout)


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


@router.get("/features", response_model=FeatureAccessList)
def feature_access(
    principal: Annotated[Principal, Depends(get_principal)],
    settings: Config,
) -> FeatureAccessList:
    """Published plan and add-on access for this store. The portal modal reads this and does not decide it."""
    del principal
    from app.console.feature_access import explain
    from app.services.settings_service import (
        effective_promotional_keys,
        effective_purchased_keys,
        load_settings,
        managed_of,
    )

    tenant_id = _tenant_id(settings)
    with registry.control_session(settings) as db:
        tenant = db.get(Tenant, tenant_id)
        if tenant is None:
            raise ApiError(404, "tenant_not_found", "This store is not registered.")
        from app.console.entitlements import tenant_session

        with tenant_session(tenant, settings) as store:
            row = load_settings(store)
            profile = row.business_profile
            purchased = effective_purchased_keys(row)
            promotional = effective_promotional_keys(row)
            managed = managed_of(row)
            country = (row.country or "").strip().upper() or None
        return FeatureAccessList(
            features=explain(
                db,
                tenant,
                profile=profile,
                purchased=purchased,
                promotional=promotional,
                managed=managed,
                country=country,
            )
        )


@router.get("/usage", response_model=UsageOut)
def usage_status(principal: Annotated[Principal, Depends(get_principal)], settings: Config) -> UsageOut:
    """Actual resource counts for this store. A tenant id in the query string is ignored."""
    del principal
    tenant_id = _tenant_id(settings)
    from app.console.entitlements import tenant_session
    from app.console.usage import usage_for

    with registry.control_session(settings) as control:
        tenant = control.get(Tenant, tenant_id)
        if tenant is None:
            raise ApiError(404, "tenant_not_found", "This store is not registered.")
        with tenant_session(tenant, settings) as store:
            return usage_for(control, tenant_id, store)


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
        from app.console import promotional_trial
        from app.console.billing import _business_profile

        profile = _business_profile(settings, tenant) if tenant is not None else ""
        trial = promotional_trial.present(db, tenant, profile) if tenant is not None else None
        return AccessOut(
            state=transfers.access_state(db, tenant_id),
            ai_allowed=transfers.ai_allowed(db, tenant_id),
            operational=transfers.operational_block(db, tenant_id) is None,
            attention=transfers.attention(db, tenant_id),
            subscription=subscription,
            promotional_trial=trial,
        )


@router.get("/promotional-trial", response_model=PromotionalTrialOut)
def promotional_trial_status(
    _: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))], settings: Config
) -> PromotionalTrialOut:
    tenant_id = _tenant_id(settings)
    with registry.control_session(settings) as db:
        tenant = db.get(Tenant, tenant_id)
        if tenant is None:
            raise ApiError(404, "tenant_not_found", "This store is not registered.")
        from app.console import promotional_trial
        from app.console.billing import _business_profile

        return promotional_trial.present(db, tenant, _business_profile(settings, tenant))


@router.post("/promotional-trial", response_model=PromotionalTrialOut)
def start_promotional_trial(
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))], settings: Config
) -> PromotionalTrialOut:
    """Starts the one Pro AI promotion. The base subscription and invoices stay as they are."""
    if principal.user is None:
        raise ApiError(403, "business_wide_only", "Only a business-wide admin can start the trial.")
    tenant_id = _tenant_id(settings)
    from app.console import promotional_trial
    from app.console.billing import _business_profile

    with registry.control_session(settings) as db:
        tenant = db.get(Tenant, tenant_id)
        if tenant is None:
            raise ApiError(404, "tenant_not_found", "This store is not registered.")
        row = promotional_trial.start(db, tenant, principal.user.id)
        profile = _business_profile(settings, tenant)
        expires_at = row.expires_at
        active = promotional_trial.effective_status(row) == "active"
        keys = promotional_trial._module_keys(db, profile) if active else []
        db.commit()
        promotional_trial.publish_window(settings, tenant, keys, expires_at)
        return promotional_trial.present(db, tenant, profile)


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
