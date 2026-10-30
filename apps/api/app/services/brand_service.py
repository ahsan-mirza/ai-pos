import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError, field_conflict
from app.models.brand import Brand, ProductModel
from app.models.category import SubCategory
from app.models.product import Product
from app.schemas.inventory import (
    BrandOut,
    BrandWrite,
    CategoryUpdate,
    ProductModelOut,
    ProductModelUpdate,
    ProductModelWrite,
)
from app.services import fashion_attributes, list_cache
from app.services.category_service import _code_from


def _unique_code(db: Session, base: str) -> str:
    code, suffix = base, 2
    while db.scalar(select(Brand.id).where(Brand.code == code)) is not None:
        code = f"{base[:26]}-{suffix}"
        suffix += 1
    return code


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        message = "That name or code is already in use."
        raise field_conflict(message, name=message, code=message) from exc


def _brand(db: Session, brand_id: uuid.UUID) -> Brand:
    brand = db.get(Brand, brand_id)
    if brand is None:
        raise ApiError(404, "not_found", "Brand was not found.")
    return brand


def _sub(db: Session, sub_id: uuid.UUID) -> SubCategory:
    sub = db.get(SubCategory, sub_id)
    if sub is None:
        raise ApiError(422, "unknown_sub_category", "Sub-category does not exist.")
    return sub


def _model(db: Session, model_id: uuid.UUID) -> ProductModel:
    model = db.get(ProductModel, model_id)
    if model is None:
        raise ApiError(404, "not_found", "Model was not found.")
    return model


def resolve_brand(db: Session, name: str) -> Brand:
    """Free-text brand names (sync payloads, imports) map to the global list; unknown names become new brands."""
    cleaned = " ".join(name.split())
    brand = db.scalar(select(Brand).where(func.lower(Brand.name) == cleaned.lower()))
    if brand is None:
        brand = Brand(name=cleaned, code=_unique_code(db, _code_from(cleaned)), description="")
        db.add(brand)
        db.flush()
    return brand


def link(brand: Brand, sub: SubCategory | None) -> None:
    if sub is not None and all(item.id != sub.id for item in brand.sub_categories):
        brand.sub_categories.append(sub)


# --- Brands --------------------------------------------------------------------------------------


def _brand_counts(db: Session) -> tuple[dict[uuid.UUID, int], dict[uuid.UUID, int]]:
    models = dict(db.execute(select(ProductModel.brand_id, func.count()).group_by(ProductModel.brand_id)).all())
    products = dict(
        db.execute(
            select(Product.brand_id, func.count()).where(Product.brand_id.is_not(None)).group_by(Product.brand_id)
        ).all()
    )
    return models, products  # type: ignore[return-value]


def _brand_out(brand: Brand, models: dict[uuid.UUID, int], products: dict[uuid.UUID, int]) -> BrandOut:
    return BrandOut(
        id=brand.id,
        name=brand.name,
        code=brand.code,
        description=brand.description,
        sub_category_ids=[sub.id for sub in brand.sub_categories],
        model_count=models.get(brand.id, 0),
        product_count=products.get(brand.id, 0),
        created_at=brand.created_at,
    )


def _one_brand(db: Session, brand: Brand) -> BrandOut:
    db.refresh(brand)
    return _brand_out(brand, *_brand_counts(db))


def list_brands(db: Session, *, sub_category_id: uuid.UUID | None = None) -> list[BrandOut]:
    statement = select(Brand).order_by(Brand.name)
    if sub_category_id is not None:
        statement = statement.where(Brand.sub_categories.any(SubCategory.id == sub_category_id))
    models, products = _brand_counts(db)
    return [_brand_out(row, models, products) for row in db.scalars(statement).all()]


def create_brand(db: Session, data: BrandWrite) -> BrandOut:
    if db.scalar(select(Brand.id).where(func.lower(Brand.name) == data.name.lower())) is not None:
        message = "A brand with this name already exists."
        raise field_conflict(message, name=message)
    brand = Brand(
        name=data.name,
        code=data.code or _unique_code(db, _code_from(data.name)),
        description=data.description.strip(),
    )
    for sub_id in dict.fromkeys(data.sub_category_ids):
        link(brand, _sub(db, sub_id))
    db.add(brand)
    _commit(db)
    return _one_brand(db, brand)


