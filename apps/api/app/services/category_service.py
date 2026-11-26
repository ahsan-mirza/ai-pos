import re
import uuid

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError, field_conflict
from app.models.audit_log import AuditLog
from app.models.brand import ProductModel
from app.models.category import Category, SubCategory
from app.models.margin import MarginPolicy
from app.models.product import Product
from app.models.replenishment import SeasonalEvent
from app.models.stock_count import StockCount
from app.models.warranty import WarrantyPolicy, WarrantyRegistration
from app.schemas.inventory import (
    AssignedModelOut,
    CategoryModelsOut,
    CategoryOut,
    CategoryUpdate,
    CategoryWrite,
    SubCategoryOut,
)
from app.services import audit, brand_service, list_cache


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


def _destination_error(message: str) -> ApiError:
    return ApiError(422, "destination_invalid", message, details={"fields": {"destination_category_id": message}})


def _locked_category(db: Session, category_id: uuid.UUID) -> Category:
    statement = select(Category).where(Category.id == category_id)
    bind = db.get_bind()
    if bind is not None and bind.dialect.name != "sqlite":
        statement = statement.with_for_update()
    category = db.scalars(statement).one_or_none()
    if category is None:
        raise ApiError(404, "not_found", "Category was not found.")
    return category


def _models_on(db: Session, category_id: uuid.UUID) -> list[ProductModel]:
    statement = (
        select(ProductModel)
        .join(SubCategory, ProductModel.sub_category_id == SubCategory.id)
        .where(SubCategory.category_id == category_id)
        .order_by(ProductModel.name)
    )
    return list(db.scalars(statement).unique())


def _model_name_taken(
    db: Session, brand_id: uuid.UUID, sub_id: uuid.UUID, name: str, exclude: uuid.UUID
) -> bool:
    statement = select(ProductModel.id).where(
        ProductModel.brand_id == brand_id,
        ProductModel.sub_category_id == sub_id,
        func.lower(ProductModel.name) == name.lower(),
        ProductModel.id != exclude,
    )
    return db.scalar(statement) is not None


def _refile_products(
    db: Session,
    source: Category,
    destination: Category,
    plan: list[tuple[ProductModel, SubCategory]],
    sub_ids: list[uuid.UUID],
) -> None:
    """Point products at the destination. Rows, prices, and stock stay; only the category link changes."""
    clauses = [Product.category_id == source.id]
    if sub_ids:
        clauses.append(Product.sub_category_id.in_(sub_ids))
    model_ids = [model.id for model, _target in plan]
    if model_ids:
        clauses.append(Product.product_model_id.in_(model_ids))
    products = list(db.scalars(select(Product).where(or_(*clauses))))
    targets = {model.id: target for model, target in plan}
    fallback = next((target for _model, target in plan), None)
    for product in products:
        target = targets.get(product.product_model_id) if product.product_model_id is not None else fallback
        if target is None or target.category_id != destination.id:
            continue
        product.category_id = destination.id
        product.category = destination.name
        product.sub_category_id = target.id


def _still_holding(db: Session, category_id: uuid.UUID, sub_ids: list[uuid.UUID]) -> bool:
    product_clause = [Product.category_id == category_id]
    if sub_ids:
        product_clause.append(Product.sub_category_id.in_(sub_ids))
    if db.scalar(select(func.count()).select_from(Product).where(or_(*product_clause))):
        return True
    return bool(
        sub_ids
        and db.scalar(select(func.count()).select_from(ProductModel).where(ProductModel.sub_category_id.in_(sub_ids)))
    )


def assigned_models(db: Session, category_id: uuid.UUID) -> CategoryModelsOut:
    category = _category(db, category_id)
    models = _models_on(db, category.id)
    return CategoryModelsOut(
        model_count=len(models),
        models=[
            AssignedModelOut(
                id=model.id,
                name=model.name,
                brand_name=model.brand.name,
                sub_category_name=model.sub_category.name,
            )
            for model in models
        ],
    )


