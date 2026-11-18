"""Public hardware catalogue on the registry session. Prices stay integer fils.

The configured package price is never rewritten from component prices. Savings are reported
only when every required component has an AED display price and that sum is higher.
"""

import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.console.security import OperatorPrincipal, audit_operator
from app.core.config import get_settings
from app.core.errors import ApiError
from app.schemas.public_catalog import (
    CategoryIn,
    CategoryOut,
    EnquiryNoteIn,
    EnquiryNoteOut,
    EnquiryOut,
    EnquiryStatusIn,
    ImageOut,
    OverviewOut,
    PackageIn,
    PackageItemIn,
    PackageItemOut,
    PackageOut,
    PlanRefOut,
    ProductIn,
    ProductOut,
    PublicCategoryOut,
    PublicComponentOut,
    PublicEnquiryIn,
    PublicEnquiryOut,
    PublicImageOut,
    PublicPackageCard,
    PublicPackageOut,
    PublicPlanOut,
    PublicProductOut,
    SpecIn,
)
from app.services import media_storage
from app.services.product_image_service import CONTENT_TYPES, FULL_PX, MAX_BYTES, THUMB_PX, _decode, _encode
from app.tenancy.models import BillingPlan, Operator
from app.tenancy.public_hardware import (
    PublicHardwareCategory,
    PublicHardwareEnquiry,
    PublicHardwareEnquiryNote,
    PublicHardwareImage,
    PublicHardwarePackage,
    PublicHardwarePackageItem,
    PublicHardwareProduct,
)

PLATFORM = "platform"
MAX_IMAGES = 8
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PHONE = re.compile(r"^\+[1-9][0-9]{6,14}$")
DUPLICATE_WINDOW = timedelta(minutes=10)


def component_value(
    rows: list[tuple[int, int | None, str, bool]], currency: str, package_price: int | None
) -> tuple[int | None, int | None]:
    """Required-component total and savings. None when a price or currency is missing, or there is no saving."""
    total = 0
    for quantity, price, item_currency, optional in rows:
        if optional:
            continue
        if price is None or item_currency != currency:
            return None, None
        total += quantity * price
    if package_price is None or total <= package_price:
        return total, None
    return total, total - package_price


def _slug(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")[:80].strip("-")
    if SLUG.fullmatch(cleaned or ""):
        return cleaned
    base = re.sub(r"[^a-z0-9]+", "-", fallback.strip().lower()).strip("-")[:80].strip("-")
    if not SLUG.fullmatch(base or ""):
        raise ApiError(422, "slug", "Use a short name made of letters, numbers, and hyphens.")
    return base


def _unique_slug(db: Session, model, slug: str, current: uuid.UUID | None = None) -> str:
    candidate = slug
    suffix = 2
    while True:
        found = db.scalar(select(model.id).where(model.slug == candidate))
        if found is None or found == current:
            return candidate
        candidate = f"{slug[:70].rstrip('-')}-{suffix}"
        suffix += 1
        if suffix > 50:
            raise ApiError(409, "duplicate_slug", "Choose a different name.")


def _url(key: str | None) -> str | None:
    if not key:
        return None
    return f"{get_settings().public_base_url.rstrip('/')}/media/{PLATFORM}/{key}"


def _specs(raw: list | None) -> list[SpecIn]:
    found = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        value = str(item.get("value") or "").strip()
        if label and value:
            found.append(SpecIn(label=label[:80], value=value[:240]))
    return found


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "conflict", "That catalogue value is already in use.") from exc


def _category(db: Session, category_id: uuid.UUID) -> PublicHardwareCategory:
    row = db.get(PublicHardwareCategory, category_id)
    if row is None:
        raise ApiError(422, "unknown_category", "Choose a hardware category.")
    return row


def _product(db: Session, product_id: uuid.UUID) -> PublicHardwareProduct:
    row = db.get(PublicHardwareProduct, product_id)
    if row is None:
        raise ApiError(404, "not_found", "That product does not exist.")
    return row


def _package(db: Session, package_id: uuid.UUID) -> PublicHardwarePackage:
    row = db.get(PublicHardwarePackage, package_id)
    if row is None:
        raise ApiError(404, "not_found", "That package does not exist.")
    return row


def _images(
    db: Session, *, product_id: uuid.UUID | None = None, package_id: uuid.UUID | None = None
) -> list[PublicHardwareImage]:
    if product_id is not None:
        clause = PublicHardwareImage.product_id == product_id
    else:
        clause = PublicHardwareImage.package_id == package_id
    return list(
        db.scalars(
            select(PublicHardwareImage)
            .where(clause)
            .order_by(PublicHardwareImage.position, PublicHardwareImage.created_at)
        )
    )


def _image_out(row: PublicHardwareImage) -> ImageOut:
    return ImageOut(
        id=row.id,
        url=_url(row.key) or "",
        thumb_url=_url(row.thumb_key) or "",
        alt=row.alt,
        position=row.position,
        is_primary=row.is_primary,
        width=row.width,
        height=row.height,
    )


def _public_images(rows: list[PublicHardwareImage]) -> list[PublicImageOut]:
    return [
        PublicImageOut(
            url=_url(row.key) or "", thumb_url=_url(row.thumb_key) or "", alt=row.alt, is_primary=row.is_primary
        )
        for row in rows
    ]


def category_out(row: PublicHardwareCategory) -> CategoryOut:
    return CategoryOut(
        id=row.id,
        name=row.name,
        slug=row.slug,
        description=row.description,
        image_url=_url(row.image_key),
        thumb_url=_url(row.thumb_key),
        image_alt=row.image_alt,
        display_order=row.display_order,
        is_active=row.is_active,
        updated_at=row.updated_at,
    )