def update_brand(db: Session, brand_id: uuid.UUID, data: CategoryUpdate) -> BrandOut:
    brand = _brand(db, brand_id)
    if data.name is not None and data.name != brand.name:
        clash = db.scalar(select(Brand.id).where(func.lower(Brand.name) == data.name.lower(), Brand.id != brand.id))
        if clash is not None:
            message = "A brand with this name already exists."
            raise field_conflict(message, name=message)
        brand.name = data.name
        for product in db.scalars(select(Product).where(Product.brand_id == brand.id)):
            product.brand = data.name
    if data.code is not None:
        brand.code = data.code
    if data.description is not None:
        brand.description = data.description.strip()
    _commit(db)
    list_cache.bump("models")
    return _one_brand(db, brand)


def delete_brand(db: Session, brand_id: uuid.UUID) -> None:
    brand = _brand(db, brand_id)
    if db.scalar(select(func.count()).select_from(ProductModel).where(ProductModel.brand_id == brand.id)):
        raise ApiError(409, "brand_in_use", "Delete or move this brand's models first.")
    if db.scalar(select(func.count()).select_from(Product).where(Product.brand_id == brand.id)):
        raise ApiError(409, "brand_in_use", "Products still use this brand.")
    db.delete(brand)
    db.commit()


def link_sub_category(db: Session, brand_id: uuid.UUID, sub_id: uuid.UUID) -> BrandOut:
    brand = _brand(db, brand_id)
    link(brand, _sub(db, sub_id))
    _commit(db)
    return _one_brand(db, brand)


def unlink_sub_category(db: Session, brand_id: uuid.UUID, sub_id: uuid.UUID) -> BrandOut:
    brand = _brand(db, brand_id)
    in_use = db.scalar(
        select(func.count())
        .select_from(ProductModel)
        .where(ProductModel.brand_id == brand.id, ProductModel.sub_category_id == sub_id)
    )
    if in_use:
        raise ApiError(409, "brand_in_use", f"{brand.name} still has models in this sub-category.")
    brand.sub_categories = [sub for sub in brand.sub_categories if sub.id != sub_id]
    _commit(db)
    return _one_brand(db, brand)


# --- Models --------------------------------------------------------------------------------------


def _variant_counts(db: Session) -> dict[uuid.UUID, int]:
    return dict(  # type: ignore[return-value]
        db.execute(
            select(Product.product_model_id, func.count())
            .where(Product.product_model_id.is_not(None))
            .group_by(Product.product_model_id)
        ).all()
    )


def _model_out(model: ProductModel, variants: dict[uuid.UUID, int]) -> ProductModelOut:
    sub = model.sub_category
    return ProductModelOut(
        id=model.id,
        brand_id=model.brand_id,
        brand_name=model.brand.name,
        category_id=sub.category_id,
        category_name=sub.category.name,
        sub_category_id=sub.id,
        sub_category_name=sub.name,
        name=model.name,
        code=model.code,
        release_year=model.release_year,
        description=model.description,
        variant_count=variants.get(model.id, 0),
        default_price_cents=model.default_price_cents,
        price_rules=model.price_rules or [],
        axis_swatches=model.axis_swatches or {},
        season=model.season,
        collection=model.collection,
        gender=model.gender,  # type: ignore[arg-type]
        material=model.material,
        fit=model.fit,
        care=model.care,
    )


def model_out(db: Session, model: ProductModel) -> ProductModelOut:
    db.refresh(model)
    return _model_out(model, _variant_counts(db))


def list_models(
    db: Session,
    *,
    sub_category_id: uuid.UUID | None = None,
    brand_id: uuid.UUID | None = None,
) -> list[ProductModelOut]:
    fingerprint = f"{brand_id or ''}|{sub_category_id or ''}"

    def load() -> list[dict[str, object]]:
        statement = select(ProductModel).order_by(ProductModel.release_year.desc().nulls_last(), ProductModel.name)
        if sub_category_id is not None:
            statement = statement.where(ProductModel.sub_category_id == sub_category_id)
        if brand_id is not None:
            statement = statement.where(ProductModel.brand_id == brand_id)
        variants = _variant_counts(db)
        rows = [_model_out(row, variants) for row in db.scalars(statement).unique().all()]
        return [row.model_dump(mode="json") for row in rows]

    cached = list_cache.remember("models", fingerprint, 30, load)
    return [ProductModelOut.model_validate(row) for row in cached]


