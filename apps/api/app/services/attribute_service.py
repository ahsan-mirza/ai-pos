"""Copies business-type templates into the tenant and stores validated product values."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.errors import ApiError
from app.models.attribute import ProductAttributeDefinition, ProductAttributeValue
from app.models.product import Product
from app.services import attribute_catalog
from app.services.attribute_catalog import Coerced
from app.services.settings_service import load_settings


def profile_of(db: Session) -> str:
    return load_settings(db).business_profile or ""


def ensure(db: Session) -> list[ProductAttributeDefinition]:
    """Inserts missing template copies for this tenant's business type. Existing rows are left alone."""
    profile = profile_of(db)
    existing = {row.template_key or row.key: row for row in db.scalars(select(ProductAttributeDefinition)).all()}
    for template in attribute_catalog.for_profile(profile):
        if template.key in existing:
            continue
        db.add(
            ProductAttributeDefinition(
                key=template.key,
                name=template.name,
                description=template.description,
                data_type=template.data_type,
                unit=template.unit,
                options=list(template.options),
                profiles=list(template.profiles),
                required=False,
                searchable=template.filterable,
                filterable=template.filterable,
                active=True,
                sort_order=template.sort_order,
                origin="template",
                template_key=template.key,
            )
        )
    db.flush()
    rows = db.scalars(select(ProductAttributeDefinition).order_by(ProductAttributeDefinition.sort_order, ProductAttributeDefinition.name)).all()
    return list(rows)


def list_definitions(db: Session) -> list[ProductAttributeDefinition]:
    rows = ensure(db)
    db.commit()
    return rows


def create_definition(
    db: Session,
    *,
    name: str,
    key: str | None,
    data_type: str,
    unit: str,
    options: list[str],
    description: str,
    required: bool,
    searchable: bool,
    filterable: bool,
) -> ProductAttributeDefinition:
    if data_type not in {
        "text",
        "number",
        "decimal",
        "boolean",
        "date",
        "select",
        "multi_select",
        "measurement",
    }:
        raise ApiError(422, "invalid_attribute", "Choose a supported attribute type.")
    slug = key or attribute_catalog.slug(name)
    if not attribute_catalog.is_key(slug):
        raise ApiError(422, "invalid_attribute", "Use a short key of letters, numbers, and underscores.")
    ensure(db)
    if db.scalar(select(ProductAttributeDefinition.id).where(func.lower(ProductAttributeDefinition.key) == slug)) is not None:
        raise ApiError(409, "conflict", "An attribute with this key already exists.")
    row = ProductAttributeDefinition(
        key=slug,
        name=" ".join(name.split())[:80],
        description=description.strip()[:500],
        data_type=data_type,
        unit=unit.strip()[:16],
        options=[item.strip() for item in options if item.strip()][:40],
        profiles=[],
        required=required,
        searchable=searchable or filterable,
        filterable=filterable,
        active=True,
        sort_order=500,
        origin="custom",
        template_key=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_definition(db: Session, definition_id: uuid.UUID, changes: dict) -> ProductAttributeDefinition:
    row = db.get(ProductAttributeDefinition, definition_id)
    if row is None:
        raise ApiError(404, "not_found", "Attribute was not found.")
    if "data_type" in changes and changes["data_type"] != row.data_type:
        used = db.scalar(select(ProductAttributeValue.id).where(ProductAttributeValue.definition_id == row.id))
        if used is not None:
            raise ApiError(409, "attribute_in_use", "This attribute already has values, so its type stays as it is.")
        row.data_type = changes["data_type"]
    for field in ("name", "description", "unit", "required", "searchable", "filterable", "active", "sort_order"):
        if field in changes and changes[field] is not None:
            setattr(row, field, changes[field])
    if "options" in changes and changes["options"] is not None:
        row.options = [item.strip() for item in changes["options"] if item.strip()][:40]
    db.commit()
    db.refresh(row)
    return row


def definitions_by_key(db: Session) -> dict[str, ProductAttributeDefinition]:
    return {row.key: row for row in ensure(db) if row.active}


def check_mapping(mapping: dict[str, str], headers: list[str], standard: dict[str, str]) -> None:
    used = {header for header in standard.values() if header}
    seen: dict[str, str] = {}
    unknown = []
    for key, header in mapping.items():
        if not header:
            continue
        if not attribute_catalog.is_key(key):
            raise ApiError(422, "invalid_attribute", f"{key} is not an attribute key.")
        if header not in headers:
            unknown.append(header)
        elif header in used or header in seen:
            raise ApiError(422, "mapping_duplicate", f"{header} is already mapped.")
        elif attribute_catalog.is_tracking_header(header):
            raise ApiError(
                422,
                "tracking_field",
                f"{header} is inventory tracking. Map it to IMEI / serials or expiry, not a specification.",
            )
        else:
            seen[header] = key
    if unknown:
        raise ApiError(422, "mapping_unknown_column", f"Column not found in the file: {', '.join(sorted(set(unknown)))}.")


def row_issues(
    attributes: dict[str, str],
    definitions: dict[str, ProductAttributeDefinition],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for key, raw in attributes.items():
        definition = definitions.get(key)
        if definition is None:
            errors.append(f"Unknown attribute {key}.")
            continue
        if not raw.strip():
            if definition.required:
                errors.append(f"{definition.name} is required.")
            continue
        try:
            attribute_catalog.coerce(definition, raw)
        except ValueError as exc:
            errors.append(f"{definition.name} {exc}")
    return errors, warnings


def apply(db: Session, product: Product, attributes: dict[str, str], definitions: dict[str, ProductAttributeDefinition]) -> list[str]:
    """Writes typed values and the display copy on the product. Blank cells are skipped."""
    applied: list[str] = []
    specs = dict(product.specifications or {})
    for key, raw in attributes.items():
        if not str(raw).strip():
            continue
        definition = definitions.get(key)
        if definition is None:
            continue
        coerced = attribute_catalog.coerce(definition, raw)
        _upsert(db, product, definition, coerced)
        specs[key] = coerced.display
        if key == "brand":
            product.brand = coerced.display[:80]
        applied.append(key)
    if applied:
        product.specifications = specs
        flag_modified(product, "specifications")
    return applied


def _upsert(db: Session, product: Product, definition: ProductAttributeDefinition, coerced: Coerced) -> None:
    row = db.scalar(
        select(ProductAttributeValue).where(
            ProductAttributeValue.product_id == product.id,
            ProductAttributeValue.definition_id == definition.id,
        )
    )
    if row is None:
        row = ProductAttributeValue(product_id=product.id, definition_id=definition.id)
        db.add(row)
    row.text_value = coerced.text_value
    row.number_value = coerced.number_value
    row.bool_value = coerced.bool_value
    row.date_value = coerced.date_value
    row.unit = coerced.unit


def matches(db: Session, key: str, value: str):
    definition = db.scalar(select(ProductAttributeDefinition).where(ProductAttributeDefinition.key == key))
    if definition is None or not definition.active or not definition.filterable:
        raise ApiError(422, "attribute_not_filterable", "That attribute is not available as a filter.")
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        return Product.specifications[key].astext == value
    return func.json_extract(Product.specifications, f"$.{key}") == value