def product_out(db: Session, row: PublicHardwareProduct) -> ProductOut:
    category = db.get(PublicHardwareCategory, row.category_id)
    return ProductOut(
        id=row.id,
        category_id=row.category_id,
        category_name=category.name if category else "",
        category_slug=category.slug if category else "",
        name=row.name,
        slug=row.slug,
        sku=row.sku,
        short_description=row.short_description,
        full_description=row.full_description,
        brand=row.brand,
        model_number=row.model_number,
        manufacturer=row.manufacturer,
        specifications=_specs(row.specifications),
        purchase_price_fils=row.purchase_price_fils,
        display_price_fils=row.display_price_fils,
        currency=row.currency,
        warranty_months=row.warranty_months,
        stock_status=row.stock_status,
        compatibility=row.compatibility,
        display_order=row.display_order,
        is_featured=row.is_featured,
        is_published=row.is_published,
        is_active=row.is_active,
        archived=row.archived,
        published_at=row.published_at,
        images=[_image_out(image) for image in _images(db, product_id=row.id)],
        updated_at=row.updated_at,
    )


def _plan(db: Session, plan_id: uuid.UUID | None, *, required_active: bool) -> BillingPlan | None:
    if plan_id is None:
        return None
    row = db.get(BillingPlan, plan_id)
    if row is None or (required_active and not row.active):
        raise ApiError(422, "unknown_plan", "Choose an active AxizPOS billing plan.")
    return row


def _plan_out(row: BillingPlan | None) -> PlanRefOut | None:
    if row is None:
        return None
    return PlanRefOut(
        id=row.id,
        code=row.code,
        name=row.name,
        monthly_fils=row.monthly_fils,
        included_registers=row.included_registers,
        active=row.active,
    )


def _replace_items(db: Session, package: PublicHardwarePackage, items: list[PackageItemIn]) -> None:
    seen: set[uuid.UUID] = set()
    for item in items:
        if item.product_id in seen:
            raise ApiError(
                422, "duplicate_component", "A package can include each product once. Raise the quantity instead."
            )
        seen.add(item.product_id)
        product = db.get(PublicHardwareProduct, item.product_id)
        if product is None or product.archived:
            raise ApiError(422, "unknown_product", "A package component must be an active catalogue product.")
        if product.currency != package.currency:
            raise ApiError(422, "currency", "Every component must use the package currency.")
    db.execute(delete(PublicHardwarePackageItem).where(PublicHardwarePackageItem.package_id == package.id))
    for index, item in enumerate(items):
        db.add(
            PublicHardwarePackageItem(
                package_id=package.id,
                product_id=item.product_id,
                quantity=item.quantity,
                is_optional=item.is_optional,
                display_order=item.display_order or index,
            )
        )
    db.flush()


def _item_rows(db: Session, package_id: uuid.UUID) -> list[PublicHardwarePackageItem]:
    return list(
        db.scalars(
            select(PublicHardwarePackageItem)
            .where(PublicHardwarePackageItem.package_id == package_id)
            .order_by(PublicHardwarePackageItem.display_order, PublicHardwarePackageItem.id)
        )
    )


def _thumb_for(db: Session, product_id: uuid.UUID) -> str | None:
    image = db.scalar(
        select(PublicHardwareImage)
        .where(PublicHardwareImage.product_id == product_id)
        .order_by(PublicHardwareImage.is_primary.desc(), PublicHardwareImage.position)
    )
    return _url(image.thumb_key) if image else None


def package_out(db: Session, row: PublicHardwarePackage) -> PackageOut:
    plan = db.get(BillingPlan, row.billing_plan_id) if row.billing_plan_id else None
    items = []
    valued: list[tuple[int, int | None, str, bool]] = []
    for item in _item_rows(db, row.id):
        product = db.get(PublicHardwareProduct, item.product_id)
        if product is None:
            continue
        items.append(
            PackageItemOut(
                id=item.id,
                product_id=product.id,
                product_name=product.name,
                product_slug=product.slug,
                sku=product.sku,
                quantity=item.quantity,
                is_optional=item.is_optional,
                display_order=item.display_order,
                display_price_fils=product.display_price_fils,
                currency=product.currency,
                is_published=product.is_published,
                archived=product.archived,
                thumb_url=_thumb_for(db, product.id),
            )
        )
        valued.append((item.quantity, product.display_price_fils, product.currency, item.is_optional))
    total, savings = component_value(valued, row.currency, row.display_price_fils)
    return PackageOut(
        id=row.id,
        name=row.name,
        slug=row.slug,
        short_description=row.short_description,
        full_description=row.full_description,
        display_price_fils=row.display_price_fils,
        currency=row.currency,
        billing_plan_id=row.billing_plan_id,
        plan=_plan_out(plan),
        package_type=row.package_type,
        display_order=row.display_order,
        is_featured=row.is_featured,
        is_published=row.is_published,
        is_active=row.is_active,
        published_at=row.published_at,
        items=items,
        images=[_image_out(image) for image in _images(db, package_id=row.id)],
        component_value_fils=total,
        savings_fils=savings,
        updated_at=row.updated_at,
    )


def overview(db: Session) -> OverviewOut:
    def count(*where) -> int:
        return int(db.scalar(select(func.count()).select_from(PublicHardwareProduct).where(*where)) or 0)

    return OverviewOut(
        categories=int(db.scalar(select(func.count()).select_from(PublicHardwareCategory)) or 0),
        products=count(),
        published_products=count(
            PublicHardwareProduct.is_published.is_(True), PublicHardwareProduct.archived.is_(False)
        ),
        draft_products=count(PublicHardwareProduct.is_published.is_(False), PublicHardwareProduct.archived.is_(False)),
        archived_products=count(PublicHardwareProduct.archived.is_(True)),
        packages=int(db.scalar(select(func.count()).select_from(PublicHardwarePackage)) or 0),
        published_packages=int(
            db.scalar(
                select(func.count())
                .select_from(PublicHardwarePackage)
                .where(PublicHardwarePackage.is_published.is_(True))
            )
            or 0
        ),
        new_enquiries=int(
            db.scalar(
                select(func.count()).select_from(PublicHardwareEnquiry).where(PublicHardwareEnquiry.status == "new")
            )
            or 0
        ),
        converted_enquiries=int(
            db.scalar(
                select(func.count())
                .select_from(PublicHardwareEnquiry)
                .where(PublicHardwareEnquiry.status == "converted")
            )
            or 0
        ),
    )


