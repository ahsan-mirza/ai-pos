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
        scope.setdefault("state", {})["tenant"] = found.tenant
        with use_tenant(found.tenant):
            await self.app(scope, receive, send)


def install(app: FastAPI, settings: Settings) -> None:
    if not settings.tenancy_enabled:
        return
    app.add_middleware(TenantContextMiddleware, settings=settings)