def move_models_and_delete(
    db: Session,
    category_id: uuid.UUID,
    destination_id: uuid.UUID,
    event_id: uuid.UUID | None = None,
) -> None:
    """Move models and their products onto the destination, then delete the source category."""
    if event_id is not None and db.scalar(select(AuditLog.id).where(AuditLog.client_event_id == event_id)):
        return
    source = _locked_category(db, category_id)
    if destination_id == source.id:
        raise _destination_error("Choose a different category.")
    destination = db.get(Category, destination_id)
    if destination is None or not destination.is_active:
        raise _destination_error("Choose an active category.")
    models = _models_on(db, source.id)
    active_subs = [sub for sub in destination.sub_categories if sub.is_active]
    if models and not active_subs:
        raise _destination_error("Choose an active category that has a sub-category.")
    ordered = sorted(active_subs, key=lambda sub: (sub.display_order, sub.name.lower()))
    plan: list[tuple[ProductModel, SubCategory]] = []
    for model in models:
        target = next((sub for sub in ordered if sub.name.lower() == model.sub_category.name.lower()), None)
        target = target or ordered[0]
        if _model_name_taken(db, model.brand_id, target.id, model.name, model.id):
            message = f"{model.brand.name} already has a model called {model.name} in {target.name}."
            raise field_conflict(message, destination_category_id=message)
        plan.append((model, target))
    sub_ids = list(db.scalars(select(SubCategory.id).where(SubCategory.category_id == source.id)))
    try:
        moved: list[dict[str, str]] = []
        for model, target in plan:
            previous = model.sub_category_id
            model.sub_category_id = target.id
            brand_service.link(model.brand, target)
            moved.append(
                {
                    "id": str(model.id),
                    "name": model.name,
                    "from_sub_category_id": str(previous),
                    "to_sub_category_id": str(target.id),
                }
            )
        _refile_products(db, source, destination, plan, sub_ids)
        if moved:
            audit.record(
                db,
                action_type="UPDATE",
                action="category.reassign_models",
                target_entity="Category",
                target_entity_id=source.id,
                old_values={"category_id": str(source.id)},
                new_values={"category_id": str(destination.id)},
                details={"destination_category_id": str(destination.id), "models": moved},
            )
        audit.record(
            db,
            action_type="DELETE",
            action="category.delete",
            target_entity="Category",
            target_entity_id=source.id,
            old_values={"name": source.name},
            details={"destination_category_id": str(destination.id), "model_count": len(moved)},
            client_event_id=event_id,
        )
        _release_category_links(db, source.id)
        if _still_holding(db, source.id, sub_ids):
            raise ApiError(409, "category_in_use", "Move this category's products before deleting it.")
        db.delete(source)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(
            409,
            "category_in_use",
            "The category could not be deleted. Its models were left where they were.",
        ) from exc
    except ApiError:
        db.rollback()
        raise
    list_cache.bump("models")


def delete_category(db: Session, category_id: uuid.UUID) -> None:
    category = _category(db, category_id)
    sub_ids = list(db.scalars(select(SubCategory.id).where(SubCategory.category_id == category.id)))
    product_clause = [Product.category_id == category.id]
    if sub_ids:
        product_clause.append(Product.sub_category_id.in_(sub_ids))
    if db.scalar(select(func.count()).select_from(Product).where(or_(*product_clause))):
        raise ApiError(409, "category_in_use", "Move this category's products before deleting it.")
    if sub_ids and db.scalar(
        select(func.count()).select_from(ProductModel).where(ProductModel.sub_category_id.in_(sub_ids))
    ):
        raise ApiError(409, "category_in_use", "Move this category's models before deleting it.")
    _release_category_links(db, category.id)
    db.delete(category)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(
            409,
            "category_in_use",
            "This category is still used. Move what references it, then delete it.",
        ) from exc


def _release_category_links(db: Session, category_id: uuid.UUID) -> None:
    """Drop rules that only exist for this category. History rows keep their record and lose the link."""
    policy_ids = list(db.scalars(select(WarrantyPolicy.id).where(WarrantyPolicy.category_id == category_id)))
    if policy_ids and db.scalar(
        select(func.count()).select_from(WarrantyRegistration).where(WarrantyRegistration.policy_id.in_(policy_ids))
    ):
        raise ApiError(
            409,
            "category_in_use",
            "This category is used by a warranty policy that already covers a sale.",
        )
    if policy_ids:
        db.execute(sql_delete(WarrantyPolicy).where(WarrantyPolicy.id.in_(policy_ids)))
    db.execute(sql_delete(MarginPolicy).where(MarginPolicy.category_id == category_id))
    db.execute(update(SeasonalEvent).where(SeasonalEvent.category_id == category_id).values(category_id=None))
    db.execute(update(StockCount).where(StockCount.category_id == category_id).values(category_id=None))


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
    if db.scalar(select(func.count()).select_from(ProductModel).where(ProductModel.sub_category_id == sub.id)):
        raise ApiError(409, "sub_category_in_use", "Move this sub-category's models before deleting it.")
    category_id = sub.category_id
    db.delete(sub)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(
            409,
            "sub_category_in_use",
            "This sub-category is still used. Move what references it, then delete it.",
        ) from exc
    return _one(db, _category(db, category_id))