def list_categories(db: Session, *, active_only: bool = False) -> list[CategoryOut]:
    query = select(PublicHardwareCategory).order_by(PublicHardwareCategory.display_order, PublicHardwareCategory.name)
    if active_only:
        query = query.where(PublicHardwareCategory.is_active.is_(True))
    return [category_out(row) for row in db.scalars(query)]


def create_category(db: Session, operator: OperatorPrincipal, data: CategoryIn) -> CategoryOut:
    slug = _unique_slug(db, PublicHardwareCategory, _slug(data.slug, data.name))
    row = PublicHardwareCategory(
        name=data.name.strip(),
        slug=slug,
        description=data.description.strip(),
        image_alt=data.image_alt.strip(),
        display_order=data.display_order,
        is_active=data.is_active,
    )
    db.add(row)
    db.flush()
    audit_operator(
        db, operator, "public_hardware.category_create", after={"slug": slug, "name": row.name}, reason=data.reason
    )
    _commit(db)
    return category_out(row)


def update_category(db: Session, operator: OperatorPrincipal, category_id: uuid.UUID, data: CategoryIn) -> CategoryOut:
    row = _category(db, category_id)
    before = {"name": row.name, "is_active": row.is_active, "display_order": row.display_order}
    row.name = data.name.strip()
    row.slug = _unique_slug(db, PublicHardwareCategory, _slug(data.slug, data.name), row.id)
    row.description = data.description.strip()
    row.image_alt = data.image_alt.strip()
    row.display_order = data.display_order
    row.is_active = data.is_active
    row.updated_at = datetime.now(UTC)
    audit_operator(
        db,
        operator,
        "public_hardware.category_update",
        before=before,
        after={"slug": row.slug, "is_active": row.is_active},
        reason=data.reason,
    )
    _commit(db)
    return category_out(row)


def delete_category(db: Session, operator: OperatorPrincipal, category_id: uuid.UUID, reason: str) -> None:
    row = _category(db, category_id)
    used = db.scalar(select(PublicHardwareProduct.id).where(PublicHardwareProduct.category_id == row.id).limit(1))
    if used is not None:
        raise ApiError(409, "category_in_use", "Move or archive the products in this category before deleting it.")
    keys = [row.image_key, row.thumb_key]
    audit_operator(db, operator, "public_hardware.category_delete", before={"slug": row.slug}, reason=reason)
    db.delete(row)
    _commit(db)
    _drop_files(db, keys)


def list_products(
    db: Session,
    *,
    q: str = "",
    status: str = "",
    category_id: uuid.UUID | None = None,
    featured: bool | None = None,
    sort: str = "updated",
    offset: int = 0,
    limit: int = 25,
) -> tuple[list[ProductOut], int]:
    query = select(PublicHardwareProduct)
    if category_id is not None:
        query = query.where(PublicHardwareProduct.category_id == category_id)
    if featured is True:
        query = query.where(PublicHardwareProduct.is_featured.is_(True))
    if status == "published":
        query = query.where(PublicHardwareProduct.is_published.is_(True), PublicHardwareProduct.archived.is_(False))
    elif status == "draft":
        query = query.where(PublicHardwareProduct.is_published.is_(False), PublicHardwareProduct.archived.is_(False))
    elif status == "archived":
        query = query.where(PublicHardwareProduct.archived.is_(True))
    needle = q.strip().lower()
    if needle:
        like = f"%{needle}%"
        query = query.where(
            or_(
                func.lower(PublicHardwareProduct.name).like(like),
                func.lower(PublicHardwareProduct.sku).like(like),
                func.lower(PublicHardwareProduct.brand).like(like),
            )
        )
    order = {
        "name": PublicHardwareProduct.name,
        "price": PublicHardwareProduct.display_price_fils,
        "order": PublicHardwareProduct.display_order,
    }.get(sort, PublicHardwareProduct.updated_at)
    total = int(db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0)
    rows = db.scalars(
        query.order_by(order.desc() if sort == "updated" else order, PublicHardwareProduct.name)
        .offset(offset)
        .limit(limit)
    )
    return [product_out(db, row) for row in rows], total


def _fill_product(row: PublicHardwareProduct, data: ProductIn, slug: str) -> None:
    row.category_id = data.category_id
    row.name = data.name.strip()
    row.slug = slug
    row.sku = data.sku.strip().upper()
    row.short_description = data.short_description.strip()
    row.full_description = data.full_description.strip()
    row.brand = data.brand.strip()
    row.model_number = data.model_number.strip()
    row.manufacturer = data.manufacturer.strip()
    row.specifications = [item.model_dump() for item in data.specifications]
    row.purchase_price_fils = data.purchase_price_fils
    row.display_price_fils = data.display_price_fils
    row.currency = "AED"
    row.warranty_months = data.warranty_months
    row.stock_status = data.stock_status
    row.compatibility = data.compatibility.strip()
    row.display_order = data.display_order
    row.is_featured = data.is_featured
    row.is_active = data.is_active and not row.archived
    if not row.is_active:
        row.is_published = False
    row.updated_at = datetime.now(UTC)


def create_product(db: Session, operator: OperatorPrincipal, data: ProductIn) -> ProductOut:
    category = _category(db, data.category_id)
    if not category.is_active:
        raise ApiError(422, "inactive_category", "Choose an active category.")
    sku = data.sku.strip().upper()
    if db.scalar(select(PublicHardwareProduct.id).where(PublicHardwareProduct.sku == sku)) is not None:
        raise ApiError(409, "duplicate_sku", "That SKU is already in the catalogue.")
    row = PublicHardwareProduct(category_id=category.id, name=data.name.strip(), slug="pending", sku=sku)
    _fill_product(row, data, _unique_slug(db, PublicHardwareProduct, _slug(data.slug, data.name)))
    db.add(row)
    db.flush()
    audit_operator(
        db,
        operator,
        "public_hardware.product_create",
        after={
            "sku": sku,
            "display_price_fils": row.display_price_fils,
            "purchase_price_fils": row.purchase_price_fils,
        },
        reason=data.reason,
    )
    _commit(db)
    return product_out(db, row)


