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


def _out(
    category: Category,
    by_category: dict[uuid.UUID, int],
    by_sub: dict[uuid.UUID, int],
    *,
    active_only: bool = False,
) -> CategoryOut:
    subs = category.sub_categories
    if active_only:
        subs = [sub for sub in subs if sub.is_active]
    return CategoryOut(
        id=category.id,
        name=category.name,
        code=category.code,
        description=category.description,
        product_count=by_category.get(category.id, 0),
        created_at=category.created_at,
        display_order=category.display_order,
        is_active=category.is_active,
        image_key=category.image_key,
        product_kinds=list(category.product_kinds or []),
        form_policy=category.form_policy or "",
        sub_categories=[
            SubCategoryOut(
                id=sub.id,
                category_id=category.id,
                name=sub.name,
                code=sub.code,
                description=sub.description,
                product_count=by_sub.get(sub.id, 0),
                display_order=sub.display_order,
                is_active=sub.is_active,
            )
            for sub in subs
        ],
    )


def list_categories(db: Session, *, active_only: bool = False) -> list[CategoryOut]:
    by_category, by_sub = _counts(db)
    rows = db.scalars(select(Category).order_by(Category.display_order, Category.name)).all()
    if active_only:
        rows = [row for row in rows if row.is_active]
    return [_out(row, by_category, by_sub, active_only=active_only) for row in rows]


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


def _veterinary_locked(code: str, kinds: list[str], active: bool) -> None:
    """Stage 2 has no veterinary licence, so that category cannot be switched on."""
    veterinary = code == "VET" or (kinds == ["VETERINARY"] and bool(kinds))
    if veterinary and active:
        raise ApiError(
            422,
            "veterinary_not_licensed",
            "Veterinary products stay off until a later licence allows them.",
        )


def assert_assignable(db: Session, category_id: uuid.UUID | None, sub_category_id: uuid.UUID | None) -> None:
    """A product cannot be filed under a category or subcategory that is switched off."""
    if category_id is not None:
        category = db.get(Category, category_id)
        if category is None:
            raise ApiError(422, "category_inactive", "Choose an active category.")
        if not category.is_active:
            raise ApiError(422, "category_inactive", "That category is inactive.")
    if sub_category_id is not None:
        sub = db.get(SubCategory, sub_category_id)
        if sub is None or not sub.is_active:
            raise ApiError(422, "category_inactive", "That sub-category is inactive.")
        if category_id is not None and sub.category_id != category_id:
            raise ApiError(422, "category_inactive", "That sub-category does not belong to the category.")


def create_category(db: Session, data: CategoryWrite) -> CategoryOut:
    if db.scalar(select(Category.id).where(func.lower(Category.name) == data.name.lower())) is not None:
        message = "A category with this name already exists."
        raise field_conflict(message, name=message)
    code = data.code or _unique_code(db, _code_from(data.name))
    _veterinary_locked(code, [], data.is_active)
    category = Category(
        name=data.name,
        code=code,
        description=data.description.strip(),
        display_order=data.display_order,
        is_active=data.is_active,
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
    if data.display_order is not None:
        category.display_order = data.display_order
    next_active = category.is_active if data.is_active is None else data.is_active
    next_code = category.code if data.code is None else data.code
    _veterinary_locked(next_code, list(category.product_kinds or []), next_active)
    if data.is_active is not None:
        category.is_active = data.is_active
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
    if not category.is_active:
        raise ApiError(422, "category_inactive", "Activate the category before adding a sub-category.")
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
            display_order=data.display_order,
            is_active=data.is_active,
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
    if data.display_order is not None:
        sub.display_order = data.display_order
    if data.is_active is not None:
        sub.is_active = data.is_active
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
