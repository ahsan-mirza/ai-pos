import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from app.core import audit_context
from app.core.config import Settings, get_settings
from app.core.errors import (
    ApiError,
    api_name,
    error_payload,
    field_error_map,
    http_error,
    unhandled_error,
    validation_message,
)
from app.core.pagination import TOTAL_COUNT_HEADER
from app.jobs import scheduler
from app.routers.media import router as media_router
from app.routers.repair_public import router as repair_public_router
from app.routers.signup import router as signup_router
from app.routers.super_admin import router as super_admin_router
from app.routers.v1 import api_router
from app.routers.v1.downloads import latest_windows_file
from app.services import audit as _audit_listeners  # noqa: F401  registers the ORM audit listeners
from app.tenancy import middleware as tenancy_middleware
from app.websockets.rooms import bind_loop as bind_room_loop
from app.websockets.table_sync import bind_loop

logger = logging.getLogger("ai_pos")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    settings = get_settings()
    for name in ("jwt_secret", "pin_salt", "encryption_secret", "api_key", "admin_password"):
        if str(getattr(settings, name)).startswith("change-me"):
            logger.warning("%s is still a placeholder value.", name.upper())
    loop = asyncio.get_running_loop()
    bind_loop(loop)
    bind_room_loop(loop)
    scheduler.start(settings)
    try:
        yield
    finally:
        scheduler.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AI POS API", version="0.1.0", lifespan=lifespan)
    # Added before CORS so CORS wraps it: tenant errors still carry CORS headers for the browser.
    tenancy_middleware.install(app, settings)

    # Starlette answers uncaught exceptions outside CORS, so browsers would only see a failed fetch.
    @app.middleware("http")
    async def unhandled_errors(request: Request, call_next):  # type: ignore[no-untyped-def]
        try:
            return await call_next(request)
        except Exception as exc:
            logger.exception("Unhandled error on %s %s", request.method, request.url.path)
            status, body = unhandled_error(
                exc,
                debug=settings.app_env != "production",
                api=api_name(request.method, request.url.path),
            )
            return JSONResponse(status_code=status, content=body)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=settings.tenant_origin_regex,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[TOTAL_COUNT_HEADER],
    )

    @app.middleware("http")
    async def audit_request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        token = audit_context.begin(
            audit_context.RequestContext(
                method=request.method,
                path=request.url.path,
                ip_address=request.client.host if request.client else None,
                client_device=audit_context.detect_device(
                    request.headers.get("x-client-device"), request.headers.get("user-agent")
                ),
            )
        )
        try:
            return await call_next(request)
        finally:
            audit_context.end(token)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith(("/api/v1/auth", "/api/v1/super-admin")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(
                exc.code,
                exc.message,
                api=api_name(request.method, request.url.path),
                details=exc.details,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = jsonable_encoder(exc.errors())
        return JSONResponse(
            status_code=422,
            content=error_payload(
                "invalid_request",
                validation_message(details),
                api=api_name(request.method, request.url.path),
                details=details,
                field_errors=field_error_map(details),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, message = http_error(exc.status_code, exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(code, message, api=api_name(request.method, request.url.path)),
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/download/installer/win", include_in_schema=False)
    def download_windows_installer(settings: Annotated[Settings, Depends(get_settings)]) -> FileResponse:
        return latest_windows_file(settings)

    app.include_router(api_router, prefix="/api/v1")
    app.include_router(repair_public_router)
    app.include_router(media_router)
    app.include_router(signup_router, prefix="/api/v1/signup", tags=["signup"])
    app.include_router(super_admin_router, prefix="/api/v1/super-admin", tags=["console"])
    return app


app = create_app()