def update_product(db: Session, operator: OperatorPrincipal, product_id: uuid.UUID, data: ProductIn) -> ProductOut:
    row = _product(db, product_id)
    if row.archived:
        raise ApiError(409, "archived", "Restore the product before editing it.")
    category = _category(db, data.category_id)
    sku = data.sku.strip().upper()
    taken = db.scalar(
        select(PublicHardwareProduct.id).where(PublicHardwareProduct.sku == sku, PublicHardwareProduct.id != row.id)
    )
    if taken is not None:
        raise ApiError(409, "duplicate_sku", "That SKU is already in the catalogue.")
    before = {
        "display_price_fils": row.display_price_fils,
        "purchase_price_fils": row.purchase_price_fils,
        "sku": row.sku,
    }
    _fill_product(row, data, _unique_slug(db, PublicHardwareProduct, _slug(data.slug, data.name), row.id))
    if not category.is_active:
        row.is_published = False
    audit_operator(
        db,
        operator,
        "public_hardware.product_update",
        before=before,
        after={
            "sku": row.sku,
            "display_price_fils": row.display_price_fils,
            "purchase_price_fils": row.purchase_price_fils,
        },
        reason=data.reason,
    )
    _commit(db)
    return product_out(db, row)


def _publish_product_checks(db: Session, row: PublicHardwareProduct) -> None:
    if row.archived or not row.is_active:
        raise ApiError(409, "not_publishable", "An archived or inactive product cannot be published.")
    category = _category(db, row.category_id)
    if not category.is_active:
        raise ApiError(409, "inactive_category", "Activate the category before publishing this product.")


def publish_product(db: Session, operator: OperatorPrincipal, product_id: uuid.UUID, reason: str) -> ProductOut:
    row = _product(db, product_id)
    _publish_product_checks(db, row)
    row.is_published = True
    row.published_at = datetime.now(UTC)
    row.updated_at = row.published_at
    audit_operator(db, operator, "public_hardware.product_publish", after={"slug": row.slug}, reason=reason)
    _commit(db)
    return product_out(db, row)


def unpublish_product(db: Session, operator: OperatorPrincipal, product_id: uuid.UUID, reason: str) -> ProductOut:
    row = _product(db, product_id)
    row.is_published = False
    row.updated_at = datetime.now(UTC)
    audit_operator(db, operator, "public_hardware.product_unpublish", after={"slug": row.slug}, reason=reason)
    _commit(db)
    return product_out(db, row)


def archive_product(db: Session, operator: OperatorPrincipal, product_id: uuid.UUID, reason: str) -> ProductOut:
    row = _product(db, product_id)
    row.archived = True
    row.archived_at = datetime.now(UTC)
    row.is_active = False
    row.is_published = False
    row.is_featured = False
    row.updated_at = row.archived_at
    audit_operator(db, operator, "public_hardware.product_archive", after={"slug": row.slug}, reason=reason)
    _commit(db)
    return product_out(db, row)


def delete_product(db: Session, operator: OperatorPrincipal, product_id: uuid.UUID, reason: str) -> None:
    row = _product(db, product_id)
    used = db.scalar(
        select(PublicHardwarePackageItem.id).where(PublicHardwarePackageItem.product_id == row.id).limit(1)
    )
    if used is not None:
        raise ApiError(409, "product_in_use", "This product is in a package. Remove it from the package or archive it.")
    for enquiry in db.scalars(select(PublicHardwareEnquiry).where(PublicHardwareEnquiry.product_id == row.id)):
        enquiry.product_label = enquiry.product_label or row.name
    images = _images(db, product_id=row.id)
    keys = [key for image in images for key in (image.key, image.thumb_key)]
    audit_operator(
        db, operator, "public_hardware.product_delete", before={"sku": row.sku, "slug": row.slug}, reason=reason
    )
    db.delete(row)
    _commit(db)
    _drop_files(db, keys)


def list_packages(
    db: Session, *, q: str = "", published: bool | None = None, offset: int = 0, limit: int = 25
) -> tuple[list[PackageOut], int]:
    query = select(PublicHardwarePackage)
    if published is True:
        query = query.where(PublicHardwarePackage.is_published.is_(True))
    elif published is False:
        query = query.where(PublicHardwarePackage.is_published.is_(False))
    needle = q.strip().lower()
    if needle:
        query = query.where(func.lower(PublicHardwarePackage.name).like(f"%{needle}%"))
    total = int(db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0)
    rows = db.scalars(
        query.order_by(PublicHardwarePackage.display_order, PublicHardwarePackage.name).offset(offset).limit(limit)
    )
    return [package_out(db, row) for row in rows], total


def _save_package(db: Session, row: PublicHardwarePackage, data: PackageIn, slug: str) -> None:
    plan = _plan(db, data.billing_plan_id, required_active=True)
    if data.package_type == "hardware_software" and plan is None:
        raise ApiError(422, "plan_required", "A hardware and software package needs an AxizPOS billing plan.")
    row.name = data.name.strip()
    row.slug = slug
    row.short_description = data.short_description.strip()
    row.full_description = data.full_description.strip()
    row.display_price_fils = data.display_price_fils
    row.currency = "AED"
    row.billing_plan_id = plan.id if plan else None
    row.package_type = data.package_type
    row.display_order = data.display_order
    row.is_featured = data.is_featured
    row.is_active = data.is_active
    if not row.is_active:
        row.is_published = False
    row.updated_at = datetime.now(UTC)
    db.flush()
    _replace_items(db, row, data.items)


def create_package(db: Session, operator: OperatorPrincipal, data: PackageIn) -> PackageOut:
    slug = _unique_slug(db, PublicHardwarePackage, _slug(data.slug, data.name))
    row = PublicHardwarePackage(name=data.name.strip(), slug=slug)
    db.add(row)
    db.flush()
    _save_package(db, row, data, slug)
    audit_operator(
        db,
        operator,
        "public_hardware.package_create",
        after={
            "slug": row.slug,
            "display_price_fils": row.display_price_fils,
            "items": len(data.items),
            "plan_id": str(row.billing_plan_id or ""),
        },
        reason=data.reason,
    )
    _commit(db)
    return package_out(db, row)


