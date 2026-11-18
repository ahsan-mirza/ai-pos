"""Public hardware catalogue. No tenant and no operator token."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.console import public_catalog
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.pagination import Offset, set_total
from app.core.rate_limit import check_identity
from app.schemas.public_catalog import (
    PublicCategoryOut,
    PublicEnquiryIn,
    PublicEnquiryOut,
    PublicPackageCard,
    PublicPackageOut,
    PublicProductOut,
)
from app.tenancy import registry

router = APIRouter(prefix="/hardware", tags=["public hardware"])
Config = Annotated[Settings, Depends(get_settings)]


def _db(settings: Settings):
    if not settings.tenancy_enabled:
        raise ApiError(404, "catalogue_unavailable", "The hardware catalogue is not available on this server.")
    return registry.control_session(settings)


@router.get("/categories", response_model=list[PublicCategoryOut])
def categories(settings: Config, response: Response) -> list[PublicCategoryOut]:
    response.headers["Cache-Control"] = "no-cache"
    with _db(settings) as db:
        return public_catalog.public_categories(db)


@router.get("/products", response_model=list[PublicProductOut])
def products(
    settings: Config,
    response: Response,
    offset: Offset,
    q: Annotated[str, Query(max_length=80)] = "",
    category: Annotated[str, Query(max_length=80)] = "",
    featured: Annotated[bool | None, Query()] = None,
    sort: Annotated[str, Query(pattern=r"^(order|name|price)$")] = "order",
    limit: Annotated[int, Query(ge=1, le=48)] = 24,
) -> list[PublicProductOut]:
    response.headers["Cache-Control"] = "no-cache"
    with _db(settings) as db:
        rows, total = public_catalog.public_products(
            db, q=q, category=category, featured=featured, sort=sort, offset=offset, limit=limit
        )
        set_total(response, total)
        return rows


@router.get("/products/{slug}", response_model=PublicProductOut)
def product(slug: str, settings: Config, response: Response) -> PublicProductOut:
    response.headers["Cache-Control"] = "no-cache"
    with _db(settings) as db:
        return public_catalog.public_product(db, slug)


@router.get("/packages", response_model=list[PublicPackageCard])
def packages(
    settings: Config,
    response: Response,
    offset: Offset,
    featured: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=48)] = 24,
) -> list[PublicPackageCard]:
    response.headers["Cache-Control"] = "no-cache"
    with _db(settings) as db:
        rows, total = public_catalog.public_packages(db, featured=featured, offset=offset, limit=limit)
        set_total(response, total)
        return rows


@router.get("/packages/{slug}", response_model=PublicPackageOut)
def package(slug: str, settings: Config, response: Response) -> PublicPackageOut:
    response.headers["Cache-Control"] = "no-cache"
    with _db(settings) as db:
        return public_catalog.public_package(db, slug)


@router.post("/enquiries", response_model=PublicEnquiryOut, status_code=201)
def enquiry(payload: PublicEnquiryIn, request: Request, settings: Config) -> PublicEnquiryOut:
    check_identity(
        request,
        "hardware-enquiry",
        payload.email.strip().lower(),
        ip_limit=8,
        identity_limit=4,
        window_seconds=600,
    )
    with _db(settings) as db:
        return public_catalog.submit_enquiry(db, payload)
