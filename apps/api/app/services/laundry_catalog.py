"""Laundry catalog administration. Prices are snapshotted only when an order is accepted later."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.customer import Customer
from app.models.laundry import (
    OPERATING_MODES,
    PRICE_LIST_KINDS,
    TRACKING_MODES,
    LaundryBranchCapacity,
    LaundryGarmentType,
    LaundryPriceList,
    LaundryPriceRate,
    LaundryService,
    LaundryServiceCategory,
    LaundryServiceGarment,
    LaundrySettings,
    LaundryWorkflowTemplate,
)
from app.models.store import Store
from app.services import audit
from app.services.laundry_pricing import UNITS, LaundryPriceError, PriceQuote, quote
from app.services.tax import policy as tax_policy

TEMPLATES: dict[str, dict] = {
    "laundry_shop": {
        "modes": ["WASH_AND_FOLD", "WASH_AND_IRON", "PRESSING_ONLY"],
        "tracking": "bag",
    },
    "laundry_dry_cleaner": {
        "modes": ["DRY_CLEANING", "PRESSING_ONLY", "ALTERATIONS"],
        "tracking": "individual",
    },
    "laundry_multi_branch": {
        "modes": ["WASH_AND_FOLD", "DRY_CLEANING", "PICKUP_AND_DELIVERY", "CENTRAL_PLANT"],
        "tracking": "individual",
    },
    "laundry_commercial": {
        "modes": ["COMMERCIAL_LAUNDRY", "WASH_AND_FOLD"],
        "tracking": "bulk",
    },
}

_CATEGORIES = (
    ("cleaning", "Cleaning", 10),
    ("garment_care", "Garment care", 20),
    ("special", "Special services", 30),
)
_GARMENTS = (
    ("shirt", "Shirt"),
    ("t_shirt", "T-shirt"),
    ("trousers", "Trousers"),
    ("abaya", "Abaya"),
    ("kandura", "Kandura"),
    ("bedsheet", "Bedsheet"),
    ("towel", "Towel"),
    ("other", "Other"),
)
_SERVICES = (
    ("wash_fold", "Wash and fold", "cleaning", "KG", "WASH_FOLD"),
    ("dry_clean_shirt", "Dry clean shirt", "cleaning", "PIECE", "DRY_CLEAN"),
    ("press_shirt", "Press shirt", "cleaning", "PIECE", "PRESS"),
)
_WORKFLOWS = {
    "WASH_FOLD": [
        "RECEIVED",
        "TAGGED",
        "SORTING",
        "WASHING",
        "DRYING",
        "FOLDING",
        "QUALITY_CHECK",
        "PACKING",
        "READY_FOR_COLLECTION",
    ],
    "DRY_CLEAN": [
        "RECEIVED",
        "TAGGED",
        "SORTING",
        "PRE_TREATMENT",
        "DRY_CLEANING",
        "FINISHING",
        "QUALITY_CHECK",
        "PACKING",
        "READY_FOR_COLLECTION",
    ],
    "PRESS": ["RECEIVED", "TAGGED", "IRONING", "QUALITY_CHECK", "PACKING", "READY_FOR_COLLECTION"],
    "WASH_IRON": [
        "RECEIVED",
        "TAGGED",
        "SORTING",
        "WASHING",
        "DRYING",
        "IRONING",
        "QUALITY_CHECK",
        "PACKING",
        "READY_FOR_COLLECTION",
    ],
}


def workflow_stages(code: str) -> list[str]:
    """The built-in stage list. A saved template replaces it for that tenant."""
    return list(_WORKFLOWS.get(code, []))


def _code(value: str) -> str:
    cleaned = value.strip().lower().replace(" ", "_")
    if not cleaned or len(cleaned) > 40:
        raise ApiError(422, "invalid_code", "Enter a short code.")
    return cleaned


def settings_row(db: Session) -> LaundrySettings:
    row = db.scalar(select(LaundrySettings))
    if row is None:
        row = LaundrySettings(operating_modes=[], tracking_mode="individual", weight_precision=3)
        db.add(row)
        db.flush()
    return row


def update_settings(
    db: Session,
    *,
    modes: list[str],
    tracking_mode: str,
    weight_precision: int,
    express_daily_capacity: int | None,
    actor,
) -> LaundrySettings:
    unknown = [mode for mode in modes if mode not in OPERATING_MODES]
    if unknown or tracking_mode not in TRACKING_MODES or weight_precision < 0 or weight_precision > 3:
        raise ApiError(422, "invalid_settings", "Choose supported operating modes, tracking, and weight precision.")
    if express_daily_capacity is not None and express_daily_capacity < 0:
        raise ApiError(422, "invalid_settings", "Express capacity cannot be negative.")
    row = settings_row(db)
    row.operating_modes = list(dict.fromkeys(modes))
    row.tracking_mode = tracking_mode
    row.weight_precision = weight_precision
    row.express_daily_capacity = express_daily_capacity
    audit.record(
        db,
        action_type="UPDATE",
        action="laundry.settings",
        target_entity="LaundrySettings",
        target_entity_id=row.id,
        user=actor,
    )
    db.commit()
    return row


def create_category(db: Session, *, code: str, name: str, actor) -> LaundryServiceCategory:
    row = LaundryServiceCategory(code=_code(code), name=name.strip(), is_active=True)
    if not row.name:
        raise ApiError(422, "invalid_name", "Enter a category name.")
    db.add(row)
    db.flush()
    audit.record(
        db,
        action_type="CREATE",
        action="laundry.category",
        target_entity="LaundryServiceCategory",
        target_entity_id=row.id,
        user=actor,
    )
    db.commit()
    return row


def create_garment(db: Session, *, code: str, name: str, actor) -> LaundryGarmentType:
    row = LaundryGarmentType(code=_code(code), name=name.strip(), is_active=True)
    if not row.name:
        raise ApiError(422, "invalid_name", "Enter a garment name.")
    db.add(row)
    db.flush()
    audit.record(
        db,
        action_type="CREATE",
        action="laundry.garment",
        target_entity="LaundryGarmentType",
        target_entity_id=row.id,
        user=actor,
    )
    db.commit()
    return row


def create_service(db: Session, payload: dict, actor) -> LaundryService:
    if payload["pricing_unit"] not in UNITS:
        raise ApiError(422, "invalid_unit", "This pricing unit is not supported.")
    category = db.get(LaundryServiceCategory, payload["category_id"])
    if category is None or not category.is_active:
        raise ApiError(422, "invalid_category", "Choose an active service category.")
    row = LaundryService(
        category_id=category.id,
        code=_code(payload["code"]),
        name=payload["name"].strip(),
        pricing_unit=payload["pricing_unit"],
        base_rate_cents=payload["base_rate_cents"],
        min_charge_cents=payload["min_charge_cents"],
        min_quantity=payload["min_quantity"],
        weight_precision=payload["weight_precision"],
        express_surcharge_cents=payload.get("express_surcharge_cents"),
        same_day_surcharge_cents=payload.get("same_day_surcharge_cents"),
        special_surcharge_cents=payload.get("special_surcharge_cents"),
        tax_category=payload["tax_category"],
        price_includes_tax=payload["price_includes_tax"],
        allow_zero_rate=payload["allow_zero_rate"],
        turnaround_minutes=payload["turnaround_minutes"],
        workflow_code=payload.get("workflow_code") or "",
        is_active=True,
    )
    if not row.name:
        raise ApiError(422, "invalid_name", "Enter a service name.")
    db.add(row)
    db.flush()
    for garment_id in payload.get("garment_type_ids") or []:
        garment = db.get(LaundryGarmentType, garment_id)
        if garment is None:
            raise ApiError(422, "invalid_garment", "One of the garment types is not in this business.")
        db.add(LaundryServiceGarment(service_id=row.id, garment_type_id=garment.id))
    audit.record(
        db,
        action_type="CREATE",
        action="laundry.service",
        target_entity="LaundryService",
        target_entity_id=row.id,
        user=actor,
    )
    db.commit()
    return row


def update_service(db: Session, service_id: uuid.UUID, changes: dict, actor) -> LaundryService:
    row = db.get(LaundryService, service_id)
    if row is None:
        raise ApiError(404, "not_found", "This service is not in the catalog.")
    if "name" in changes:
        row.name = str(changes["name"]).strip()
        if not row.name:
            raise ApiError(422, "invalid_name", "Enter a service name.")
    if "base_rate_cents" in changes:
        if changes["base_rate_cents"] < 0:
            raise ApiError(422, "invalid_rate", "The unit rate cannot be negative.")
        row.base_rate_cents = changes["base_rate_cents"]
    if "min_charge_cents" in changes:
        if changes["min_charge_cents"] < 0:
            raise ApiError(422, "invalid_amount", "The minimum charge cannot be negative.")
        row.min_charge_cents = changes["min_charge_cents"]
    if "min_quantity" in changes:
        if changes["min_quantity"] < 0:
            raise ApiError(422, "invalid_quantity", "The minimum quantity cannot be negative.")
        row.min_quantity = changes["min_quantity"]
    if "weight_precision" in changes:
        if changes["weight_precision"] < 0 or changes["weight_precision"] > 3:
            raise ApiError(422, "invalid_precision", "Weight precision must be from 0 to 3.")
        row.weight_precision = changes["weight_precision"]
    if "express_surcharge_cents" in changes:
        surcharge = changes["express_surcharge_cents"]
        if surcharge is not None and surcharge < 0:
            raise ApiError(422, "invalid_amount", "The express surcharge cannot be negative.")
        row.express_surcharge_cents = surcharge
    if "is_active" in changes:
        row.is_active = bool(changes["is_active"])
    if "allow_zero_rate" in changes:
        row.allow_zero_rate = bool(changes["allow_zero_rate"])
    audit.record(
        db,
        action_type="UPDATE",
        action="laundry.service",
        target_entity="LaundryService",
        target_entity_id=row.id,
        user=actor,
        details={key: changes[key] for key in changes},
    )
    db.commit()
    return row


def create_price_list(db: Session, payload: dict, actor) -> LaundryPriceList:
    if payload["kind"] not in PRICE_LIST_KINDS:
        raise ApiError(422, "invalid_price_list", "Choose a supported price list.")
    if payload["kind"] == "branch":
        if payload.get("store_id") is None or db.get(Store, payload["store_id"]) is None:
            raise ApiError(422, "invalid_branch", "A branch price list must name a branch in this business.")
    elif payload.get("store_id") is not None:
        raise ApiError(422, "invalid_branch", "Only a branch price list names a branch.")
    if payload["kind"] in {"customer", "corporate"}:
        if payload.get("customer_id") is None or db.get(Customer, payload["customer_id"]) is None:
            raise ApiError(422, "invalid_customer", "This price list must belong to a customer in this business.")
    elif payload.get("customer_id") is not None:
        raise ApiError(422, "invalid_customer", "Only a customer or corporate price list names a customer.")
    row = LaundryPriceList(
        code=_code(payload["code"]),
        name=payload["name"].strip(),
        kind=payload["kind"],
        store_id=payload.get("store_id"),
        customer_id=payload.get("customer_id"),
        valid_from=payload.get("valid_from"),
        valid_to=payload.get("valid_to"),
        is_active=True,
    )
    if not row.name:
        raise ApiError(422, "invalid_name", "Enter a price list name.")
    db.add(row)
    db.flush()
    audit.record(
        db,
        action_type="CREATE",
        action="laundry.price_list",
        target_entity="LaundryPriceList",
        target_entity_id=row.id,
        user=actor,
    )
    db.commit()
    return row


def set_rate(
    db: Session, price_list_id: uuid.UUID, service_id: uuid.UUID, unit_price_cents: int, actor
) -> LaundryPriceRate:
    if unit_price_cents < 0:
        raise ApiError(422, "invalid_rate", "The unit rate cannot be negative.")
    price_list = db.get(LaundryPriceList, price_list_id)
    service = db.get(LaundryService, service_id)
    if price_list is None or service is None:
        raise ApiError(404, "not_found", "The price list or service is not in this business.")
    row = db.scalar(
        select(LaundryPriceRate).where(
            LaundryPriceRate.price_list_id == price_list.id,
            LaundryPriceRate.service_id == service.id,
        )
    )
    if row is None:
        row = LaundryPriceRate(price_list_id=price_list.id, service_id=service.id, unit_price_cents=unit_price_cents)
        db.add(row)
    else:
        row.unit_price_cents = unit_price_cents
    db.flush()
    audit.record(
        db,
        action_type="UPDATE",
        action="laundry.price",
        target_entity="LaundryPriceRate",
        target_entity_id=row.id,
        user=actor,
        details={"unit_price_cents": unit_price_cents},
    )
    db.commit()
    return row


def set_branch_capacity(
    db: Session, store_id: uuid.UUID, express_daily_capacity: int | None, actor
) -> LaundryBranchCapacity:
    if db.get(Store, store_id) is None:
        raise ApiError(422, "invalid_branch", "Choose a branch in this business.")
    if express_daily_capacity is not None and express_daily_capacity < 0:
        raise ApiError(422, "invalid_settings", "Express capacity cannot be negative.")
    row = db.scalar(select(LaundryBranchCapacity).where(LaundryBranchCapacity.store_id == store_id))
    if row is None:
        row = LaundryBranchCapacity(store_id=store_id, express_daily_capacity=express_daily_capacity)
        db.add(row)
    else:
        row.express_daily_capacity = express_daily_capacity
    db.flush()
    audit.record(
        db,
        action_type="UPDATE",
        action="laundry.branch_capacity",
        target_entity="LaundryBranchCapacity",
        target_entity_id=row.id,
        user=actor,
        details={"store_id": str(store_id), "express_daily_capacity": express_daily_capacity},
    )
    db.commit()
    return row


def _express_closed(db: Session, settings: LaundrySettings, store_id: uuid.UUID | None) -> bool:
    """Zero capacity refuses express. A branch row replaces the tenant setting for that branch."""
    if store_id is not None:
        branch = db.scalar(select(LaundryBranchCapacity).where(LaundryBranchCapacity.store_id == store_id))
        if branch is not None:
            return branch.express_daily_capacity == 0
    return settings.express_daily_capacity == 0


def _price_list_open(
    row: LaundryPriceList, on: date, *, store_id: uuid.UUID | None, customer_id: uuid.UUID | None
) -> bool:
    if not row.is_active:
        return False
    if row.valid_from is not None and on < row.valid_from:
        return False
    if row.valid_to is not None and on > row.valid_to:
        return False
    if row.kind == "branch" and row.store_id != store_id:
        return False
    if row.kind in {"customer", "corporate"} and row.customer_id != customer_id:
        return False
    return True


def quote_service(
    db: Session,
    service_id: uuid.UUID,
    *,
    quantity: int,
    on: date,
    store_id: uuid.UUID | None,
    customer_id: uuid.UUID | None,
    price_list_id: uuid.UUID | None,
    extras_cents: int,
    express: bool,
    same_day: bool,
    special: bool,
    discount_cents: int,
    discount_authorized: bool,
) -> tuple[PriceQuote, uuid.UUID | None]:
    service = db.get(LaundryService, service_id)
    if service is None or not service.is_active:
        raise ApiError(404, "not_found", "This service is not available.")
    settings = settings_row(db)
    if express and _express_closed(db, settings, store_id):
        raise ApiError(422, "express_capacity", "Express service has no remaining capacity.")
    unit_price = service.base_rate_cents
    used_list: uuid.UUID | None = None
    if price_list_id is not None:
        chosen = db.get(LaundryPriceList, price_list_id)
        if chosen is None or not _price_list_open(chosen, on, store_id=store_id, customer_id=customer_id):
            raise ApiError(
                422, "expired_price_list", "That price list cannot be used for this branch, customer, or date."
            )
        rate = db.scalar(
            select(LaundryPriceRate).where(
                LaundryPriceRate.price_list_id == chosen.id,
                LaundryPriceRate.service_id == service.id,
            )
        )
        if rate is None:
            raise ApiError(422, "missing_rate", "This price list does not price that service.")
        unit_price = rate.unit_price_cents
        used_list = chosen.id
    policy = tax_policy(db, store_id)
    rate_bps = policy.rate_for(service.tax_category)
    try:
        priced = quote(
            unit=service.pricing_unit,
            quantity=quantity,
            precision=service.weight_precision,
            unit_price_cents=unit_price,
            min_charge_cents=service.min_charge_cents,
            min_quantity=service.min_quantity,
            extras_cents=extras_cents,
            express=express,
            express_surcharge_cents=service.express_surcharge_cents,
            same_day=same_day,
            same_day_surcharge_cents=service.same_day_surcharge_cents,
            special=special,
            special_surcharge_cents=service.special_surcharge_cents,
            discount_cents=discount_cents,
            discount_authorized=discount_authorized,
            allow_zero_rate=service.allow_zero_rate,
            tax_category=service.tax_category,
            rate_bps=rate_bps,
            price_includes_tax=service.price_includes_tax,
        )
    except LaundryPriceError as exc:
        raise ApiError(422, exc.code, exc.message) from exc
    return priced, used_list


def apply_template(db: Session, code: str, actor) -> dict:
    spec = TEMPLATES.get(code)
    if spec is None:
        raise ApiError(422, "unknown_template", "Choose a laundry configuration template.")
    row = settings_row(db)
    row.operating_modes = spec["modes"]
    row.tracking_mode = spec["tracking"]
    categories = {}
    for item_code, name, order in _CATEGORIES:
        found = db.scalar(select(LaundryServiceCategory).where(LaundryServiceCategory.code == item_code))
        if found is None:
            found = LaundryServiceCategory(code=item_code, name=name, display_order=order, is_active=True)
            db.add(found)
            db.flush()
        categories[item_code] = found
    for item_code, name in _GARMENTS:
        if db.scalar(select(LaundryGarmentType.id).where(LaundryGarmentType.code == item_code)) is None:
            db.add(LaundryGarmentType(code=item_code, name=name, is_active=True))
    for item_code, stages in _WORKFLOWS.items():
        if db.scalar(select(LaundryWorkflowTemplate.id).where(LaundryWorkflowTemplate.code == item_code)) is None:
            db.add(
                LaundryWorkflowTemplate(
                    code=item_code, name=item_code.replace("_", " ").title(), stages=stages, is_active=True
                )
            )
    db.flush()
    for item_code, name, category_code, unit, workflow in _SERVICES:
        if db.scalar(select(LaundryService.id).where(LaundryService.code == item_code)) is None:
            db.add(
                LaundryService(
                    category_id=categories[category_code].id,
                    code=item_code,
                    name=name,
                    pricing_unit=unit,
                    base_rate_cents=0,
                    allow_zero_rate=True,
                    workflow_code=workflow,
                    weight_precision=3 if unit == "KG" else 0,
                    is_active=True,
                )
            )
    audit.record(
        db,
        action_type="UPDATE",
        action="laundry.template",
        target_entity="LaundrySettings",
        target_entity_id=row.id,
        user=actor,
        details={"template": code},
    )
    db.commit()
    return {"template": code, "operating_modes": row.operating_modes, "tracking_mode": row.tracking_mode}