def update_package(db: Session, operator: OperatorPrincipal, package_id: uuid.UUID, data: PackageIn) -> PackageOut:
    row = _package(db, package_id)
    before = {
        "display_price_fils": row.display_price_fils,
        "plan_id": str(row.billing_plan_id or ""),
        "items": len(_item_rows(db, row.id)),
    }
    _save_package(db, row, data, _unique_slug(db, PublicHardwarePackage, _slug(data.slug, data.name), row.id))
    if row.is_published:
        _publish_package_checks(db, row)
    audit_operator(
        db,
        operator,
        "public_hardware.package_update",
        before=before,
        after={
            "slug": row.slug,
            "display_price_fils": row.display_price_fils,
            "items": len(data.items),
            "plan_id": str(row.billing_plan_id or ""),
        },
        reason=data.reason,
    )
    _commit(db)
    return package_out(db, row)


def _publish_package_checks(db: Session, row: PublicHardwarePackage) -> None:
    if not row.is_active:
        raise ApiError(409, "not_publishable", "An inactive package cannot be published.")
    items = _item_rows(db, row.id)
    if not items:
        raise ApiError(409, "empty_package", "Add at least one product before publishing the package.")
    plan = _plan(db, row.billing_plan_id, required_active=True) if row.billing_plan_id else None
    if row.package_type == "hardware_software" and plan is None:
        raise ApiError(409, "plan_required", "Link an active AxizPOS plan before publishing this package.")
    for item in items:
        product = db.get(PublicHardwareProduct, item.product_id)
        if product is None or product.archived or not product.is_active or not product.is_published:
            raise ApiError(
                409, "unpublished_component", "Publish every included product before publishing the package."
            )
        if product.currency != row.currency:
            raise ApiError(409, "currency", "Every component must use the package currency.")


def publish_package(db: Session, operator: OperatorPrincipal, package_id: uuid.UUID, reason: str) -> PackageOut:
    row = _package(db, package_id)
    _publish_package_checks(db, row)
    row.is_published = True
    row.published_at = datetime.now(UTC)
    row.updated_at = row.published_at
    audit_operator(db, operator, "public_hardware.package_publish", after={"slug": row.slug}, reason=reason)
    _commit(db)
    return package_out(db, row)


def unpublish_package(db: Session, operator: OperatorPrincipal, package_id: uuid.UUID, reason: str) -> PackageOut:
    row = _package(db, package_id)
    row.is_published = False
    row.updated_at = datetime.now(UTC)
    audit_operator(db, operator, "public_hardware.package_unpublish", after={"slug": row.slug}, reason=reason)
    _commit(db)
    return package_out(db, row)


def delete_package(db: Session, operator: OperatorPrincipal, package_id: uuid.UUID, reason: str) -> None:
    row = _package(db, package_id)
    if row.is_published:
        raise ApiError(409, "published", "Unpublish the package before deleting it.")
    for enquiry in db.scalars(select(PublicHardwareEnquiry).where(PublicHardwareEnquiry.package_id == row.id)):
        enquiry.package_label = enquiry.package_label or row.name
    keys = [key for image in _images(db, package_id=row.id) for key in (image.key, image.thumb_key)]
    audit_operator(db, operator, "public_hardware.package_delete", before={"slug": row.slug}, reason=reason)
    db.delete(row)
    _commit(db)
    _drop_files(db, keys)


def list_plans(db: Session) -> list[PlanRefOut]:
    rows = db.scalars(
        select(BillingPlan).where(BillingPlan.active.is_(True)).order_by(BillingPlan.sort_order, BillingPlan.name)
    )
    return [plan for row in rows if (plan := _plan_out(row)) is not None]


def store_photo(data: bytes, content_type: str | None, filename: str) -> tuple[str, str, int, int]:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise ApiError(415, "unsupported_file", "Upload a JPEG, PNG, or WebP photo.")
    if (content_type or "").split(";")[0].strip().lower() not in CONTENT_TYPES:
        raise ApiError(415, "unsupported_file", "Upload a JPEG, PNG, or WebP photo.")
    if len(data) > MAX_BYTES or len(data) == 0:
        raise ApiError(413, "file_too_large", "Photos are limited to 5 MB.")
    image = _decode(data)
    full, width, height = _encode(image, FULL_PX)
    thumb, _, _ = _encode(image, THUMB_PX)
    stem = uuid.uuid4().hex
    key, thumb_key = f"catalog/{stem}.webp", f"catalog/{stem}-thumb.webp"
    storage = media_storage.storage_for(PLATFORM)
    storage.put(key, full)
    storage.put(thumb_key, thumb)
    return key, thumb_key, width, height


def _drop_files(db: Session, keys: list[str | None]) -> None:
    storage = media_storage.storage_for(PLATFORM)
    for key in keys:
        if not key:
            continue
        still = db.scalar(
            select(PublicHardwareImage.id)
            .where(or_(PublicHardwareImage.key == key, PublicHardwareImage.thumb_key == key))
            .limit(1)
        )
        category = db.scalar(
            select(PublicHardwareCategory.id)
            .where(or_(PublicHardwareCategory.image_key == key, PublicHardwareCategory.thumb_key == key))
            .limit(1)
        )
        if still is None and category is None:
            storage.delete(key)


def _attach(
    db: Session,
    *,
    product_id: uuid.UUID | None,
    package_id: uuid.UUID | None,
    alt: str,
    stored: tuple[str, str, int, int],
) -> PublicHardwareImage:
    existing = _images(db, product_id=product_id, package_id=package_id)
    if len(existing) >= MAX_IMAGES:
        _drop_files(db, [stored[0], stored[1]])
        raise ApiError(409, "too_many_images", f"Keep at most {MAX_IMAGES} photos.")
    key, thumb, width, height = stored
    row = PublicHardwareImage(
        product_id=product_id,
        package_id=package_id,
        key=key,
        thumb_key=thumb,
        alt=alt.strip()[:160],
        position=len(existing),
        is_primary=len(existing) == 0,
        width=width,
        height=height,
    )
    db.add(row)
    db.flush()
    return row