def _name_taken(db: Session, brand_id: uuid.UUID, sub_id: uuid.UUID, name: str, exclude: uuid.UUID | None) -> bool:
    statement = select(ProductModel.id).where(
        ProductModel.brand_id == brand_id,
        ProductModel.sub_category_id == sub_id,
        func.lower(ProductModel.name) == name.lower(),
    )
    if exclude is not None:
        statement = statement.where(ProductModel.id != exclude)
    return db.scalar(statement) is not None


def create_model(db: Session, data: ProductModelWrite) -> ProductModelOut:
    brand = _brand(db, data.brand_id)
    sub = _sub(db, data.sub_category_id)
    if _name_taken(db, brand.id, sub.id, data.name, None):
        message = f"{brand.name} already has a model called {data.name} in {sub.name}."
        raise field_conflict(message, name=message)
    model = ProductModel(
        brand_id=brand.id,
        sub_category_id=sub.id,
        name=data.name,
        code=data.code,
        release_year=data.release_year,
        description=data.description.strip(),
        default_price_cents=data.default_price_cents,
        price_rules=[rule.model_dump() for rule in data.price_rules],
        axis_swatches=data.axis_swatches,
    )
    fashion_attributes.apply(model, data, only_sent=False)
    link(brand, sub)
    db.add(model)
    _commit(db)
    list_cache.bump("models")
    return model_out(db, model)


def _reprice_inherited(db: Session, model: ProductModel, user_id: uuid.UUID | None) -> None:
    """Rewrites variants that still follow the model. An explicit variant price is left as it is."""
    if model.default_price_cents is None:
        return
    from app.services import markdown_service
    from app.services.variant_keys import resolved_price

    products = db.scalars(
        select(Product).where(Product.product_model_id == model.id, Product.price_source != "override")
    )
    for product in products:
        price, source = resolved_price(model.default_price_cents, model.price_rules or [], product.variant_attributes)
        if price != product.price_cents:
            markdown_service.record(db, product, price, "BULK", user_id=user_id)
            product.price_cents = price
        product.price_source = source


def update_model(
    db: Session, model_id: uuid.UUID, data: ProductModelUpdate, *, user_id: uuid.UUID | None = None
) -> ProductModelOut:
    model = _model(db, model_id)
    if data.name is not None:
        if _name_taken(db, model.brand_id, model.sub_category_id, data.name, model.id):
            message = "Another model in this sub-category already has that name."
            raise field_conflict(message, name=message)
        model.name = data.name
    if "code" in data.model_fields_set:
        model.code = data.code
    if "release_year" in data.model_fields_set:
        model.release_year = data.release_year
    if data.description is not None:
        model.description = data.description.strip()
    if fashion_attributes.apply(model, data, only_sent=True):
        db.flush()
        fashion_attributes.push_to_variants(db, model)
    pricing_changed = False
    if "default_price_cents" in data.model_fields_set:
        model.default_price_cents = data.default_price_cents
        pricing_changed = True
    if "price_rules" in data.model_fields_set and data.price_rules is not None:
        model.price_rules = [rule.model_dump() for rule in data.price_rules]
        pricing_changed = True
    if "axis_swatches" in data.model_fields_set and data.axis_swatches is not None:
        model.axis_swatches = data.axis_swatches
    if pricing_changed:
        _reprice_inherited(db, model, user_id)
    _commit(db)
    list_cache.bump("models")
    return model_out(db, model)


def delete_model(db: Session, model_id: uuid.UUID) -> None:
    model = _model(db, model_id)
    if db.scalar(select(func.count()).select_from(Product).where(Product.product_model_id == model.id)):
        raise ApiError(409, "model_in_use", "Delete or move this model's variants first.")
    db.delete(model)
    db.commit()
    list_cache.bump("models")
