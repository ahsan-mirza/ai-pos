"""Fashion attributes (season, collection, gender, material, fit, care): set on a model and copied to its variants,
or set directly on a standalone product."""

from sqlalchemy import Select, select, update
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.models.brand import ProductModel
from app.models.product import Product
from app.schemas.catalogue import ATTRIBUTE_FIELDS, GENDERS, CatalogAttributesOut, FashionAttributes


def copy_from_model(model: ProductModel, product: Product) -> None:
    for field in ATTRIBUTE_FIELDS:
        setattr(product, field, getattr(model, field))


def apply(target: ProductModel | Product, data: FashionAttributes, *, only_sent: bool) -> bool:
    """Writes the attributes in `data` onto `target`; returns whether anything changed."""
    changed = False
    for field in ATTRIBUTE_FIELDS:
        if only_sent and field not in data.model_fields_set:
            continue
        value = getattr(data, field)
        if getattr(target, field) != value:
            setattr(target, field, value)
            changed = True
    return changed


def push_to_variants(db: Session, model: ProductModel) -> None:
    db.execute(
        update(Product)
        .where(Product.product_model_id == model.id)
        .values({field: getattr(model, field) for field in ATTRIBUTE_FIELDS})
        .execution_options(synchronize_session="fetch")
    )


def _distinct(db: Session, column: InstrumentedAttribute[str | None]) -> list[str]:
    rows = db.scalars(select(column).where(column.is_not(None)).distinct()).all()
    return sorted({value for value in rows if value}, key=str.lower)


def catalog_attributes(db: Session) -> CatalogAttributesOut:
    used_genders = set(_distinct(db, Product.gender)) | set(_distinct(db, ProductModel.gender))
    return CatalogAttributesOut(
        seasons=sorted(set(_distinct(db, Product.season)) | set(_distinct(db, ProductModel.season)), reverse=True),
        collections=sorted(set(_distinct(db, Product.collection)) | set(_distinct(db, ProductModel.collection))),
        genders=[gender for gender in GENDERS if gender in used_genders],
        materials=_distinct(db, Product.material),
        fits=_distinct(db, Product.fit),
    )


def filter_products(
    statement: Select[tuple[Product]],
    *,
    season: str | None = None,
    collection: str | None = None,
    gender: str | None = None,
) -> Select[tuple[Product]]:
    """Adds the attribute filters a list endpoint received."""
    if season:
        statement = statement.where(Product.season == season.strip().upper())
    if collection:
        statement = statement.where(Product.collection == collection.strip())
    if gender:
        statement = statement.where(Product.gender == gender.strip().lower())
    return statement