def add_product_image(
    db: Session,
    operator: OperatorPrincipal,
    product_id: uuid.UUID,
    data: bytes,
    content_type: str | None,
    filename: str,
    alt: str,
    reason: str,
) -> ProductOut:
    row = _product(db, product_id)
    stored = store_photo(data, content_type, filename)
    try:
        _attach(db, product_id=row.id, package_id=None, alt=alt or row.name, stored=stored)
        audit_operator(
            db, operator, "public_hardware.image_add", after={"slug": row.slug, "alt": alt[:80]}, reason=reason
        )
        _commit(db)
    except Exception:
        db.rollback()
        _drop_files(db, [stored[0], stored[1]])
        raise
    return product_out(db, row)


def add_package_image(
    db: Session,
    operator: OperatorPrincipal,
    package_id: uuid.UUID,
    data: bytes,
    content_type: str | None,
    filename: str,
    alt: str,
    reason: str,
) -> PackageOut:
    row = _package(db, package_id)
    stored = store_photo(data, content_type, filename)
    try:
        _attach(db, product_id=None, package_id=row.id, alt=alt or row.name, stored=stored)
        audit_operator(
            db, operator, "public_hardware.image_add", after={"slug": row.slug, "alt": alt[:80]}, reason=reason
        )
        _commit(db)
    except Exception:
        db.rollback()
        _drop_files(db, [stored[0], stored[1]])
        raise
    return package_out(db, row)


def add_category_image(
    db: Session,
    operator: OperatorPrincipal,
    category_id: uuid.UUID,
    data: bytes,
    content_type: str | None,
    filename: str,
    alt: str,
    reason: str,
) -> CategoryOut:
    row = _category(db, category_id)
    stored = store_photo(data, content_type, filename)
    previous = [row.image_key, row.thumb_key]
    row.image_key, row.thumb_key = stored[0], stored[1]
    if alt.strip():
        row.image_alt = alt.strip()[:160]
    row.updated_at = datetime.now(UTC)
    try:
        audit_operator(db, operator, "public_hardware.image_add", after={"slug": row.slug}, reason=reason)
        _commit(db)
    except Exception:
        db.rollback()
        _drop_files(db, [stored[0], stored[1]])
        raise
    _drop_files(db, previous)
    return category_out(row)


def reorder_images(
    db: Session, operator: OperatorPrincipal, owner: str, owner_id: uuid.UUID, ids: list[uuid.UUID], reason: str
) -> None:
    if owner == "product":
        rows = _images(db, product_id=owner_id)
    else:
        rows = _images(db, package_id=owner_id)
    by_id = {row.id: row for row in rows}
    if set(by_id) != set(ids):
        raise ApiError(422, "image_order", "Include every photo for this item, once.")
    for index, image_id in enumerate(ids):
        by_id[image_id].position = index
        by_id[image_id].is_primary = index == 0
    audit_operator(db, operator, "public_hardware.image_reorder", after={"count": len(ids)}, reason=reason)
    _commit(db)


def delete_image(db: Session, operator: OperatorPrincipal, image_id: uuid.UUID, reason: str) -> None:
    row = db.get(PublicHardwareImage, image_id)
    if row is None:
        raise ApiError(404, "not_found", "That photo does not exist.")
    keys = [row.key, row.thumb_key]
    owner_product, owner_package = row.product_id, row.package_id
    was_primary = row.is_primary
    audit_operator(db, operator, "public_hardware.image_delete", before={"key": row.key}, reason=reason)
    db.delete(row)
    db.flush()
    if was_primary:
        remaining = _images(db, product_id=owner_product, package_id=owner_package)
        if remaining:
            remaining[0].is_primary = True
    _commit(db)
    _drop_files(db, keys)


