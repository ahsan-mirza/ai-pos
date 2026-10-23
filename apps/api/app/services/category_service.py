import re
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError, field_conflict
from app.models.category import Category, SubCategory
from app.models.product import Product
from app.schemas.inventory import CategoryOut, CategoryUpdate, CategoryWrite, SubCategoryOut


def _code_from(name: str) -> str:
    return "-".join(re.findall(r"[A-Za-z0-9]+", name.upper()))[:28] or "CAT"


def _unique_code(db: Session, base: str, *, category_id: uuid.UUID | None = None) -> str:
    code, suffix = base, 2
    while True:
        if category_id is None:
            clash = db.scalar(select(Category.id).where(Category.code == code))
        else:
            clash = db.scalar(
                select(SubCategory.id).where(SubCategory.category_id == category_id, SubCategory.code == code)
            )
        if clash is None:
            return code
        code = f"{base[:26]}-{suffix}"
        suffix += 1


def resolve_by_name(
    db: Session,
    category_name: str,
    sub_category_name: str | None,
) -> tuple[Category, SubCategory | None]:
    """Sync payloads name their category; unknown names become new categories so offline registers keep working."""
    name = " ".join(category_name.split())
    category = db.scalar(select(Category).where(func.lower(Category.name) == name.lower()))
    if category is None:
        category = Category(name=name, code=_unique_code(db, _code_from(name)), description="")
        db.add(category)
        db.flush()
    sub = None
    if sub_category_name:
        sub_name = " ".join(sub_category_name.split())
        sub = db.scalar(
            select(SubCategory).where(
                SubCategory.category_id == category.id, func.lower(SubCategory.name) == sub_name.lower()
            )
        )
        if sub is None:
            sub = SubCategory(
                category_id=category.id,
                name=sub_name,
                code=_unique_code(db, _code_from(sub_name), category_id=category.id),
                description="",
            )
            db.add(sub)
            db.flush()
    return category, sub


def _counts(db: Session) -> tuple[dict[uuid.UUID, int], dict[uuid.UUID, int]]:
    by_category = dict(
        db.execute(
            select(Product.category_id, func.count())
            .where(Product.category_id.is_not(None))
            .group_by(Product.category_id)
        ).all()
    )
    by_sub = dict(
        db.execute(
            select(Product.sub_category_id, func.count())
            .where(Product.sub_category_id.is_not(None))
            .group_by(Product.sub_category_id)
        ).all()
    )
    return by_category, by_sub  # type: ignore[return-value]


def _out(category: Category, by_category: dict[uuid.UUID, int], by_sub: dict[uuid.UUID, int]) -> CategoryOut:
    return CategoryOut(
        id=category.id,
        name=category.name,
        code=category.code,
        description=category.description,
        product_count=by_category.get(category.id, 0),
        created_at=category.created_at,
        sub_categories=[
            SubCategoryOut(
                id=sub.id,
                category_id=category.id,
                name=sub.name,
                code=sub.code,
                description=sub.description,
                product_count=by_sub.get(sub.id, 0),
            )
            for sub in category.sub_categories
        ],
    )


def list_categories(db: Session) -> list[CategoryOut]:
    by_category, by_sub = _counts(db)
    return [_out(row, by_category, by_sub) for row in db.scalars(select(Category).order_by(Category.name)).all()]


def _one(db: Session, category: Category) -> CategoryOut:
    db.refresh(category)
    by_category, by_sub = _counts(db)
    return _out(category, by_category, by_sub)


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        message = "That name or code is already in use."
        raise field_conflict(message, name=message, code=message) from exc


def _category(db: Session, category_id: uuid.UUID) -> Category:
    category = db.get(Category, category_id)
    if category is None:
        raise ApiError(404, "not_found", "Category was not found.")
    return category


def _sub(db: Session, sub_id: uuid.UUID) -> SubCategory:
    sub = db.get(SubCategory, sub_id)
    if sub is None:
        raise ApiError(404, "not_found", "Sub-category was not found.")
    return sub


def create_category(db: Session, data: CategoryWrite) -> CategoryOut:
    if db.scalar(select(Category.id).where(func.lower(Category.name) == data.name.lower())) is not None:
        message = "A category with this name already exists."
        raise field_conflict(message, name=message)
    category = Category(
        name=data.name,
        code=data.code or _unique_code(db, _code_from(data.name)),
        description=data.description.strip(),
    )
    db.add(category)
    _commit(db)
    return _one(db, category)


def update_category(db: Session, category_id: uuid.UUID, data: CategoryUpdate) -> CategoryOut:
    category = _category(db, category_id)
    if data.name is not None and data.name != category.name:
        clash = db.scalar(
            select(Category.id).where(func.lower(Category.name) == data.name.lower(), Category.id != category.id)
        )
        if clash is not None:
            message = "A category with this name already exists."
            raise field_conflict(message, name=message)
        category.name = data.name
        db.execute(update(Product).where(Product.category_id == category.id).values(category=data.name))
    if data.code is not None:
        category.code = data.code
    if data.description is not None:
        category.description = data.description.strip()
    _commit(db)
    return _one(db, category)


def delete_category(db: Session, category_id: uuid.UUID) -> None:
    category = _category(db, category_id)
    if db.scalar(select(func.count()).select_from(Product).where(Product.category_id == category.id)):
        raise ApiError(409, "category_in_use", "Move this category's products before deleting it.")
    db.delete(category)
    db.commit()


def create_sub_category(db: Session, category_id: uuid.UUID, data: CategoryWrite) -> CategoryOut:
    category = _category(db, category_id)
    clash = db.scalar(
        select(SubCategory.id).where(
            SubCategory.category_id == category.id, func.lower(SubCategory.name) == data.name.lower()
        )
    )
    if clash is not None:
        message = f"{category.name} already has a sub-category with this name."
        raise field_conflict(message, name=message)
    db.add(
        SubCategory(
            category_id=category.id,
            name=data.name,
            code=data.code or _unique_code(db, _code_from(data.name), category_id=category.id),
            description=data.description.strip(),
        )
    )
    _commit(db)
    return _one(db, category)


def update_sub_category(db: Session, sub_id: uuid.UUID, data: CategoryUpdate) -> CategoryOut:
    sub = _sub(db, sub_id)
    if data.name is not None:
        sub.name = data.name
    if data.code is not None:
        sub.code = data.code
    if data.description is not None:
        sub.description = data.description.strip()
    _commit(db)
    return _one(db, _category(db, sub.category_id))


def delete_sub_category(db: Session, sub_id: uuid.UUID) -> CategoryOut:
    sub = _sub(db, sub_id)
    if db.scalar(select(func.count()).select_from(Product).where(Product.sub_category_id == sub.id)):
        raise ApiError(409, "sub_category_in_use", "Move this sub-category's products before deleting it.")
    category_id = sub.category_id
    db.delete(sub)
    db.commit()
    return _one(db, _category(db, category_id))
