"""Binds every request to a tenant from X-Tenant-Domain or the Host subdomain (client1.axizpos.com)."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import Settings
from app.core.errors import api_name, error_payload
from app.tenancy import registry
from app.tenancy.context import use_tenant

TENANT_HEADER = "x-tenant-domain"
# Reachable without a tenant: liveness, API docs, self-service signup on the bare domain, the public
# package list, the POS-company console (which opens tenant databases explicitly, never through the
# request's tenant), and media files (the tenant is in their path, so <img> tags need no header).
# Paid operations stay closed until a verified activation. Billing, sign-in, onboarding, and the
# offline sales queue stay open so a pending receipt cannot trap the store or drop queued sales.
OPERATIONAL_ALLOW = (
    "/api/v1/auth",
    "/api/v1/billing",
    "/api/v1/onboarding",
    "/api/v1/sync",
    "/api/v1/site",
)
OPEN_PATHS = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/signup",
    "/api/v1/auth/recover-store-code",
    "/api/v1/super-admin",
    "/media/",
    "/api/v1/billing/public-catalog",
    "/api/v1/site/contact",
    "/api/v1/billing/stripe-webhook",
    "/api/v1/billing/checkout/return",
    "/api/v1/downloads/latest.json",
    "/api/v1/downloads/win",
    "/api/download/installer/win",
)


def _error(request: Request, status: int, code: str, message: str) -> JSONResponse:
    payload = error_payload(code, message, api=api_name(request.method, request.url.path))
    return JSONResponse(status_code=status, content=payload)


class TenantContextMiddleware:
    """Binds the store on the request task itself.

    The previous HTTP middleware ran the endpoint on a side task, so photo storage sometimes
    saw no store and wrote the file under "default" while the gallery URL named the real store.
    """

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        if request.method == "OPTIONS" or request.url.path.startswith(OPEN_PATHS):
            await self.app(scope, receive, send)
            return
        named = request.headers.get(TENANT_HEADER)
        slug = registry.slug_from_domain(named, self.settings) if named else None
        if named and slug is None:
            await _error(request, 400, "tenant_invalid", f"'{named}' is not a tenant domain.")(scope, receive, send)
            return
        host_slug = registry.slug_from_domain(request.headers.get("host"), self.settings)
        slug = slug or host_slug or self.settings.default_tenant
        if not slug:
            await _error(request, 400, "tenant_required", "Send X-Tenant-Domain or use your store's subdomain.")(
                scope, receive, send
            )
            return
        found = registry.lookup(slug, self.settings)
        if found.tenant is None:
            await _error(request, 404, "tenant_not_found", f"No store is registered at {slug}.")(scope, receive, send)
            return
        if found.status != "active":
            await _error(request, 403, "tenant_suspended", f"{found.tenant.name} is suspended. Contact support.")(
                scope, receive, send
            )
            return
        if _paid_route(request):
            blocked = _subscription_block(found.tenant.id)
            if blocked is not None:
                payload = error_payload(
                    blocked["code"],
                    blocked["message"],
                    api=api_name(request.method, request.url.path),
                    details={"subscription_status": blocked["subscription_status"], "redirect": blocked["redirect"]},
                )
                await JSONResponse(status_code=403, content=payload)(scope, receive, send)
                return
        scope.setdefault("state", {})["tenant"] = found.tenant
        with use_tenant(found.tenant):
            await self.app(scope, receive, send)


def _paid_route(request: Request) -> bool:
    path = request.url.path
    if path.startswith(OPERATIONAL_ALLOW):
        return False
    if request.method == "GET" and path in {"/api/v1/settings", "/api/v1/stores"}:
        return False
    return path.startswith("/api/v1/")


def _subscription_block(tenant_id: str) -> dict[str, str] | None:
    import uuid

    from app.console.transfers import operational_block
    from app.tenancy import registry

    try:
        with registry.control_session() as db:
            return operational_block(db, uuid.UUID(tenant_id))
    except Exception:  # noqa: BLE001 - a control-plane failure must not be reported as an active subscription
        return {
            "code": "subscription_unavailable",
            "subscription_status": "unknown",
            "message": "Subscription access could not be confirmed. Try again.",
            "redirect": "/subscription",
        }


def install(app: FastAPI, settings: Settings) -> None:
    if not settings.tenancy_enabled:
        return
    app.add_middleware(TenantContextMiddleware, settings=settings)
