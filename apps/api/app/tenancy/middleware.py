"""Binds every request to a tenant from X-Tenant-Domain or the Host subdomain (client1.qios.ae)."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.core.config import Settings
from app.tenancy import registry
from app.tenancy.context import use_tenant

TENANT_HEADER = "x-tenant-domain"
# Reachable without a tenant: liveness, API docs, self-service signup on the bare domain, the POS-company
# console (which opens tenant databases explicitly, never through the request's tenant), and media files (the
# tenant is in their path, so <img> tags need no header).
OPEN_PATHS = ("/health", "/docs", "/redoc", "/openapi.json", "/api/v1/signup", "/api/v1/super-admin", "/media/")


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def install(app: FastAPI, settings: Settings) -> None:
    if not settings.tenancy_enabled:
        return

    @app.middleware("http")
    async def tenant_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method == "OPTIONS" or request.url.path.startswith(OPEN_PATHS):
            return await call_next(request)
        named = request.headers.get(TENANT_HEADER)
        slug = registry.slug_from_domain(named, settings) if named else None
        if named and slug is None:
            return _error(400, "tenant_invalid", f"'{named}' is not a tenant domain.")
        slug = slug or registry.slug_from_domain(request.headers.get("host"), settings) or settings.default_tenant
        if not slug:
            return _error(400, "tenant_required", "Send X-Tenant-Domain or use your store's subdomain.")
        found = registry.lookup(slug, settings)
        if found.tenant is None:
            return _error(404, "tenant_not_found", f"No store is registered at {slug}.")
        if found.status != "active":
            return _error(403, "tenant_suspended", f"{found.tenant.name} is suspended. Contact support.")
        request.state.tenant = found.tenant
        with use_tenant(found.tenant):
            return await call_next(request)
