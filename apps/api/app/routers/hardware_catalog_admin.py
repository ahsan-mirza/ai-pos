"""Console management for the public hardware catalogue. Operator token required."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile

from app.console import public_catalog
from app.console.security import CurrentOperator, OperatorPrincipal
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.pagination import Offset, set_total
from app.schemas.public_catalog import (
    CategoryIn,
    CategoryOut,
    EnquiryNoteIn,
    EnquiryOut,
    EnquiryStatusIn,
    ImageOrderIn,
    OverviewOut,
    PackageIn,
    PackageOut,
    PlanRefOut,
    ProductIn,
    ProductOut,
    ReasonIn,
)
from app.tenancy import registry

router = APIRouter(prefix="/hardware-catalog", tags=["hardware catalog"])
Config = Annotated[Settings, Depends(get_settings)]


def catalog_admin(operator: CurrentOperator) -> OperatorPrincipal:
    if not operator.is_admin:
        raise ApiError(403, "forbidden", "Only a console admin can change the hardware catalogue.")
    return operator


CatalogAdmin = Annotated[OperatorPrincipal, Depends(catalog_admin)]


def _db(settings: Settings):
    return registry.control_session(settings)


@router.get("/overview", response_model=OverviewOut)
def overview(_: CurrentOperator, settings: Config) -> OverviewOut:
    with _db(settings) as db:
        return public_catalog.overview(db)


@router.get("/plans", response_model=list[PlanRefOut])
def plans(_: CurrentOperator, settings: Config) -> list[PlanRefOut]:
    with _db(settings) as db:
        return public_catalog.list_plans(db)


@router.get("/categories", response_model=list[CategoryOut])
def categories(_: CurrentOperator, settings: Config) -> list[CategoryOut]:
    with _db(settings) as db:
        return public_catalog.list_categories(db)


@router.post("/categories", response_model=CategoryOut, status_code=201)
def category_create(payload: CategoryIn, operator: CatalogAdmin, settings: Config) -> CategoryOut:
    with _db(settings) as db:
        return public_catalog.create_category(db, operator, payload)


@router.put("/categories/{category_id}", response_model=CategoryOut)
def category_update(
    category_id: uuid.UUID, payload: CategoryIn, operator: CatalogAdmin, settings: Config
) -> CategoryOut:
    with _db(settings) as db:
        return public_catalog.update_category(db, operator, category_id, payload)


@router.delete("/categories/{category_id}", status_code=204)
def category_delete(
    category_id: uuid.UUID,
    operator: CatalogAdmin,
    settings: Config,
    reason: Annotated[str, Query(min_length=3, max_length=500)],
) -> Response:
    with _db(settings) as db:
        public_catalog.delete_category(db, operator, category_id, reason)
    return Response(status_code=204)


@router.post("/categories/{category_id}/image", response_model=CategoryOut)
async def category_image(
    category_id: uuid.UUID,
    operator: CatalogAdmin,
    settings: Config,
    file: Annotated[UploadFile, File()],
    reason: Annotated[str, Form(min_length=3, max_length=500)],
    alt: Annotated[str, Form(max_length=160)] = "",
) -> CategoryOut:
    data = await file.read()
    with _db(settings) as db:
        return public_catalog.add_category_image(
            db, operator, category_id, data, file.content_type, file.filename or "", alt, reason
        )


@router.get("/products", response_model=list[ProductOut])
def products(
    _: CurrentOperator,
    settings: Config,
    response: Response,
    offset: Offset,
    q: Annotated[str, Query(max_length=80)] = "",
    status: Annotated[str, Query(pattern=r"^(|published|draft|archived)$")] = "",
    category_id: Annotated[uuid.UUID | None, Query()] = None,
    sort: Annotated[str, Query(pattern=r"^(updated|name|price|order)$")] = "updated",
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[ProductOut]:
    with _db(settings) as db:
        rows, total = public_catalog.list_products(
            db, q=q, status=status, category_id=category_id, sort=sort, offset=offset, limit=limit
        )
        set_total(response, total)
        return rows


@router.post("/products", response_model=ProductOut, status_code=201)
def product_create(payload: ProductIn, operator: CatalogAdmin, settings: Config) -> ProductOut:
    with _db(settings) as db:
        return public_catalog.create_product(db, operator, payload)


@router.get("/products/{product_id}", response_model=ProductOut)
def product_get(product_id: uuid.UUID, _: CurrentOperator, settings: Config) -> ProductOut:
    with _db(settings) as db:
        return public_catalog.product_out(db, public_catalog._product(db, product_id))


@router.put("/products/{product_id}", response_model=ProductOut)
def product_update(product_id: uuid.UUID, payload: ProductIn, operator: CatalogAdmin, settings: Config) -> ProductOut:
    with _db(settings) as db:
        return public_catalog.update_product(db, operator, product_id, payload)


@router.post("/products/{product_id}/publish", response_model=ProductOut)
def product_publish(product_id: uuid.UUID, payload: ReasonIn, operator: CatalogAdmin, settings: Config) -> ProductOut:
    with _db(settings) as db:
        return public_catalog.publish_product(db, operator, product_id, payload.reason)


@router.post("/products/{product_id}/unpublish", response_model=ProductOut)
def product_unpublish(product_id: uuid.UUID, payload: ReasonIn, operator: CatalogAdmin, settings: Config) -> ProductOut:
    with _db(settings) as db:
        return public_catalog.unpublish_product(db, operator, product_id, payload.reason)


@router.post("/products/{product_id}/archive", response_model=ProductOut)
def product_archive(product_id: uuid.UUID, payload: ReasonIn, operator: CatalogAdmin, settings: Config) -> ProductOut:
    with _db(settings) as db:
        return public_catalog.archive_product(db, operator, product_id, payload.reason)


@router.delete("/products/{product_id}", status_code=204)
def product_delete(
    product_id: uuid.UUID,
    operator: CatalogAdmin,
    settings: Config,
    reason: Annotated[str, Query(min_length=3, max_length=500)],
) -> Response:
    with _db(settings) as db:
        public_catalog.delete_product(db, operator, product_id, reason)
    return Response(status_code=204)


@router.post("/products/{product_id}/images", response_model=ProductOut, status_code=201)
async def product_image(
    product_id: uuid.UUID,
    operator: CatalogAdmin,
    settings: Config,
    file: Annotated[UploadFile, File()],
    reason: Annotated[str, Form(min_length=3, max_length=500)],
    alt: Annotated[str, Form(max_length=160)] = "",
) -> ProductOut:
    data = await file.read()
    with _db(settings) as db:
        return public_catalog.add_product_image(
            db, operator, product_id, data, file.content_type, file.filename or "", alt, reason
        )


@router.put("/products/{product_id}/images/order", status_code=204)
def product_image_order(
    product_id: uuid.UUID, payload: ImageOrderIn, operator: CatalogAdmin, settings: Config
) -> Response:
    with _db(settings) as db:
        public_catalog._product(db, product_id)
        public_catalog.reorder_images(db, operator, "product", product_id, payload.ids, payload.reason)
    return Response(status_code=204)


@router.get("/packages", response_model=list[PackageOut])
def packages(
    _: CurrentOperator,
    settings: Config,
    response: Response,
    offset: Offset,
    q: Annotated[str, Query(max_length=80)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[PackageOut]:
    with _db(settings) as db:
        rows, total = public_catalog.list_packages(db, q=q, offset=offset, limit=limit)
        set_total(response, total)
        return rows


@router.post("/packages", response_model=PackageOut, status_code=201)
def package_create(payload: PackageIn, operator: CatalogAdmin, settings: Config) -> PackageOut:
    with _db(settings) as db:
        return public_catalog.create_package(db, operator, payload)


@router.get("/packages/{package_id}", response_model=PackageOut)
def package_get(package_id: uuid.UUID, _: CurrentOperator, settings: Config) -> PackageOut:
    with _db(settings) as db:
        return public_catalog.package_out(db, public_catalog._package(db, package_id))


@router.put("/packages/{package_id}", response_model=PackageOut)
def package_update(package_id: uuid.UUID, payload: PackageIn, operator: CatalogAdmin, settings: Config) -> PackageOut:
    with _db(settings) as db:
        return public_catalog.update_package(db, operator, package_id, payload)


@router.post("/packages/{package_id}/publish", response_model=PackageOut)
def package_publish(package_id: uuid.UUID, payload: ReasonIn, operator: CatalogAdmin, settings: Config) -> PackageOut:
    with _db(settings) as db:
        return public_catalog.publish_package(db, operator, package_id, payload.reason)


@router.post("/packages/{package_id}/unpublish", response_model=PackageOut)
def package_unpublish(package_id: uuid.UUID, payload: ReasonIn, operator: CatalogAdmin, settings: Config) -> PackageOut:
    with _db(settings) as db:
        return public_catalog.unpublish_package(db, operator, package_id, payload.reason)


@router.delete("/packages/{package_id}", status_code=204)
def package_delete(
    package_id: uuid.UUID,
    operator: CatalogAdmin,
    settings: Config,
    reason: Annotated[str, Query(min_length=3, max_length=500)],
) -> Response:
    with _db(settings) as db:
        public_catalog.delete_package(db, operator, package_id, reason)
    return Response(status_code=204)


@router.post("/packages/{package_id}/images", response_model=PackageOut, status_code=201)
async def package_image(
    package_id: uuid.UUID,
    operator: CatalogAdmin,
    settings: Config,
    file: Annotated[UploadFile, File()],
    reason: Annotated[str, Form(min_length=3, max_length=500)],
    alt: Annotated[str, Form(max_length=160)] = "",
) -> PackageOut:
    data = await file.read()
    with _db(settings) as db:
        return public_catalog.add_package_image(
            db, operator, package_id, data, file.content_type, file.filename or "", alt, reason
        )


@router.put("/packages/{package_id}/images/order", status_code=204)
def package_image_order(
    package_id: uuid.UUID, payload: ImageOrderIn, operator: CatalogAdmin, settings: Config
) -> Response:
    with _db(settings) as db:
        public_catalog._package(db, package_id)
        public_catalog.reorder_images(db, operator, "package", package_id, payload.ids, payload.reason)
    return Response(status_code=204)


@router.delete("/images/{image_id}", status_code=204)
def image_delete(
    image_id: uuid.UUID,
    operator: CatalogAdmin,
    settings: Config,
    reason: Annotated[str, Query(min_length=3, max_length=500)],
) -> Response:
    with _db(settings) as db:
        public_catalog.delete_image(db, operator, image_id, reason)
    return Response(status_code=204)


@router.get("/enquiries", response_model=list[EnquiryOut])
def enquiries(
    _: CurrentOperator,
    settings: Config,
    response: Response,
    offset: Offset,
    q: Annotated[str, Query(max_length=80)] = "",
    status: Annotated[str, Query(max_length=16)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[EnquiryOut]:
    with _db(settings) as db:
        rows, total = public_catalog.list_enquiries(db, q=q, status=status, offset=offset, limit=limit)
        set_total(response, total)
        return rows


@router.get("/enquiries/{enquiry_id}", response_model=EnquiryOut)
def enquiry_get(enquiry_id: uuid.UUID, _: CurrentOperator, settings: Config) -> EnquiryOut:
    with _db(settings) as db:
        return public_catalog.get_enquiry(db, enquiry_id)


@router.put("/enquiries/{enquiry_id}", response_model=EnquiryOut)
def enquiry_status(
    enquiry_id: uuid.UUID, payload: EnquiryStatusIn, operator: CurrentOperator, settings: Config
) -> EnquiryOut:
    with _db(settings) as db:
        return public_catalog.set_enquiry_status(db, operator, enquiry_id, payload)


@router.post("/enquiries/{enquiry_id}/notes", response_model=EnquiryOut, status_code=201)
def enquiry_note(
    enquiry_id: uuid.UUID, payload: EnquiryNoteIn, operator: CurrentOperator, settings: Config
) -> EnquiryOut:
    with _db(settings) as db:
        return public_catalog.add_note(db, operator, enquiry_id, payload)