def _enquiry_out(db: Session, row: PublicHardwareEnquiry) -> EnquiryOut:
    notes = []
    for note in db.scalars(
        select(PublicHardwareEnquiryNote)
        .where(PublicHardwareEnquiryNote.enquiry_id == row.id)
        .order_by(PublicHardwareEnquiryNote.created_at)
    ):
        operator = db.get(Operator, note.operator_id) if note.operator_id else None
        notes.append(
            EnquiryNoteOut(
                id=note.id,
                body=note.body,
                operator_name=operator.full_name if operator else "",
                created_at=note.created_at,
            )
        )
    return EnquiryOut(
        id=row.id,
        enquiry_reference=row.enquiry_reference,
        customer_name=row.customer_name,
        business_name=row.business_name,
        email=row.email,
        phone=row.phone,
        country=row.country,
        business_type=row.business_type,
        enquiry_type=row.enquiry_type,
        product_id=row.product_id,
        package_id=row.package_id,
        product_label=row.product_label,
        package_label=row.package_label,
        quantity=row.quantity,
        message=row.message,
        status=row.status,
        source=row.source,
        notes=notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_enquiries(
    db: Session, *, q: str = "", status: str = "", offset: int = 0, limit: int = 25
) -> tuple[list[EnquiryOut], int]:
    if status and status not in {"new", "contacted", "quoted", "converted", "closed"}:
        raise ApiError(422, "status", "Unknown enquiry status.")
    query = select(PublicHardwareEnquiry)
    if status:
        query = query.where(PublicHardwareEnquiry.status == status)
    needle = q.strip().lower()
    if needle:
        like = f"%{needle}%"
        query = query.where(
            or_(
                func.lower(PublicHardwareEnquiry.customer_name).like(like),
                func.lower(PublicHardwareEnquiry.business_name).like(like),
                func.lower(PublicHardwareEnquiry.email).like(like),
                func.lower(PublicHardwareEnquiry.enquiry_reference).like(like),
            )
        )
    total = int(db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0)
    rows = db.scalars(query.order_by(PublicHardwareEnquiry.created_at.desc()).offset(offset).limit(limit))
    return [_enquiry_out(db, row) for row in rows], total


def get_enquiry(db: Session, enquiry_id: uuid.UUID) -> EnquiryOut:
    row = db.get(PublicHardwareEnquiry, enquiry_id)
    if row is None:
        raise ApiError(404, "not_found", "That enquiry does not exist.")
    return _enquiry_out(db, row)


def set_enquiry_status(
    db: Session, operator: OperatorPrincipal, enquiry_id: uuid.UUID, data: EnquiryStatusIn
) -> EnquiryOut:
    row = db.get(PublicHardwareEnquiry, enquiry_id)
    if row is None:
        raise ApiError(404, "not_found", "That enquiry does not exist.")
    before = row.status
    row.status = data.status
    row.updated_at = datetime.now(UTC)
    audit_operator(
        db,
        operator,
        "public_hardware.enquiry_status",
        before={"status": before},
        after={"status": row.status, "reference": row.enquiry_reference},
        reason=data.reason,
    )
    _commit(db)
    return _enquiry_out(db, row)


def add_note(db: Session, operator: OperatorPrincipal, enquiry_id: uuid.UUID, data: EnquiryNoteIn) -> EnquiryOut:
    row = db.get(PublicHardwareEnquiry, enquiry_id)
    if row is None:
        raise ApiError(404, "not_found", "That enquiry does not exist.")
    db.add(PublicHardwareEnquiryNote(enquiry_id=row.id, operator_id=operator.id, body=data.body.strip()))
    audit_operator(
        db, operator, "public_hardware.enquiry_note", after={"reference": row.enquiry_reference}, reason=data.reason
    )
    _commit(db)
    return _enquiry_out(db, row)


def _phone(value: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", value.strip())
    if cleaned.startswith("00"):
        cleaned = f"+{cleaned[2:]}"
    if not cleaned.startswith("+"):
        cleaned = f"+{cleaned}"
    if PHONE.fullmatch(cleaned) is None:
        raise ApiError(422, "phone", "Enter a phone number with the country code.")
    return cleaned


def _reference(db: Session) -> str:
    day = datetime.now(UTC).strftime("%Y%m%d")
    for _ in range(5):
        reference = f"PHW-{day}-{secrets.token_hex(2).upper()}"
        if (
            db.scalar(select(PublicHardwareEnquiry.id).where(PublicHardwareEnquiry.enquiry_reference == reference))
            is None
        ):
            return reference
    raise ApiError(503, "unavailable", "Try the enquiry again.")


def _source(value: str) -> str:
    path = value.strip().split("?")[0].split("#")[0]
    if not path.startswith("/hardware"):
        return "/hardware"
    return path[:200]


def submit_enquiry(db: Session, data: PublicEnquiryIn) -> PublicEnquiryOut:
    if data.website.strip():
        raise ApiError(422, "rejected", "The enquiry could not be accepted.")
    email = data.email.strip().lower()
    phone = _phone(data.phone)
    product = None
    package = None
    if data.product_slug.strip():
        product = db.scalar(
            select(PublicHardwareProduct).where(PublicHardwareProduct.slug == data.product_slug.strip())
        )
        if product is None or not product.is_published or not product.is_active or product.archived:
            raise ApiError(422, "unavailable", "That product is not available for an enquiry.")
    if data.package_slug.strip():
        package = db.scalar(
            select(PublicHardwarePackage).where(PublicHardwarePackage.slug == data.package_slug.strip())
        )
        if package is None or not package.is_published or not package.is_active:
            raise ApiError(422, "unavailable", "That package is not available for an enquiry.")
    if data.enquiry_type == "product" and product is None:
        raise ApiError(422, "product_required", "Choose a published product.")
    if data.enquiry_type == "package" and package is None:
        raise ApiError(422, "package_required", "Choose a published package.")
    message = data.message.strip()
    cutoff = datetime.now(UTC) - DUPLICATE_WINDOW
    duplicate = db.scalar(
        select(PublicHardwareEnquiry).where(
            PublicHardwareEnquiry.email == email,
            PublicHardwareEnquiry.message == message,
            PublicHardwareEnquiry.product_id == (product.id if product else None),
            PublicHardwareEnquiry.package_id == (package.id if package else None),
            PublicHardwareEnquiry.created_at >= cutoff,
        )
    )
    if duplicate is not None:
        raise ApiError(
            409,
            "duplicate_enquiry",
            "This enquiry was already received.",
            details={"reference": duplicate.enquiry_reference},
        )
    row = PublicHardwareEnquiry(
        enquiry_reference=_reference(db),
        customer_name=data.customer_name.strip(),
        business_name=data.business_name.strip(),
        email=email,
        phone=phone,
        country=data.country.strip(),
        business_type=data.business_type,
        enquiry_type=data.enquiry_type,
        product_id=product.id if product else None,
        package_id=package.id if package else None,
        product_label=product.name if product else "",
        package_label=package.name if package else "",
        quantity=data.quantity,
        message=message,
        status="new",
        source=_source(data.source),
    )
    db.add(row)
    audit_operator(
        db, None, "public_hardware.enquiry_create", after={"reference": row.enquiry_reference, "source": row.source}
    )
    _commit(db)
    return PublicEnquiryOut(
        reference=row.enquiry_reference, message="We received your enquiry. A specialist will contact you."
    )


def public_categories(db: Session) -> list[PublicCategoryOut]:
    rows = db.scalars(
        select(PublicHardwareCategory)
        .where(PublicHardwareCategory.is_active.is_(True))
        .order_by(PublicHardwareCategory.display_order, PublicHardwareCategory.name)
    )
    return [
        PublicCategoryOut(
            slug=row.slug,
            name=row.name,
            description=row.description,
            image_url=_url(row.image_key),
            image_alt=row.image_alt,
            display_order=row.display_order,
        )
        for row in rows
    ]


def _public_product(db: Session, row: PublicHardwareProduct, *, detail: bool) -> PublicProductOut:
    category = db.get(PublicHardwareCategory, row.category_id)
    packages: list[PublicPackageCard] = []
    if detail:
        linked = db.scalars(
            select(PublicHardwarePackage)
            .join(PublicHardwarePackageItem, PublicHardwarePackageItem.package_id == PublicHardwarePackage.id)
            .where(
                PublicHardwarePackageItem.product_id == row.id,
                PublicHardwarePackage.is_published.is_(True),
                PublicHardwarePackage.is_active.is_(True),
            )
            .order_by(PublicHardwarePackage.display_order)
        )
        packages = [_public_card(db, item) for item in linked]
    return PublicProductOut(
        slug=row.slug,
        name=row.name,
        sku=row.sku,
        brand=row.brand,
        model_number=row.model_number,
        manufacturer=row.manufacturer,
        short_description=row.short_description,
        full_description=row.full_description if detail else "",
        currency=row.currency,
        display_price_fils=row.display_price_fils,
        warranty_months=row.warranty_months,
        stock_status=row.stock_status,
        compatibility=row.compatibility if detail else "",
        is_featured=row.is_featured,
        category_slug=category.slug if category else "",
        category_name=category.name if category else "",
        specifications=_specs(row.specifications) if detail else [],
        images=_public_images(_images(db, product_id=row.id)),
        packages=packages,
    )


def _public_card(db: Session, row: PublicHardwarePackage) -> PublicPackageCard:
    image = db.scalar(
        select(PublicHardwareImage)
        .where(PublicHardwareImage.package_id == row.id)
        .order_by(PublicHardwareImage.is_primary.desc(), PublicHardwareImage.position)
    )
    return PublicPackageCard(
        slug=row.slug,
        name=row.name,
        short_description=row.short_description,
        display_price_fils=row.display_price_fils,
        currency=row.currency,
        package_type=row.package_type,
        is_featured=row.is_featured,
        thumb_url=_url(image.thumb_key) if image else None,
    )


def public_products(
    db: Session,
    *,
    q: str = "",
    category: str = "",
    featured: bool | None = None,
    sort: str = "order",
    offset: int = 0,
    limit: int = 24,
) -> tuple[list[PublicProductOut], int]:
    query = (
        select(PublicHardwareProduct)
        .join(PublicHardwareCategory, PublicHardwareCategory.id == PublicHardwareProduct.category_id)
        .where(
            PublicHardwareProduct.is_published.is_(True),
            PublicHardwareProduct.is_active.is_(True),
            PublicHardwareProduct.archived.is_(False),
            PublicHardwareCategory.is_active.is_(True),
        )
    )
    if category:
        query = query.where(PublicHardwareCategory.slug == category)
    if featured is True:
        query = query.where(PublicHardwareProduct.is_featured.is_(True))
    needle = q.strip().lower()
    if needle:
        like = f"%{needle}%"
        query = query.where(
            or_(
                func.lower(PublicHardwareProduct.name).like(like),
                func.lower(PublicHardwareProduct.brand).like(like),
                func.lower(PublicHardwareProduct.sku).like(like),
            )
        )
    order = {
        "name": PublicHardwareProduct.name,
        "price": PublicHardwareProduct.display_price_fils,
    }.get(sort, PublicHardwareProduct.display_order)
    total = int(db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0)
    rows = db.scalars(query.order_by(order, PublicHardwareProduct.name).offset(offset).limit(limit))
    return [_public_product(db, row, detail=False) for row in rows], total


def public_product(db: Session, slug: str) -> PublicProductOut:
    row = db.scalar(
        select(PublicHardwareProduct)
        .join(PublicHardwareCategory, PublicHardwareCategory.id == PublicHardwareProduct.category_id)
        .where(
            PublicHardwareProduct.slug == slug,
            PublicHardwareProduct.is_published.is_(True),
            PublicHardwareProduct.is_active.is_(True),
            PublicHardwareProduct.archived.is_(False),
            PublicHardwareCategory.is_active.is_(True),
        )
    )
    if row is None:
        raise ApiError(404, "not_found", "That product is not published.")
    return _public_product(db, row, detail=True)


def public_packages(
    db: Session, *, featured: bool | None = None, offset: int = 0, limit: int = 24
) -> tuple[list[PublicPackageCard], int]:
    query = select(PublicHardwarePackage).where(
        PublicHardwarePackage.is_published.is_(True), PublicHardwarePackage.is_active.is_(True)
    )
    if featured is True:
        query = query.where(PublicHardwarePackage.is_featured.is_(True))
    total = int(db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0)
    rows = db.scalars(
        query.order_by(PublicHardwarePackage.display_order, PublicHardwarePackage.name).offset(offset).limit(limit)
    )
    return [_public_card(db, row) for row in rows], total


def public_package(db: Session, slug: str) -> PublicPackageOut:
    row = db.scalar(
        select(PublicHardwarePackage).where(
            PublicHardwarePackage.slug == slug,
            PublicHardwarePackage.is_published.is_(True),
            PublicHardwarePackage.is_active.is_(True),
        )
    )
    if row is None:
        raise ApiError(404, "not_found", "That package is not published.")
    plan = db.get(BillingPlan, row.billing_plan_id) if row.billing_plan_id else None
    if plan is not None and not plan.active:
        plan = None
    items = []
    valued: list[tuple[int, int | None, str, bool]] = []
    for item in _item_rows(db, row.id):
        product = db.get(PublicHardwareProduct, item.product_id)
        if product is None or not product.is_published or product.archived:
            continue
        items.append(
            PublicComponentOut(
                slug=product.slug,
                name=product.name,
                quantity=item.quantity,
                is_optional=item.is_optional,
                display_price_fils=product.display_price_fils,
                thumb_url=_thumb_for(db, product.id),
            )
        )
        valued.append((item.quantity, product.display_price_fils, product.currency, item.is_optional))
    total, savings = component_value(valued, row.currency, row.display_price_fils)
    public_plan = None
    if plan is not None:
        public_plan = PublicPlanOut(
            code=plan.code, name=plan.name, monthly_fils=plan.monthly_fils, included_registers=plan.included_registers
        )
    return PublicPackageOut(
        slug=row.slug,
        name=row.name,
        short_description=row.short_description,
        full_description=row.full_description,
        display_price_fils=row.display_price_fils,
        currency=row.currency,
        package_type=row.package_type,
        is_featured=row.is_featured,
        images=_public_images(_images(db, package_id=row.id)),
        plan=public_plan,
        items=items,
        component_value_fils=total,
        savings_fils=savings,
    )
