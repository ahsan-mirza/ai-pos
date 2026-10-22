"""Product photos: uploads are re-encoded as a 1200 px WebP plus a 320 px thumbnail, stored per tenant, and attached
to a variant or to a whole model (optionally to one colour of it)."""

import io
import uuid

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.brand import ProductModel
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.user import User
from app.schemas.catalogue import ProductImageOut, ProductImageUpdate
from app.services import media_storage

MAX_BYTES = 5 * 1024 * 1024
CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
FULL_PX = 1200
THUMB_PX = 320
MAX_PER_OWNER = 24
# Refuse decompression bombs: a 5 MB file may not unpack to more than ~40 megapixels.
Image.MAX_IMAGE_PIXELS = 40_000_000


def _encode(image: Image.Image, size: int) -> tuple[bytes, int, int]:
    copy = image.copy()
    copy.thumbnail((size, size), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    copy.save(buffer, "WEBP", quality=82, method=4)
    return buffer.getvalue(), copy.width, copy.height


def _decode(data: bytes) -> Image.Image:
    try:
        Image.open(io.BytesIO(data)).verify()
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError) as error:
        raise ApiError(415, "unsupported_file", "That file is not a JPEG, PNG or WebP photo.") from error
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "transparency" in image.info or image.mode in ("LA", "PA", "P") else "RGB")
    return image


def out(image: ProductImage) -> ProductImageOut:
    return ProductImageOut(
        id=image.id,
        product_id=image.product_id,
        product_model_id=image.product_model_id,
        attribute_key=image.attribute_key,
        attribute_value=image.attribute_value,
        url=media_storage.url(image.key),
        thumb_url=media_storage.url(image.thumb_key),
        width=image.width,
        height=image.height,
        position=image.position,
        is_primary=image.is_primary,
        created_at=image.created_at,
    )


def _owner_filter(product_id: uuid.UUID | None, model_id: uuid.UUID | None) -> ColumnElement[bool]:
    if product_id is not None:
        return ProductImage.product_id == product_id
    return ProductImage.product_model_id == model_id


def list_images(
    db: Session, *, product_id: uuid.UUID | None = None, model_id: uuid.UUID | None = None
) -> list[ProductImageOut]:
    rows = db.scalars(
        select(ProductImage)
        .where(_owner_filter(product_id, model_id))
        .order_by(ProductImage.is_primary.desc(), ProductImage.position, ProductImage.created_at)
    ).all()
    return [out(row) for row in rows]


def upload(
    db: Session,
    user: User | None,
    data: bytes,
    content_type: str | None,
    *,
    product_id: uuid.UUID | None = None,
    model_id: uuid.UUID | None = None,
    attribute_key: str | None = None,
    attribute_value: str | None = None,
) -> ProductImageOut:
    if product_id is not None and db.get(Product, product_id) is None:
        raise ApiError(404, "not_found", "Product was not found.")
    if model_id is not None and db.get(ProductModel, model_id) is None:
        raise ApiError(404, "not_found", "Model was not found.")
    if (content_type or "").split(";")[0].strip().lower() not in CONTENT_TYPES:
        raise ApiError(415, "unsupported_file", "Upload a JPEG, PNG or WebP photo.")
    if len(data) > MAX_BYTES:
        raise ApiError(413, "file_too_large", "Photos are limited to 5 MB.")
    owner = _owner_filter(product_id, model_id)
    count = db.scalar(select(func.count()).select_from(ProductImage).where(owner)) or 0
    if count >= MAX_PER_OWNER:
        raise ApiError(409, "too_many_images", f"Keep at most {MAX_PER_OWNER} photos per product or model.")
    image = _decode(data)
    full, width, height = _encode(image, FULL_PX)
    thumb, _, _ = _encode(image, THUMB_PX)
    stem = uuid.uuid4().hex
    key, thumb_key = f"products/{stem}.webp", f"products/{stem}-thumb.webp"
    storage = media_storage.storage_for()
    storage.put(key, full)
    storage.put(thumb_key, thumb)
    value = (attribute_value or "").strip() or None
    row = ProductImage(
        product_id=product_id,
        product_model_id=model_id,
        attribute_key=(attribute_key or "color").strip().lower() if value else None,
        attribute_value=value,
        key=key,
        thumb_key=thumb_key,
        width=width,
        height=height,
        position=count,
        is_primary=count == 0,
        uploaded_by_id=user.id if user is not None else None,
    )
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(key)
        storage.delete(thumb_key)
        raise
    return out(row)


def _image(db: Session, image_id: uuid.UUID) -> ProductImage:
    row = db.get(ProductImage, image_id)
    if row is None:
        raise ApiError(404, "not_found", "Photo was not found.")
    return row


def update(db: Session, image_id: uuid.UUID, data: ProductImageUpdate) -> ProductImageOut:
    row = _image(db, image_id)
    if data.is_primary:
        for other in db.scalars(select(ProductImage).where(_owner_filter(row.product_id, row.product_model_id))):
            other.is_primary = other.id == row.id
    if data.position is not None:
        row.position = data.position
    if "attribute_value" in data.model_fields_set:
        value = (data.attribute_value or "").strip() or None
        row.attribute_value = value
        row.attribute_key = (data.attribute_key or "color").strip().lower() if value else None
    db.commit()
    return out(row)


def delete(db: Session, image_id: uuid.UUID) -> None:
    row = _image(db, image_id)
    owner = _owner_filter(row.product_id, row.product_model_id)
    keys = (row.key, row.thumb_key)
    was_primary = row.is_primary
    db.delete(row)
    db.flush()
    if was_primary:
        successor = db.scalars(select(ProductImage).where(owner).order_by(ProductImage.position)).first()
        if successor is not None:
            successor.is_primary = True
    db.commit()
    storage = media_storage.storage_for()
    for key in keys:
        storage.delete(key)


def cover_urls(db: Session, products: list[Product]) -> dict[uuid.UUID, tuple[str, str]]:
    """Each product's cover: its own primary photo, else its model's photo for one of its attribute values (the
    colour), else the model's primary photo."""
    if not products:
        return {}
    ids = [product.id for product in products]
    model_ids = {product.product_model_id for product in products if product.product_model_id is not None}
    order = (ProductImage.is_primary.desc(), ProductImage.position, ProductImage.created_at)
    own: dict[uuid.UUID, ProductImage] = {}
    for row in db.scalars(select(ProductImage).where(ProductImage.product_id.in_(ids)).order_by(*order)):
        own.setdefault(row.product_id, row)  # type: ignore[arg-type]
    by_model: dict[uuid.UUID, list[ProductImage]] = {}
    if model_ids:
        for row in db.scalars(
            select(ProductImage).where(ProductImage.product_model_id.in_(model_ids)).order_by(*order)
        ):
            by_model.setdefault(row.product_model_id, []).append(row)  # type: ignore[arg-type]
    covers: dict[uuid.UUID, tuple[str, str]] = {}
    for product in products:
        chosen = own.get(product.id)
        if chosen is None and product.product_model_id in by_model:
            candidates = by_model[product.product_model_id]
            values = {(key.lower(), str(value).lower()) for key, value in (product.variant_attributes or {}).items()}
            chosen = next(
                (
                    row
                    for row in candidates
                    if row.attribute_value is not None
                    and ((row.attribute_key or "").lower(), row.attribute_value.lower()) in values
                ),
                None,
            ) or next((row for row in candidates if row.attribute_value is None), candidates[0])
        if chosen is not None:
            covers[product.id] = (media_storage.url(chosen.key), media_storage.url(chosen.thumb_key))
    return covers
