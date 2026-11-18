"""Pharmacy product extension. One product row, one stock ledger, no lot on the master."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, has_capability
from app.core.errors import ApiError, field_conflict
from app.models.category import Category, SubCategory
from app.models.pharmacy import PharmacyProductDetails, ProductDocument, ProductIngredient, SubstitutionGroup
from app.models.product import Product
from app.schemas.pharmacy import PharmacyProductOut, PharmacyWrite
from app.services import audit, category_service, uom_service
from app.services.settings_service import cached_settings

_MEDICINE = frozenset({"MEDICINE"})
_PACKED = frozenset({"MEDICINE", "SUPPLEMENT", "COSMETIC", "PERSONAL_CARE", "NUTRITION"})
_BRANDED = frozenset({"COSMETIC", "PERSONAL_CARE"})


def price_state(control: str, minimum: int | None, maximum: int | None) -> str:
    """NONE is not a missing price. A required official price with no amount stays MISSING."""
    if control == "NONE":
        return "NOT_REQUIRED"
    if control == "MINIMUM":
        return "ENTERED" if minimum is not None else "MISSING"
    if control in {"MAXIMUM", "FIXED"}:
        return "ENTERED" if maximum is not None else "MISSING"
    return "MISSING"


def apply(db: Session, product: Product, data: PharmacyWrite | None, *, creating: bool) -> None:
    """Store or replace the pharmacy block. Omitted data leaves an existing block alone."""
    if data is None:
        return
    _require_pharmacy(db)
    previous = None if creating else db.get(PharmacyProductDetails, product.id)
    old_class = None if previous is None else previous.dispensing_class
    _validate(db, product, data)
    details = previous or PharmacyProductDetails(product_id=product.id, product_kind=data.product_kind, dispensing_class=data.dispensing_class)
    if previous is None:
        db.add(details)
    _copy(details, data)
    db.flush()
    product.generic_name = data.generic_name or None
    product.gtin = data.gtin or None
    _replace_ingredients(db, details, data)
    _replace_documents(db, details, product, data)
    if creating or old_class != details.dispensing_class:
        audit.record(
            db,
            action_type="UPDATE",
            action="pharmacy.dispensing_class",
            target_entity="Product",
            target_entity_id=product.id,
            old_values=None if old_class is None else {"dispensing_class": old_class},
            new_values={"dispensing_class": details.dispensing_class, "product_kind": details.product_kind},
        )


def get_product(db: Session, product_id: uuid.UUID) -> PharmacyProductOut:
    _require_pharmacy(db)
    product = db.get(Product, product_id)
    details = db.get(PharmacyProductDetails, product_id)
    if product is None or details is None:
        raise ApiError(404, "not_found", "Pharmacy product was not found.")
    return _out(db, product, details)


def list_products(db: Session, *, query: str = "", limit: int = 50) -> list[PharmacyProductOut]:
    _require_pharmacy(db)
    statement = (
        select(Product, PharmacyProductDetails)
        .join(PharmacyProductDetails, PharmacyProductDetails.product_id == Product.id)
        .order_by(Product.name)
        .limit(min(max(limit, 1), 100))
    )
    needle = " ".join(query.lower().split())
    if needle:
        like = f"%{needle}%"
        statement = statement.where(
            or_(
                Product.search_text.like(like),
                Product.name.ilike(like),
                Product.sku.ilike(like),
                Product.barcode.ilike(like),
            )
        )
    rows = db.execute(statement).all()
    return [_out(db, product, details) for product, details in rows]


def _require_pharmacy(db: Session) -> None:
    profile = cached_settings(db).business_profile
    if profile != "pharmacy" or not has_capability(db, Capability.PHARMACY_CATALOG):
        raise ApiError(422, "profile_not_pharmacy", "Pharmacy product details belong to a pharmacy business.")


def _validate(db: Session, product: Product, data: PharmacyWrite) -> None:
    if data.product_kind == "VETERINARY":
        raise ApiError(422, "veterinary_not_licensed", "Veterinary products stay off until a later licence allows them.")
    if data.fractional_dispensing_allowed:
        raise ApiError(422, "fractional_dispensing", "Community pharmacy packs use a whole number of base units.")
    if data.offline_policy == "ALLOW" and data.dispensing_class != "OTC":
        raise ApiError(422, "offline_policy", "Only an OTC product can be marked for offline sale.")
    if data.price_control == "NONE" and (data.min_price_cents is not None or data.max_price_cents is not None):
        raise ApiError(422, "price_control", "A product without price control does not carry an official price.")
    if data.temp_min_c is not None and data.temp_max_c is not None and data.temp_min_c > data.temp_max_c:
        raise ApiError(422, "storage", "The minimum storage temperature is above the maximum.")
    _pack(db, data.selling_unit_code or data.base_unit_code, data.units_per_pack)
    category_service.assert_assignable(db, product.category_id, product.sub_category_id)
    _kind_allowed(db, product, data.product_kind)
    _required(product, data)
    _ingredients(data)
    if data.substitution_group_id is not None and db.get(SubstitutionGroup, data.substitution_group_id) is None:
        raise ApiError(422, "substitution_group", "That substitution group is not in this pharmacy.")
    if data.gtin:
        clash = db.scalar(select(Product.id).where(Product.gtin == data.gtin, Product.id != product.id))
        if clash is not None:
            raise field_conflict("GTIN is already in use.", gtin="GTIN is already in use.")


def _pack(db: Session, selling: str, factor: int) -> None:
    if factor < 1:
        raise ApiError(422, "pack_factor", "Pack conversion must be a positive whole number.")
    known = uom_service.units(db)
    option = known.get(selling)
    if option is None:
        return
    unit_factor = option[0].factor
    if selling == "PIECE" and factor != 1:
        raise ApiError(422, "pack_factor", "The piece unit converts as 1.")
    if unit_factor > 1 and factor != unit_factor:
        raise ApiError(422, "pack_factor", "The pack factor must match the selling unit.")


def _kind_allowed(db: Session, product: Product, kind: str) -> None:
    if product.category_id is None:
        return
    category = db.get(Category, product.category_id)
    if category is None:
        return
    allowed = [str(item) for item in (category.product_kinds or [])]
    if allowed and kind not in allowed:
        raise ApiError(422, "product_kind", "That product kind is not accepted in this category.")


def _required(product: Product, data: PharmacyWrite) -> None:
    missing: list[str] = []
    if not data.dispensing_class:
        missing.append("dispensing_class")
    if not data.base_unit_code:
        missing.append("base_unit_code")
    if data.product_kind in _MEDICINE:
        if not data.generic_name:
            missing.append("generic_name")
        if data.strength_amount is None or data.strength_amount <= 0:
            missing.append("strength_amount")
        if not data.strength_unit:
            missing.append("strength_unit")
        if not data.dosage_form:
            missing.append("dosage_form")
        if not data.route:
            missing.append("route")
    if data.product_kind == "DEVICE" and not data.manufacturer:
        missing.append("manufacturer")
    if data.product_kind in _BRANDED and not (product.brand or "").strip():
        missing.append("brand")
    pack = data.pack_size_label or str((product.specifications or {}).get("volume") or "").strip()
    if data.product_kind in _PACKED and not pack:
        missing.append("pack_size_label")
    if missing:
        raise ApiError(422, "pharmacy_required", "Required pharmacy fields are missing.", details={"fields": missing})


def _ingredients(data: PharmacyWrite) -> None:
    seen: set[str] = set()
    active = 0
    for row in data.ingredients:
        key = row.name.casefold()
        if key in seen:
            raise ApiError(422, "ingredient", f"{row.name} is listed more than once.")
        seen.add(key)
        if row.is_active_ingredient:
            active += 1
        if data.product_kind in _MEDICINE and row.is_active_ingredient:
            if row.strength_amount is None or row.strength_amount <= 0 or not row.strength_unit:
                raise ApiError(422, "ingredient", f"{row.name} needs a strength and a unit.")
    if data.product_kind in _MEDICINE and active < 1:
        raise ApiError(422, "ingredient", "A medicine needs at least one active ingredient.")


def _copy(details: PharmacyProductDetails, data: PharmacyWrite) -> None:
    details.product_kind = data.product_kind
    details.dispensing_class = data.dispensing_class
    details.classification_source = "TENANT_DECLARED"
    details.generic_name = data.generic_name
    details.manufacturer = data.manufacturer
    details.marketing_authorization_holder = data.marketing_authorization_holder
    details.country_of_origin = data.country_of_origin
    details.description = data.description
    details.gtin = data.gtin
    details.manufacturer_product_ref = data.manufacturer_product_ref
    details.dosage_form = data.dosage_form
    details.route = data.route
    details.strength_amount = data.strength_amount
    details.strength_unit = data.strength_unit
    details.strength_display = data.strength_display or _display(data.strength_amount, data.strength_unit)
    details.concentration = data.concentration
    details.pack_size_label = data.pack_size_label
    details.units_per_pack = data.units_per_pack
    details.base_unit_code = data.base_unit_code
    details.purchase_unit_code = data.purchase_unit_code or data.base_unit_code
    details.selling_unit_code = data.selling_unit_code or data.base_unit_code
    details.dispense_unit_code = data.dispense_unit_code or data.base_unit_code
    details.fractional_dispensing_allowed = False
    details.pharmaceutical_class = data.pharmaceutical_class
    details.registration_number = _blank(data.registration_number)
    details.registration_authority = _blank(data.registration_authority)
    details.marketing_authorization_ref = _blank(data.marketing_authorization_ref)
    details.storage_condition = data.storage_condition
    details.temp_min_c = data.temp_min_c
    details.temp_max_c = data.temp_max_c
    details.cold_chain = data.cold_chain
    details.handling_instructions = data.handling_instructions
    details.warnings_text = data.warnings_text
    details.price_control = data.price_control
    details.min_price_cents = data.min_price_cents
    details.max_price_cents = data.max_price_cents
    fixed = data.price_control == "FIXED"
    details.discount_eligible = False if fixed else data.discount_eligible
    details.promotion_eligible = False if fixed else data.promotion_eligible
    details.offline_policy = data.offline_policy
    details.substitution_group_id = data.substitution_group_id


def _replace_ingredients(db: Session, details: PharmacyProductDetails, data: PharmacyWrite) -> None:
    db.execute(delete(ProductIngredient).where(ProductIngredient.product_id == details.product_id))
    for position, row in enumerate(data.ingredients):
        db.add(
            ProductIngredient(
                product_id=details.product_id,
                position=position,
                name=row.name,
                strength_amount=row.strength_amount,
                strength_unit=row.strength_unit,
                is_active_ingredient=row.is_active_ingredient,
            )
        )
    db.flush()
    db.expire(details, ["ingredients"])


def _replace_documents(db: Session, details: PharmacyProductDetails, product: Product, data: PharmacyWrite) -> None:
    details.leaflet_document_id = None
    db.flush()
    db.execute(delete(ProductDocument).where(ProductDocument.product_id == product.id))
    leaflet: ProductDocument | None = None
    for row in data.documents:
        document = ProductDocument(
            product_id=product.id,
            kind=row.kind,
            title=row.title,
            reference=row.reference,
            storage_key=(row.storage_key or "").strip() or None,
        )
        db.add(document)
        if leaflet is None and row.kind == "leaflet":
            leaflet = document
    db.flush()
    if leaflet is not None:
        details.leaflet_document_id = leaflet.id


def _out(db: Session, product: Product, details: PharmacyProductDetails) -> PharmacyProductOut:
    sub = ""
    if product.sub_category_id is not None:
        row = db.get(SubCategory, product.sub_category_id)
        sub = "" if row is None else row.name
    state = price_state(details.price_control, details.min_price_cents, details.max_price_cents)
    documents = db.scalars(
        select(ProductDocument).where(ProductDocument.product_id == product.id).order_by(ProductDocument.title)
    ).all()
    return PharmacyProductOut(
        product_id=product.id,
        name=product.name,
        sku=product.sku,
        barcode=product.barcode,
        brand=product.brand or "",
        category=product.category or "",
        sub_category=sub,
        price_cents=product.price_cents,
        tax_category=product.tax_category,
        is_active=product.is_active,
        updated_at=product.updated_at,
        product_kind=details.product_kind,
        dispensing_class=details.dispensing_class,
        classification_source=details.classification_source,
        generic_name=details.generic_name,
        manufacturer=details.manufacturer,
        marketing_authorization_holder=details.marketing_authorization_holder,
        country_of_origin=details.country_of_origin,
        description=details.description,
        gtin=details.gtin,
        manufacturer_product_ref=details.manufacturer_product_ref,
        dosage_form=details.dosage_form,
        route=details.route,
        strength_amount=details.strength_amount,
        strength_unit=details.strength_unit,
        strength_display=details.strength_display,
        concentration=details.concentration,
        pack_size_label=details.pack_size_label,
        units_per_pack=details.units_per_pack,
        base_unit_code=details.base_unit_code,
        purchase_unit_code=details.purchase_unit_code,
        selling_unit_code=details.selling_unit_code,
        dispense_unit_code=details.dispense_unit_code,
        fractional_dispensing_allowed=details.fractional_dispensing_allowed,
        pharmaceutical_class=details.pharmaceutical_class,
        registration_number=details.registration_number,
        registration_authority=details.registration_authority,
        marketing_authorization_ref=details.marketing_authorization_ref,
        storage_condition=details.storage_condition,
        temp_min_c=details.temp_min_c,
        temp_max_c=details.temp_max_c,
        cold_chain=details.cold_chain,
        handling_instructions=details.handling_instructions,
        warnings_text=details.warnings_text,
        price_control=details.price_control,
        min_price_cents=details.min_price_cents,
        max_price_cents=details.max_price_cents,
        discount_eligible=details.discount_eligible,
        promotion_eligible=details.promotion_eligible,
        official_price_state=state,
        sale_blocked=state == "MISSING",
        offline_policy=details.offline_policy,
        substitution_group_id=details.substitution_group_id,
        ingredients=[
            {
                "id": row.id,
                "position": row.position,
                "name": row.name,
                "strength_amount": row.strength_amount,
                "strength_unit": row.strength_unit,
                "is_active_ingredient": row.is_active_ingredient,
            }
            for row in sorted(details.ingredients, key=lambda item: item.position)
        ],
        documents=[
            {
                "id": row.id,
                "kind": row.kind,
                "title": row.title,
                "reference": row.reference,
                "storage_key": row.storage_key,
            }
            for row in documents
        ],
        lot_on_product_master=False,
    )


def _display(amount: Decimal | None, unit: str) -> str:
    if amount is None or not unit:
        return ""
    text = format(amount.normalize(), "f")
    return f"{text} {unit}"


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None
