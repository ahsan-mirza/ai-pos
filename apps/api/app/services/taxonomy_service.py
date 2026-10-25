"""Starter categories, brands, and models for a business type. Never creates a product."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.brand import Brand, ProductModel
from app.models.category import Category, SubCategory
from app.services.brand_service import link, resolve_brand
from app.services.category_service import resolve_by_name

_PATH = Path(__file__).resolve().parents[4] / "packages" / "catalog" / "taxonomy.json"


@cache
def _catalog() -> dict:
    return json.loads(_PATH.read_text(encoding="utf-8"))


def _named(db: Session, model: type[Category] | type[Brand], name: str):
    return db.scalar(select(model).where(func.lower(model.name) == name.lower()))


def _sub(db: Session, category: Category, name: str) -> SubCategory | None:
    return db.scalar(
        select(SubCategory).where(
            SubCategory.category_id == category.id,
            func.lower(SubCategory.name) == name.lower(),
        )
    )


def ensure_taxonomy(db: Session, profile: str) -> int:
    """Insert this profile's catalog where the name is missing.

    Matching is case-insensitive. Names, descriptions, and brand links that already exist are left
    as they are, and nothing is deleted. A profile that has no catalog is skipped.
    """
    tree = _catalog().get(profile)
    if not tree:
        return 0
    added = 0
    for spec in tree["categories"]:
        name = " ".join(spec["name"].split())
        existing = _named(db, Category, name)
        category, _ = resolve_by_name(db, name, None)
        if existing is None:
            category.description = (spec.get("description") or "")[:255]
            added += 1
        for sub_name in spec.get("sub_categories", []):
            cleaned = " ".join(sub_name.split())
            if _sub(db, category, cleaned) is None:
                resolve_by_name(db, category.name, cleaned)
                added += 1
    for spec in tree.get("brands", []):
        name = " ".join(spec["name"].split())
        existing = _named(db, Brand, name)
        brand = resolve_brand(db, name)
        if existing is None:
            brand.description = (spec.get("description") or "")[:255]
            added += 1
        for model_spec in spec.get("models", []):
            added += _ensure_model(db, brand, model_spec)
    db.flush()
    return added


def _ensure_model(db: Session, brand: Brand, spec: dict) -> int:
    category_name = " ".join(spec["category"].split())
    sub_name = " ".join(spec["sub_category"].split())
    category = _named(db, Category, category_name)
    sub = _sub(db, category, sub_name) if category is not None else None
    if category is None or sub is None:
        raise ValueError(
            f"{brand.name} model {spec['name']} points at {category_name} / {sub_name}, which is not in this catalog."
        )
    link(brand, sub)
    model_name = " ".join(spec["name"].split())
    found = db.scalar(
        select(ProductModel.id).where(
            ProductModel.brand_id == brand.id,
            ProductModel.sub_category_id == sub.id,
            func.lower(ProductModel.name) == model_name.lower(),
        )
    )
    if found is not None:
        return 0
    db.add(
        ProductModel(
            brand_id=brand.id,
            sub_category_id=sub.id,
            name=model_name,
            code=(spec.get("code") or None),
            release_year=spec.get("release_year"),
            description="",
        )
    )
    db.flush()
    return 1
