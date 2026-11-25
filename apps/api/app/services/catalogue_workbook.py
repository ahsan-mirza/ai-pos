"""Import and export the product catalogue as one .xlsx workbook.

Stock quantities, stock movements, recipes, and sales are never written here.
A workbook is validated in full before the first catalogue change is committed.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.capabilities import FOOD_AND_BEVERAGE
from app.core.deps import Principal
from app.core.errors import ApiError
from app.models.audit_log import AuditLog
from app.models.brand import Brand
from app.models.category import Category, SubCategory
from app.models.inventory import InventoryLevel
from app.models.menu import MenuPriceOption, ModifierGroup, ModifierOption, ProductModifierGroup
from app.models.product import Product
from app.schemas.catalogue import FashionAttributes
from app.services import catalogue_xlsx as xlsx
from app.services import category_service, fashion_attributes, uom_service
from app.services.audit import log_export, record
from app.services.item_type import apply_item_type
from app.services.recipe_mode import apply_sell_without_recipe, enforce_recipe_requirement, has_recipe
from app.services.settings_service import business_currency, load_settings
from app.services.sku_policy import MENU_PROFILES, stored_sku
from app.tenancy.context import current_tenant

MODES = frozenset({"create_only", "update_only", "upsert"})
TAX = frozenset({"STANDARD", "ZERO", "EXEMPT"})
ITEM_TYPES = frozenset({"MADE_TO_ORDER", "RAW_INGREDIENT", "PRE_PACKAGED"})
_YES = frozenset({"yes", "true", "1", "y"})
_NO = frozenset({"no", "false", "0", "n"})


@dataclass
class Issue:
    sheet: str
    row: int
    field: str
    message: str

    def dump(self) -> dict[str, object]:
        return {"sheet": self.sheet, "row": self.row, "field": self.field, "message": self.message}


@dataclass
class ProductPlan:
    action: str
    sheet: str
    row: int
    product_id: uuid.UUID
    existing: Product | None
    values: dict[str, object]
    fields: set[str]


@dataclass
class OptionPlan:
    action: str
    row: int
    product_id: uuid.UUID
    option_id: uuid.UUID
    existing: MenuPriceOption | None
    name: str
    price_cents: int
    sku: str | None
    is_active: bool
    position: int


@dataclass
class GroupPlan:
    action: str
    group_id: uuid.UUID
    existing: ModifierGroup | None
    name: str
    min_select: int
    max_select: int
    is_active: bool
    options: list[dict[str, object]] = field(default_factory=list)
    product_ids: list[uuid.UUID] = field(default_factory=list)


@dataclass
class Plan:
    job_id: str
    mode: str
    profile: str
    currency: str
    products: list[ProductPlan] = field(default_factory=list)
    options: list[OptionPlan] = field(default_factory=list)
    groups: list[GroupPlan] = field(default_factory=list)
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    product_rows: int = 0
    menu_rows: int = 0
    pricing_rows: int = 0
    modifier_rows: int = 0

    def report(self, *, committed: bool, replayed: bool = False) -> dict[str, object]:
        created = sum(1 for item in self.products if item.action == "create")
        updated = sum(1 for item in self.products if item.action == "update")
        unchanged = sum(1 for item in self.products if item.action == "unchanged")
        return {
            "job_id": self.job_id,
            "workbook_version": xlsx.FORMAT_VERSION,
            "mode": self.mode,
            "product_rows": self.product_rows,
            "menu_rows": self.menu_rows,
            "pricing_rows": self.pricing_rows,
            "modifier_rows": self.modifier_rows,
            "created": created,
            "updated": updated,
            "unchanged": unchanged,
            "pricing_created": sum(1 for item in self.options if item.action == "create"),
            "pricing_updated": sum(1 for item in self.options if item.action == "update"),
            "modifier_changes": sum(1 for item in self.groups if item.action != "unchanged"),
            "failed": len(self.errors),
            "committed": committed,
            "replayed": replayed,
            "errors": [item.dump() for item in self.errors],
            "warnings": [item.dump() for item in self.warnings],
        }


def _guide() -> list[list[object]]:
    lines = [
        ("Workbook version", "Workbook", "Version 1. An exported file uses the same sheets and column names."),
        ("Product ID", "Products / Menu Items", "Blank creates a product. An exported id updates that product."),
        ("SKU", "Products / Menu Items", "Required except Restaurant and Cafe. It is not a portion id."),
        ("Barcode", "Products / Menu Items", "Required for a new product. Import does not change an existing barcode."),
        ("Product Type", "Products", "MADE_TO_ORDER, RAW_INGREDIENT, or PRE_PACKAGED."),
        ("Category", "Products / Menu Items", "Must already exist for this store. Import does not create categories."),
        ("Brand", "Products", "Must already exist when filled. Import does not create brands."),
        ("Base Price", "Products / Menu Items", "Store-currency price such as 3.00, with at most 2 decimal places."),
        ("Cost Price", "Products", "Shown for reference. Import does not change cost or stock."),
        ("Prepared Without Recipe", "Menu Items", "Yes sells the item without a recipe. Recipes are not created."),
        ("Option ID", "Menu Pricing Options", "Leave blank to add a portion. An exported id updates that portion."),
        ("Product ID", "Menu Pricing Options", "Parent product id, or a unique new item name from this file."),
        ("Modifiers", "Modifiers", "Updates groups that already match by id or name, and links them to the product."),
        ("Stock", "Workbook", "Inventory balances, movements, recipes, and sales are not part of this workbook."),
    ]
    return [["Column", "Sheet", "Meaning"], *([list(line) for line in lines])]


def _meta_rows(profile: str, scope: str) -> list[list[object]]:
    tenant = current_tenant()
    return [
        ["Key", "Value"],
        ["format_version", xlsx.FORMAT_VERSION],
        ["template_version", xlsx.FORMAT_VERSION],
        ["exported_at", datetime.now(UTC).replace(microsecond=0).isoformat()],
        ["tenant", tenant.slug if tenant is not None else "local"],
        ["business_profile", profile],
        ["export_scope", scope],
    ]


def _empty_data(columns: tuple[str, ...]) -> list[list[object]]:
    return [list(columns)]


def template_bytes() -> bytes:
    sheets = [
        (xlsx.SHEET_GUIDE, _guide()),
        (xlsx.SHEET_PRODUCTS, _empty_data(xlsx.PRODUCT_COLUMNS)),
        (xlsx.SHEET_MENU, _empty_data(xlsx.MENU_COLUMNS)),
        (xlsx.SHEET_OPTIONS, _empty_data(xlsx.OPTION_COLUMNS)),
        (xlsx.SHEET_MODIFIERS, _empty_data(xlsx.MODIFIER_COLUMNS)),
        (xlsx.SHEET_META, _meta_rows("", "template")),
    ]
    return xlsx.write_workbook(sheets, hidden={xlsx.SHEET_META})


def _fashion(profile: str) -> bool:
    return "fashion" in profile


def _product_row(product: Product, *, cost: bool) -> list[object]:
    units = product.sellable_units or ["PIECE"]
    unit = next((code for code in units if code != "PIECE"), units[0] if units else "PIECE")
    sub = product.sub_category_ref.name if product.sub_category_ref is not None else ""
    return [
        str(product.id),
        product.name,
        product.sku or "",
        product.barcode,
        product.item_type,
        product.category,
        sub,
        product.brand or "",
        unit,
        xlsx.money(product.price_cents),
        xlsx.money(product.default_cost_cents) if cost else "",
        product.currency,
        product.tax_category,
        xlsx.yes_no(product.price_includes_tax),
        xlsx.yes_no(product.is_active),
        product.model_number or "",
        xlsx.yes_no(product.is_open_price),
        xlsx.yes_no(product.sold_by_weight),
        product.plu_code or "",
        product.tare_grams if product.sold_by_weight else "",
        product.minimum_age if product.minimum_age is not None else "",
        xlsx.yes_no(product.is_ingredient),
        xlsx.yes_no(product.is_serialized),
        product.season or "",
        product.collection or "",
        product.gender or "",
        product.material or "",
        product.fit or "",
        product.care or "",
    ]


def _menu_row(product: Product) -> list[object]:
    sub = product.sub_category_ref.name if product.sub_category_ref is not None else ""
    return [
        str(product.id),
        product.name,
        product.sku or "",
        product.barcode,
        product.category,
        sub,
        xlsx.money(product.price_cents),
        product.currency,
        product.tax_category,
        xlsx.yes_no(product.price_includes_tax),
        xlsx.yes_no(product.sell_without_recipe),
        xlsx.yes_no(product.is_active),
        xlsx.yes_no(product.is_open_price),
    ]


def export_workbook(
    db: Session,
    principal: Principal,
    *,
    query: str | None = None,
    ids: set[uuid.UUID] | None = None,
) -> tuple[bytes, str, int]:
    settings = load_settings(db)
    profile = settings.business_profile
    food = profile in FOOD_AND_BEVERAGE
    needle = (query or "").strip().casefold()
    products = list(db.scalars(select(Product).order_by(Product.name, Product.id)))
    chosen: list[Product] = []
    for product in products:
        if ids is not None and product.id not in ids:
            continue
        if needle:
            haystack = " ".join([product.name, product.sku or "", product.barcode, product.category]).casefold()
            if needle not in haystack:
                continue
        chosen.append(product)
    product_rows: list[list[object]] = [list(xlsx.PRODUCT_COLUMNS)]
    menu_rows: list[list[object]] = [list(xlsx.MENU_COLUMNS)]
    chosen_ids = {product.id for product in chosen}
    for product in chosen:
        if food and product.item_type == "MADE_TO_ORDER":
            menu_rows.append(_menu_row(product))
        else:
            product_rows.append(_product_row(product, cost=True))
    option_rows: list[list[object]] = [list(xlsx.OPTION_COLUMNS)]
    if chosen_ids:
        options = db.scalars(
            select(MenuPriceOption)
            .where(MenuPriceOption.product_id.in_(chosen_ids))
            .order_by(MenuPriceOption.product_id, MenuPriceOption.position, MenuPriceOption.name)
        ).all()
    else:
        options = []
    names = {product.id: product.name for product in chosen}
    for option in options:
        option_rows.append(
            [
                str(option.id),
                str(option.product_id),
                names.get(option.product_id, ""),
                option.name,
                xlsx.money(option.price_cents),
                next((product.currency for product in chosen if product.id == option.product_id), ""),
                option.sku or "",
                xlsx.yes_no(option.is_active),
                option.position,
            ]
        )
    modifier_rows: list[list[object]] = [list(xlsx.MODIFIER_COLUMNS)]
    if chosen_ids and food:
        links = db.scalars(
            select(ProductModifierGroup)
            .where(ProductModifierGroup.product_id.in_(chosen_ids))
            .order_by(ProductModifierGroup.product_id, ProductModifierGroup.position)
        ).all()
        groups = {group.id: group for group in db.scalars(select(ModifierGroup)).all()}
        for link in links:
            group = groups.get(link.group_id)
            if group is None:
                continue
            for option in group.options:
                modifier_rows.append(
                    [
                        str(link.product_id),
                        names.get(link.product_id, ""),
                        str(group.id),
                        group.name,
                        group.min_select,
                        group.max_select,
                        xlsx.yes_no(group.is_active),
                        str(option.id),
                        option.name,
                        xlsx.money(option.price_delta_cents),
                        xlsx.yes_no(option.is_default),
                        xlsx.yes_no(option.is_active),
                    ]
                )
    scope = "filtered" if needle or ids else "all"
    sheets = [
        (xlsx.SHEET_GUIDE, _guide()),
        (xlsx.SHEET_PRODUCTS, product_rows),
        (xlsx.SHEET_MENU, menu_rows),
        (xlsx.SHEET_OPTIONS, option_rows),
        (xlsx.SHEET_MODIFIERS, modifier_rows),
        (xlsx.SHEET_META, _meta_rows(profile, scope)),
    ]
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    filename = f"AxizPOS_Product_Menu_{profile}_{stamp}.xlsx"
    payload = xlsx.write_workbook(sheets, hidden={xlsx.SHEET_META})
    log_export(
        db,
        dataset="catalogue",
        row_count=len(chosen),
        filters={"q": needle, "ids": len(ids or ()), "store_id": str(principal.store_id or "")},
        file_format="xlsx",
    )
    db.commit()
    return payload, filename, len(chosen)


def _job_id(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:32]


def _event_id(key: str) -> uuid.UUID:
    try:
        return uuid.UUID(key)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, f"axizpos-catalogue-import:{key}")


def _header_map(sheet: str, rows: list[list[str]], expected: tuple[str, ...],
    issues: list[Issue]) -> dict[str, int] | None:
    if not rows:
        return None
    header = rows[0]
    if tuple(header[: len(expected)]) != expected or any(cell for cell in header[len(expected) :]):
        issues.append(Issue(sheet, 1, "Header", "The columns do not match this workbook version."))
        return None
    return {name: index for index, name in enumerate(expected)}


def _value(row: list[str], columns: dict[str, int], name: str) -> str:
    index = columns.get(name)
    if index is None or index >= len(row):
        return ""
    return row[index].strip()


def _kept(existing: Product | None, parsed: bool | None, name: str) -> bool:
    if parsed is None and existing is not None:
        return bool(getattr(existing, name))
    return bool(parsed)


def _bool(sheet: str, row_number: int, label: str, text: str, issues: list[Issue], *, required: bool) -> bool | None:
    if text == "":
        if required:
            issues.append(Issue(sheet, row_number, label, f"{label} is required. Use Yes or No."))
        return None
    lowered = text.casefold()
    if lowered in _YES:
        return True
    if lowered in _NO:
        return False
    issues.append(Issue(sheet, row_number, label, f"{label} must be Yes or No."))
    return None


def _money(
    sheet: str,
    row_number: int,
    label: str,
    text: str,
    issues: list[Issue],
    *,
    required: bool,
    allow_negative: bool = False,
) -> int | None:
    if text == "":
        if required:
            issues.append(Issue(sheet, row_number, label, f"{label} is required."))
        return None
    try:
        amount = Decimal(text.replace(",", ""))
    except InvalidOperation:
        issues.append(Issue(sheet, row_number, label, f"{label} must be a number, such as 3.00."))
        return None
    if not allow_negative and amount < 0:
        issues.append(Issue(sheet, row_number, label, f"{label} cannot be negative."))
        return None
    cents = (amount * 100).quantize(Decimal("1"))
    if amount * 100 != cents:
        issues.append(Issue(sheet, row_number, label, f"{label} uses at most 2 decimal places."))
        return None
    if abs(int(cents)) > 100_000_000:
        issues.append(Issue(sheet, row_number, label, f"{label} is too large."))
        return None
    return int(cents)


def _int_field(
    sheet: str, row_number: int, label: str, text: str, issues: list[Issue], *, minimum: int, maximum: int
) -> int | None:
    if text == "":
        issues.append(Issue(sheet, row_number, label, f"{label} is required."))
        return None
    try:
        value = int(text)
    except ValueError:
        issues.append(Issue(sheet, row_number, label, f"{label} must be a whole number."))
        return None
    if value < minimum or value > maximum:
        issues.append(Issue(sheet, row_number, label, f"{label} is outside the allowed range."))
        return None
    return value


def _data_rows(rows: list[list[str]], width: int) -> list[tuple[int, list[str]]]:
    found = []
    for offset, row in enumerate(rows[1:], start=2):
        padded = row + [""] * width
        if any(cell.strip() for cell in padded[:width]):
            found.append((offset, padded))
    return found


def _metadata(sheets: dict[str, list[list[str]]]) -> dict[str, str]:
    rows = sheets.get(xlsx.SHEET_META) or []
    found: dict[str, str] = {}
    for row in rows:
        if not row or not row[0] or row[0] == "Key":
            continue
        found[row[0]] = row[1].strip() if len(row) > 1 else ""
    version = found.get("format_version", "")
    if version != xlsx.FORMAT_VERSION:
        shown = version or "missing"
        raise ApiError(
            422,
            "unsupported_workbook",
            f"This workbook version ({shown}) is not supported. Download the current template.",
        )
    return found


def _category(db: Session, name: str) -> Category | None:
    return db.scalar(select(Category).where(func.lower(Category.name) == name.casefold()))


def _brand(db: Session, name: str) -> Brand | None:
    return db.scalar(select(Brand).where(func.lower(Brand.name) == name.casefold()))


def _refs_ok(
    db: Session,
    plan: Plan,
    sheet: str,
    row_number: int,
    existing: Product | None,
    values: dict[str, object],
    *,
    menu: bool,
) -> bool:
    category_name = str(values.get("category") or "")
    sub_name = str(values.get("sub_category") or "")
    current_sub = ""
    if existing is not None and existing.sub_category_ref is not None:
        current_sub = existing.sub_category_ref.name
    same_category = existing is not None and category_name in {"", existing.category} and sub_name == current_sub
    if category_name and not same_category:
        category = _category(db, category_name)
        if category is None:
            plan.errors.append(Issue(sheet, row_number, "Category", "Category does not exist for this store."))
            return False
        if sub_name and _sub(db, category, sub_name) is None:
            plan.errors.append(Issue(sheet, row_number, "Sub-category",
                "Sub-category does not belong to that category."))
            return False
    if not menu:
        brand_name = str(values.get("brand") or "")
        if brand_name and _brand(db, brand_name) is None:
            plan.errors.append(Issue(sheet, row_number, "Brand", "Brand does not exist."))
            return False
        unit = str(values.get("unit") or "PIECE")
        try:
            uom_service.check_sellable(
                db,
                [unit],
                serialized=bool(values.get("is_serialized")),
                weighed=bool(values.get("sold_by_weight")),
            )
        except ApiError as exc:
            plan.errors.append(Issue(sheet, row_number, "Unit", exc.message))
            return False
    return True


def _sub(db: Session, category: Category, name: str) -> SubCategory | None:
    return db.scalar(
        select(SubCategory).where(
            SubCategory.category_id == category.id,
            func.lower(SubCategory.name) == name.casefold(),
        )
    )


def build_plan(db: Session, data: bytes, file_name: str, mode: str) -> Plan:
    if mode not in MODES:
        raise ApiError(422, "invalid_mode", "Choose create only, update only, or create and update.")
    sheets = xlsx.read_workbook(data, file_name)
    meta = _metadata(sheets)
    settings = load_settings(db)
    profile = settings.business_profile
    currency = business_currency(db)
    plan = Plan(job_id=_job_id(data), mode=mode, profile=profile, currency=currency)
    file_profile = meta.get("business_profile", "")
    if file_profile and file_profile != profile:
        raise ApiError(422, "wrong_profile", "This workbook was exported for a different business type.")
    tenant = current_tenant()
    file_tenant = meta.get("tenant", "")
    current = tenant.slug if tenant is not None else "local"
    if file_tenant and file_tenant not in {current, "local"}:
        raise ApiError(422, "wrong_tenant", "This workbook was exported for a different store.")
    known = {
        xlsx.SHEET_GUIDE,
        xlsx.SHEET_PRODUCTS,
        xlsx.SHEET_MENU,
        xlsx.SHEET_OPTIONS,
        xlsx.SHEET_MODIFIERS,
        xlsx.SHEET_META,
    }
    for name in sheets:
        if name not in known:
            plan.warnings.append(Issue(name, 1, "Sheet",
                "This sheet is not part of the catalogue workbook, so it was ignored."))
    products = list(db.scalars(select(Product)))
    by_id = {product.id: product for product in products}
    by_sku = {product.sku.casefold(): product for product in products if product.sku}
    by_barcode = {product.barcode: product for product in products}
    seen_sku: set[str] = set()
    seen_barcode: set[str] = set()
    seen_id: set[uuid.UUID] = set()
    names: dict[str, list[uuid.UUID]] = {}

    def note_name(name: str, product_id: uuid.UUID) -> None:
        bucket = names.setdefault(name.casefold(), [])
        if product_id not in bucket:
            bucket.append(product_id)

    def take_identity(sheet: str, row_number: int, raw_id: str, sku: str, barcode: str) -> Product | None:
        if raw_id:
            try:
                product_id = uuid.UUID(raw_id)
            except ValueError:
                plan.errors.append(Issue(sheet, row_number, "Product ID", "Product ID is not a valid id."))
                return None
            product = by_id.get(product_id)
            if product is None:
                plan.errors.append(Issue(sheet, row_number, "Product ID", "No product has this id."))
                return None
            return product
        if sku and sku.casefold() in by_sku:
            return by_sku[sku.casefold()]
        if barcode and barcode in by_barcode:
            return by_barcode[barcode]
        return None

    def add_product(sheet: str, row_number: int, columns: dict[str, int], row: list[str], *, menu: bool) -> None:
        label = "Menu Item Name" if menu else "Product Name"
        name = _value(row, columns, label)
        if not name:
            plan.errors.append(Issue(sheet, row_number, label, "A name is required."))
            return
        if len(name) > 200:
            plan.errors.append(Issue(sheet, row_number, label, "Name is too long."))
            return
        raw_id = _value(row, columns, "Product ID")
        sku = _value(row, columns, "SKU")
        barcode = _value(row, columns, "Barcode")
        if sku and sku.casefold() in seen_sku:
            plan.errors.append(Issue(sheet, row_number, "SKU", "This SKU is already used on another row."))
            return
        if barcode and barcode in seen_barcode:
            plan.errors.append(Issue(sheet, row_number, "Barcode", "This barcode is already used on another row."))
            return
        existing = take_identity(sheet, row_number, raw_id, sku, barcode)
        if any(issue.row == row_number and issue.sheet == sheet for issue in plan.errors):
            return
        if existing is not None and existing.id in seen_id:
            plan.errors.append(Issue(sheet, row_number, "Product ID",
                "This product is already listed in the workbook."))
            return
        creating = existing is None
        if creating and mode == "update_only":
            plan.errors.append(Issue(sheet, row_number, label, "No existing product matches this row."))
            return
        if not creating and mode == "create_only":
            plan.errors.append(
                Issue(sheet, row_number, "Product ID" if raw_id else "SKU", "This row matches an existing product.")
            )
            return
        if creating and not barcode:
            plan.errors.append(Issue(sheet, row_number, "Barcode", "A new product needs a barcode."))
            return
        if not creating and barcode and barcode != existing.barcode:
            plan.errors.append(Issue(sheet, row_number, "Barcode", "Barcode cannot be changed by this import."))
            return
        if not creating and existing.sku and sku and sku != existing.sku:
            plan.errors.append(Issue(sheet, row_number, "SKU", "SKU cannot be changed by this import."))
            return
        if not creating and existing.sku and not sku:
            plan.errors.append(Issue(sheet, row_number, "SKU", "SKU cannot be cleared by this import."))
            return
        price = _money(sheet, row_number, "Base Price", _value(row, columns, "Base Price"), plan.errors, required=True)
        active = _bool(sheet, row_number, "Active", _value(row, columns, "Active"), plan.errors, required=True)
        includes_tax = _bool(
            sheet, row_number, "Price Includes Tax", _value(row, columns, "Price Includes Tax"), plan.errors,
                required=True
        )
        open_price = _bool(sheet, row_number, "Open Price", _value(row, columns, "Open Price"), plan.errors,
            required=False)
        if open_price is None and _value(row, columns, "Open Price") == "":
            open_price = False if creating else None
        tax = _value(row, columns, "Tax Category") or "STANDARD"
        if tax not in TAX:
            plan.errors.append(Issue(sheet, row_number, "Tax Category",
                "Tax category must be STANDARD, ZERO, or EXEMPT."))
            return
        row_currency = _value(row, columns, "Currency") or (existing.currency if existing is not None else currency)
        if row_currency != (existing.currency if existing is not None else currency):
            plan.errors.append(Issue(sheet, row_number, "Currency", "Currency must match the store currency."))
            return
        category_name = _value(row, columns, "Category")
        sub_name = _value(row, columns, "Sub-category")
        if creating and not category_name:
            plan.errors.append(Issue(sheet, row_number, "Category", "Category is required."))
            return
        if menu:
            item_type = "MADE_TO_ORDER"
            prepared = _bool(
                sheet,
                row_number,
                "Prepared Without Recipe",
                _value(row, columns, "Prepared Without Recipe"),
                plan.errors,
                required=True,
            )
            if prepared is None:
                return
            values: dict[str, object] = {
                "name": name,
                "sku": sku,
                "barcode": barcode or (existing.barcode if existing else ""),
                "item_type": item_type,
                "category": category_name,
                "sub_category": sub_name,
                "price_cents": price,
                "currency": row_currency,
                "tax_category": tax,
                "price_includes_tax": includes_tax,
                "is_active": active,
                "is_open_price": _kept(existing, open_price, "is_open_price"),
                "sell_without_recipe": bool(prepared),
                "sold_by_weight": False,
                "is_serialized": False,
                "is_ingredient": False,
                "unit": "PIECE",
            }
            present = set(values)
        else:
            item_type = _value(row, columns, "Product Type") or ("PRE_PACKAGED" if creating else existing.item_type)
            if item_type not in ITEM_TYPES:
                plan.errors.append(Issue(sheet, row_number, "Product Type", "Product type is not supported."))
                return
            ingredient = _bool(sheet, row_number, "Ingredient", _value(row, columns, "Ingredient"),
                plan.errors, required=False)
            serialized = _bool(sheet, row_number, "Serialized", _value(row, columns, "Serialized"),
                plan.errors, required=False)
            weighed = _bool(
                sheet, row_number, "Sold By Weight", _value(row, columns, "Sold By Weight"), plan.errors, required=False
            )
            if ingredient is True and item_type != "RAW_INGREDIENT":
                plan.errors.append(Issue(sheet, row_number, "Ingredient",
                    "An ingredient uses product type RAW_INGREDIENT."))
                return
            if not creating and serialized is not None and serialized != existing.is_serialized:
                plan.errors.append(Issue(sheet, row_number, "Serialized",
                    "Serialized cannot be changed by this import."))
                return
            values = {
                "name": name,
                "sku": sku,
                "barcode": barcode or (existing.barcode if existing else ""),
                "item_type": item_type,
                "category": category_name,
                "sub_category": sub_name,
                "brand": _value(row, columns, "Brand"),
                "unit": _value(row, columns, "Unit") or "PIECE",
                "price_cents": price,
                "currency": row_currency,
                "tax_category": tax,
                "price_includes_tax": includes_tax,
                "is_active": active,
                "model_number": _value(row, columns, "Model Number"),
                "is_open_price": _kept(existing, open_price, "is_open_price"),
                "sold_by_weight": _kept(existing, weighed, "sold_by_weight"),
                "plu_code": _value(row, columns, "PLU"),
                "tare_grams": _value(row, columns, "Tare Grams"),
                "minimum_age": _value(row, columns, "Minimum Age"),
                "is_ingredient": item_type == "RAW_INGREDIENT" if ingredient is None else ingredient,
                "is_serialized": _kept(existing, serialized, "is_serialized"),
                "sell_without_recipe": False,
                "season": _value(row, columns, "Season"),
                "collection": _value(row, columns, "Collection"),
                "gender": _value(row, columns, "Gender"),
                "material": _value(row, columns, "Material"),
                "fit": _value(row, columns, "Fit"),
                "care": _value(row, columns, "Care"),
            }
            present = set(values)
            if not _fashion(profile) and any(values[key] for key in ("season", "collection", "gender",
                "material", "fit", "care")):
                plan.errors.append(Issue(sheet, row_number, "Season",
                    "Fashion attributes are not used for this business type."))
                return
            cost = _value(row, columns, "Cost Price")
            if cost and existing is not None:
                exported = xlsx.money(existing.default_cost_cents)
                if exported and cost != exported:
                    plan.warnings.append(
                        Issue(sheet, row_number, "Cost Price", "Cost price is not changed by this import.")
                    )
        if price is None or active is None or includes_tax is None:
            return
        if not _refs_ok(db, plan, sheet, row_number, existing, values, menu=menu):
            return
        if creating and profile not in MENU_PROFILES and not sku and menu:
            plan.errors.append(Issue(sheet, row_number, "SKU", "SKU is required."))
            return
        if creating and not menu and profile not in MENU_PROFILES and not sku:
            plan.errors.append(Issue(sheet, row_number, "SKU", "SKU is required."))
            return
        product_id = existing.id if existing is not None else uuid.uuid4()
        action = "create" if creating else "update"
        if not creating and _same(existing, values, menu=menu):
            action = "unchanged"
        if sku:
            seen_sku.add(sku.casefold())
        if values["barcode"]:
            seen_barcode.add(str(values["barcode"]))
        seen_id.add(product_id)
        note_name(name, product_id)
        if existing is not None:
            note_name(existing.name, existing.id)
        plan.products.append(
            ProductPlan(action, sheet, row_number, product_id, existing, values, present)
        )

    product_columns = _header_map(xlsx.SHEET_PRODUCTS, sheets.get(xlsx.SHEET_PRODUCTS, []),
        xlsx.PRODUCT_COLUMNS, plan.errors)
    menu_columns = _header_map(xlsx.SHEET_MENU, sheets.get(xlsx.SHEET_MENU, []), xlsx.MENU_COLUMNS, plan.errors)
    if product_columns is None and xlsx.SHEET_PRODUCTS not in sheets:
        plan.errors.append(Issue(xlsx.SHEET_PRODUCTS, 1, "Sheet", "The Products sheet is missing."))
    food = profile in FOOD_AND_BEVERAGE
    if product_columns is not None:
        for row_number, row in _data_rows(sheets.get(xlsx.SHEET_PRODUCTS, []), len(xlsx.PRODUCT_COLUMNS)):
            plan.product_rows += 1
            add_product(xlsx.SHEET_PRODUCTS, row_number, product_columns, row, menu=False)
    if menu_columns is not None:
        menu_data = _data_rows(sheets.get(xlsx.SHEET_MENU, []), len(xlsx.MENU_COLUMNS))
        if menu_data and not food:
            plan.errors.append(Issue(xlsx.SHEET_MENU, 2, "Sheet",
                "Menu items are only imported for a restaurant or cafe."))
        elif food:
            for row_number, row in menu_data:
                plan.menu_rows += 1
                add_product(xlsx.SHEET_MENU, row_number, menu_columns, row, menu=True)
    _plan_options(db, plan, sheets, by_id, names, currency)
    _plan_modifiers(db, plan, sheets, by_id, names, food)
    _check_portions(plan, db)
    _check_recipes(db, plan, profile)
    return plan


def _same(product: Product, values: dict[str, object], *, menu: bool) -> bool:
    sub = product.sub_category_ref.name if product.sub_category_ref is not None else ""
    checks = {
        "name": product.name,
        "price_cents": product.price_cents,
        "tax_category": product.tax_category,
        "price_includes_tax": product.price_includes_tax,
        "is_active": product.is_active,
        "is_open_price": product.is_open_price,
        "category": product.category if values.get("category") else product.category,
        "sub_category": sub,
    }
    if not menu:
        units = product.sellable_units or ["PIECE"]
        checks["unit"] = next((code for code in units if code != "PIECE"), "PIECE")
    if menu:
        checks["sell_without_recipe"] = product.sell_without_recipe
        checks["item_type"] = product.item_type
    else:
        checks.update(
            {
                "item_type": product.item_type,
                "brand": product.brand or "",
                "model_number": product.model_number or "",
                "sold_by_weight": product.sold_by_weight,
                "is_serialized": product.is_serialized,
                "is_ingredient": product.is_ingredient,
                "season": product.season or "",
                "collection": product.collection or "",
                "gender": product.gender or "",
                "material": product.material or "",
                "fit": product.fit or "",
                "care": product.care or "",
            }
        )
    for key, current in checks.items():
        if key not in values:
            continue
        incoming = values[key]
        if key == "category" and incoming == "":
            continue
        if incoming != current:
            return False
    return True


def _plan_options(
    db: Session,
    plan: Plan,
    sheets: dict[str, list[list[str]]],
    by_id: dict[uuid.UUID, Product],
    names: dict[str, list[uuid.UUID]],
    currency: str,
) -> None:
    columns = _header_map(xlsx.SHEET_OPTIONS, sheets.get(xlsx.SHEET_OPTIONS, []), xlsx.OPTION_COLUMNS, plan.errors)
    if columns is None:
        return
    existing = list(db.scalars(select(MenuPriceOption)))
    by_option = {option.id: option for option in existing}
    by_label = {(option.product_id, option.name.casefold()): option for option in existing}
    seen: set[tuple[uuid.UUID, str]] = set()
    for row_number, row in _data_rows(sheets.get(xlsx.SHEET_OPTIONS, []), len(xlsx.OPTION_COLUMNS)):
        plan.pricing_rows += 1
        if plan.profile not in FOOD_AND_BEVERAGE:
            plan.errors.append(Issue(xlsx.SHEET_OPTIONS, row_number, "Sheet",
                "Priced portions are only used on a restaurant or cafe menu."))
            continue
        parent = _parent(
            plan,
            xlsx.SHEET_OPTIONS,
            row_number,
            _value(row, columns, "Product ID"),
            _value(row, columns, "Product Name"),
            by_id,
            names,
        )
        option_name = _value(row, columns, "Option Name")
        if parent is None or not option_name:
            if not option_name:
                plan.errors.append(Issue(xlsx.SHEET_OPTIONS, row_number, "Option Name", "A portion needs a name."))
            continue
        if (parent, option_name.casefold()) in seen:
            plan.errors.append(Issue(xlsx.SHEET_OPTIONS, row_number, "Option Name",
                "This portion is already listed for the item."))
            continue
        seen.add((parent, option_name.casefold()))
        price = _money(xlsx.SHEET_OPTIONS, row_number, "Price", _value(row, columns, "Price"), plan.errors,
            required=True)
        active = _bool(xlsx.SHEET_OPTIONS, row_number, "Active", _value(row, columns, "Active"), plan.errors,
            required=True)
        row_currency = _value(row, columns, "Currency")
        if row_currency and row_currency != currency:
            plan.errors.append(Issue(xlsx.SHEET_OPTIONS, row_number, "Currency",
                "Currency must match the store currency."))
            continue
        if price is None or active is None:
            continue
        raw_option = _value(row, columns, "Option ID")
        current = None
        if raw_option:
            try:
                option_id = uuid.UUID(raw_option)
            except ValueError:
                plan.errors.append(Issue(xlsx.SHEET_OPTIONS, row_number, "Option ID", "Option ID is not a valid id."))
                continue
            current = by_option.get(option_id)
            if current is None or current.product_id != parent:
                plan.errors.append(Issue(xlsx.SHEET_OPTIONS, row_number, "Option ID",
                    "This portion does not belong to the product."))
                continue
        else:
            current = by_label.get((parent, option_name.casefold()))
            option_id = current.id if current is not None else uuid.uuid4()
        position_text = _value(row, columns, "Position")
        position = int(position_text) if position_text.isdigit() else len(seen)
        sku = _value(row, columns, "SKU") or None
        action = "create" if current is None else "update"
        same_option = (
            current is not None
            and current.name == option_name
            and current.price_cents == price
            and current.is_active == active
            and (current.sku or None) == sku
        )
        if same_option:
            action = "unchanged"
        plan.options.append(OptionPlan(action, row_number, parent, option_id, current, option_name, price,
            sku, active, position))


def _parent(
    plan: Plan,
    sheet: str,
    row_number: int,
    raw_id: str,
    raw_name: str,
    by_id: dict[uuid.UUID, Product],
    names: dict[str, list[uuid.UUID]],
) -> uuid.UUID | None:
    if raw_id:
        try:
            product_id = uuid.UUID(raw_id)
        except ValueError:
            product_id = None
            raw_name = raw_name or raw_id
        else:
            if product_id in by_id or any(item.product_id == product_id for item in plan.products):
                return product_id
            plan.errors.append(Issue(sheet, row_number, "Product ID", "The parent product was not found."))
            return None
    label = raw_name.strip()
    if not label:
        plan.errors.append(Issue(sheet, row_number, "Product ID", "The parent product id is missing."))
        return None
    matches = names.get(label.casefold(), [])
    if len(matches) == 1:
        return matches[0]
    plan.errors.append(Issue(sheet, row_number, "Product ID", "The parent product id is missing."))
    return None


def _check_portions(plan: Plan, db: Session) -> None:
    existing = list(db.scalars(select(MenuPriceOption)))
    by_product: dict[uuid.UUID, dict[uuid.UUID, bool]] = {}
    for option in existing:
        by_product.setdefault(option.product_id, {})[option.id] = option.is_active
    for item in plan.options:
        states = by_product.setdefault(item.product_id, {})
        if item.existing is None:
            states[item.option_id] = item.is_active
        else:
            states[item.existing.id] = item.is_active
    touched = {item.product_id for item in plan.options}
    for product_id in touched:
        active = sum(1 for value in by_product.get(product_id, {}).values() if value)
        if active == 1:
            row = next(item.row for item in plan.options if item.product_id == product_id)
            plan.errors.append(
                Issue(xlsx.SHEET_OPTIONS, row, "Active",
                    "Add at least two active portions, or leave the item on its base price.")
            )


def _check_recipes(db: Session, plan: Plan, profile: str) -> None:
    if profile not in FOOD_AND_BEVERAGE:
        return
    for item in plan.products:
        if item.values.get("item_type") != "MADE_TO_ORDER":
            continue
        if item.values.get("sell_without_recipe") or item.values.get("is_active") is False:
            continue
        if item.action == "unchanged":
            continue
        if not has_recipe(db, item.product_id):
            plan.errors.append(
                Issue(
                    item.sheet,
                    item.row,
                    "Prepared Without Recipe",
                    "A recipe is required unless the item is prepared without one.",
                )
            )


def _plan_modifiers(
    db: Session,
    plan: Plan,
    sheets: dict[str, list[list[str]]],
    by_id: dict[uuid.UUID, Product],
    names: dict[str, list[uuid.UUID]],
    food: bool,
) -> None:
    columns = _header_map(xlsx.SHEET_MODIFIERS, sheets.get(xlsx.SHEET_MODIFIERS, []), xlsx.MODIFIER_COLUMNS,
        plan.errors)
    if columns is None:
        return
    rows = _data_rows(sheets.get(xlsx.SHEET_MODIFIERS, []), len(xlsx.MODIFIER_COLUMNS))
    if not rows:
        return
    if not food:
        plan.errors.append(Issue(xlsx.SHEET_MODIFIERS, 2, "Sheet",
            "Modifiers are only imported for a restaurant or cafe."))
        return
    groups = list(db.scalars(select(ModifierGroup)))
    by_group = {group.id: group for group in groups}
    by_name = {group.name.casefold(): group for group in groups}
    drafted: dict[str, GroupPlan] = {}
    for row_number, row in rows:
        plan.modifier_rows += 1
        parent = _parent(
            plan,
            xlsx.SHEET_MODIFIERS,
            row_number,
            _value(row, columns, "Product ID"),
            _value(row, columns, "Product Name"),
            by_id,
            names,
        )
        # _parent reports option-sheet wording. A modifier row that failed still counts.
        group_name = _value(row, columns, "Group Name")
        option_name = _value(row, columns, "Option Name")
        if parent is None or not group_name or not option_name:
            if parent is not None and not group_name:
                plan.errors.append(Issue(xlsx.SHEET_MODIFIERS, row_number, "Group Name",
                    "A modifier group needs a name."))
            if parent is not None and not option_name:
                plan.errors.append(Issue(xlsx.SHEET_MODIFIERS, row_number, "Option Name",
                    "A modifier option needs a name."))
            continue
        minimum = _int_field(xlsx.SHEET_MODIFIERS, row_number, "Min Select", _value(row, columns,
            "Min Select"), plan.errors, minimum=0, maximum=20)
        maximum = _int_field(xlsx.SHEET_MODIFIERS, row_number, "Max Select", _value(row, columns,
            "Max Select"), plan.errors, minimum=1, maximum=20)
        group_active = _bool(xlsx.SHEET_MODIFIERS, row_number, "Group Active", _value(row, columns,
            "Group Active"), plan.errors, required=True)
        option_active = _bool(xlsx.SHEET_MODIFIERS, row_number, "Option Active", _value(row, columns,
            "Option Active"), plan.errors, required=True)
        default = _bool(xlsx.SHEET_MODIFIERS, row_number, "Default", _value(row, columns, "Default"),
            plan.errors, required=True)
        delta = _money(
            xlsx.SHEET_MODIFIERS,
            row_number,
            "Price Adjustment",
            _value(row, columns, "Price Adjustment") or "0.00",
            plan.errors,
            required=True,
            allow_negative=True,
        )
        if None in {minimum, maximum, group_active, option_active, default, delta}:
            continue
        if maximum < minimum:
            plan.errors.append(Issue(xlsx.SHEET_MODIFIERS, row_number, "Max Select",
                "A group cannot require more choices than it allows."))
            continue
        raw_group = _value(row, columns, "Group ID")
        existing = None
        if raw_group:
            try:
                group_id = uuid.UUID(raw_group)
            except ValueError:
                plan.errors.append(Issue(xlsx.SHEET_MODIFIERS, row_number, "Group ID", "Group ID is not a valid id."))
                continue
            existing = by_group.get(group_id)
            if existing is None:
                plan.errors.append(Issue(xlsx.SHEET_MODIFIERS, row_number, "Group ID",
                    "This modifier group was not found."))
                continue
        else:
            existing = by_name.get(group_name.casefold())
            group_id = existing.id if existing is not None else uuid.uuid4()
        key = str(group_id)
        drafted_group = drafted.get(key)
        if drafted_group is None:
            drafted_group = GroupPlan(
                "create" if existing is None else "update",
                group_id,
                existing,
                group_name,
                int(minimum),
                int(maximum),
                bool(group_active),
            )
            drafted[key] = drafted_group
        elif (drafted_group.min_select, drafted_group.max_select, drafted_group.is_active, drafted_group.name) != (
            minimum,
            maximum,
            group_active,
            group_name,
        ):
            plan.errors.append(Issue(xlsx.SHEET_MODIFIERS, row_number, "Group Name",
                "Rows for one group must use the same name and rules."))
            continue
        raw_option = _value(row, columns, "Option ID")
        option_id = None
        if raw_option:
            try:
                option_id = uuid.UUID(raw_option)
            except ValueError:
                plan.errors.append(Issue(xlsx.SHEET_MODIFIERS, row_number, "Option ID", "Option ID is not a valid id."))
                continue
        drafted_group.options.append(
            {
                "id": option_id,
                "name": option_name,
                "price_delta_cents": delta,
                "is_default": default,
                "is_active": option_active,
            }
        )
        if parent not in drafted_group.product_ids:
            drafted_group.product_ids.append(parent)
    for group in drafted.values():
        same_group = group.existing is not None and (
            group.existing.name,
            group.existing.min_select,
            group.existing.max_select,
            group.existing.is_active,
        ) == (group.name, group.min_select, group.max_select, group.is_active)
        if same_group:
            group.action = "unchanged"
        plan.groups.append(group)


def _held(db: Session, product_id: uuid.UUID) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(InventoryLevel.quantity_on_hand),
            0)).where(InventoryLevel.product_id == product_id)
    )
    return int(total or 0)


def _apply(db: Session, plan: Plan, principal: Principal) -> None:
    from app.services.markdown_service import record as record_price

    user_id = principal.user.id if principal.user is not None else None
    for item in plan.products:
        if item.action == "unchanged":
            continue
        values = item.values
        if item.action == "create":
            try:
                sku = stored_sku(db, str(values.get("sku") or ""))
            except ApiError as exc:
                raise ApiError(422, exc.code, f"{item.sheet} row {item.row}: {exc.message}") from exc
            product = Product(
                id=item.product_id,
                sku=sku,
                barcode=str(values["barcode"]),
                name=str(values["name"]),
                category=str(values.get("category") or ""),
                price_cents=int(values["price_cents"]),
                currency=str(values["currency"]),
                tax_category=str(values["tax_category"]),
                price_includes_tax=bool(values["price_includes_tax"]),
                is_active=bool(values["is_active"]),
                is_open_price=bool(values["is_open_price"]),
                is_serialized=bool(values.get("is_serialized")),
                model_number=(str(values.get("model_number") or "").strip() or None),
                price_source="override",
            )
            db.add(product)
        else:
            product = item.existing
            if product is None:
                continue
            sku_text = str(values.get("sku") or "")
            if not product.sku and sku_text and plan.profile in MENU_PROFILES:
                product.sku = sku_text
            product.name = str(values["name"])
            if int(values["price_cents"]) != product.price_cents:
                record_price(db, product, int(values["price_cents"]), "MANUAL", user_id=user_id)
                product.price_cents = int(values["price_cents"])
                product.price_source = "override"
            product.tax_category = str(values["tax_category"])
            product.price_includes_tax = bool(values["price_includes_tax"])
            product.is_active = bool(values["is_active"])
            product.is_open_price = bool(values["is_open_price"])
        if item.action != "unchanged":
            _apply_classification(db, plan, item, product)
            if "model_number" in values and item.sheet == xlsx.SHEET_PRODUCTS:
                product.model_number = str(values.get("model_number") or "").strip() or None
            _apply_weight(db, item, product)
            _apply_fashion(item, product, plan.profile)
            try:
                kind = str(values["item_type"])
                if product.item_type != kind and item.action == "update" and _held(db, product.id):
                    raise ApiError(422, "stock_on_hand",
                        f"{item.sheet} row {item.row}: item type stays while stock is on hand.")
                apply_item_type(db, product, kind)
                apply_sell_without_recipe(db, product, bool(values.get("sell_without_recipe")), sent=True)
                enforce_recipe_requirement(
                    db,
                    product,
                    creating=item.action == "create",
                    fields={"sell_without_recipe", "item_type", "is_active"},
                )
                product.sellable_units = uom_service.check_sellable(
                    db,
                    [str(values.get("unit") or "PIECE")],
                    serialized=product.is_serialized,
                    weighed=product.sold_by_weight,
                )
            except ApiError as exc:
                raise ApiError(422, exc.code, f"{item.sheet} row {item.row}: {exc.message}") from exc
    db.flush()
    _apply_options(db, plan)
    _apply_groups(db, plan)
    db.flush()


def _apply_classification(db: Session, plan: Plan, item: ProductPlan, product: Product) -> None:
    from app.services.inventory import _classify

    values = item.values
    category_name = str(values.get("category") or "")
    sub_name = str(values.get("sub_category") or "")
    brand_name = str(values.get("brand") or "") if item.sheet == xlsx.SHEET_PRODUCTS else (product.brand or "")
    if item.existing is not None and item.existing.product_model_id is not None:
        if category_name and category_name != item.existing.category:
            raise ApiError(422, "model_mismatch", f"{item.sheet} row {item.row}: this variant follows its model.")
        return
    if not category_name and item.existing is not None:
        return
    category = _category(db, category_name) if category_name else None
    if category_name and category is None:
        raise ApiError(422, "unknown_category", f"{item.sheet} row {item.row}: category was not found.")
    if category is None:
        return
    sub = None
    if sub_name:
        sub = _sub(db, category, sub_name)
        if sub is None:
            raise ApiError(422, "unknown_sub_category", f"{item.sheet} row {item.row}: sub-category was not found.")
    brand = None
    if brand_name:
        brand = _brand(db, brand_name)
        if brand is None:
            raise ApiError(422, "unknown_brand", f"{item.sheet} row {item.row}: brand was not found.")
    if item.existing is not None and category.name == item.existing.category and sub_name == (
        item.existing.sub_category_ref.name if item.existing.sub_category_ref is not None else ""
    ) and brand_name == (item.existing.brand or ""):
        return
    _classify(db, product, model_id=None, category_id=category.id, sub_category_id=sub.id if sub else None, brand=brand)
    if product.category_id is not None:
        category_service.assert_assignable(db, product.category_id, product.sub_category_id)


def _apply_weight(db: Session, item: ProductPlan, product: Product) -> None:
    if item.sheet != xlsx.SHEET_PRODUCTS:
        return
    values = item.values
    weighed = bool(values.get("sold_by_weight"))
    if weighed and (bool(values.get("is_serialized")) or bool(values.get("is_open_price"))):
        raise ApiError(422, "invalid_request", f"{item.sheet} row {item.row}: weighed items cannot be serialized.")
    product.sold_by_weight = weighed
    product.is_serialized = bool(values.get("is_serialized"))
    plu = str(values.get("plu_code") or "")
    if plu and not weighed:
        raise ApiError(422, "invalid_request", f"{item.sheet} row {item.row}: only weighed products carry a PLU.")
    if plu and (len(plu) < 4 or len(plu) > 6 or not plu.isdigit()):
        raise ApiError(422, "invalid_request", f"{item.sheet} row {item.row}: PLU must be 4 to 6 digits.")
    if plu:
        taken = db.scalar(select(Product.id).where(Product.plu_code == plu, Product.id != product.id))
        if taken is not None:
            raise ApiError(422, "conflict", f"{item.sheet} row {item.row}: PLU {plu} is already in use.")
    product.plu_code = plu or None
    tare = str(values.get("tare_grams") or "")
    product.tare_grams = int(tare) if tare.isdigit() else 0
    age = str(values.get("minimum_age") or "")
    product.minimum_age = int(age) if age.isdigit() else None


def _apply_fashion(item: ProductPlan, product: Product, profile: str) -> None:
    if item.sheet != xlsx.SHEET_PRODUCTS or not _fashion(profile):
        return
    if product.product_model_id is not None:
        return
    try:
        parsed = FashionAttributes(
            season=str(item.values.get("season") or "") or None,
            collection=str(item.values.get("collection") or "") or None,
            gender=str(item.values.get("gender") or "") or None,
            material=str(item.values.get("material") or "") or None,
            fit=str(item.values.get("fit") or "") or None,
            care=str(item.values.get("care") or "") or None,
        )
    except ValidationError as exc:
        raise ApiError(422, "invalid_request", f"{item.sheet} row {item.row}: {exc.errors()[0]['msg']}") from exc
    fashion_attributes.apply(product, parsed, only_sent=False)


def _apply_options(db: Session, plan: Plan) -> None:
    for item in plan.options:
        if item.action == "unchanged":
            continue
        if item.existing is None:
            db.add(
                MenuPriceOption(
                    id=item.option_id,
                    product_id=item.product_id,
                    name=item.name,
                    price_cents=item.price_cents,
                    sku=item.sku,
                    is_active=item.is_active,
                    position=item.position,
                )
            )
            continue
        item.existing.name = item.name
        item.existing.price_cents = item.price_cents
        item.existing.sku = item.sku
        item.existing.is_active = item.is_active
        item.existing.position = item.position


def _apply_groups(db: Session, plan: Plan) -> None:
    for group in plan.groups:
        row = group.existing
        if row is None:
            row = ModifierGroup(
                id=group.group_id,
                name=group.name,
                min_select=group.min_select,
                max_select=group.max_select,
                is_active=group.is_active,
                position=0,
            )
            db.add(row)
            db.flush()
        else:
            row.name = group.name
            row.min_select = group.min_select
            row.max_select = group.max_select
            row.is_active = group.is_active
        known = {option.id: option for option in row.options}
        by_name = {option.name.casefold(): option for option in row.options}
        for index, option in enumerate(group.options):
            label = str(option["name"]).casefold()
            current = known.get(option["id"]) if option["id"] is not None else by_name.get(label)
            if current is None:
                db.add(
                    ModifierOption(
                        group_id=row.id,
                        name=str(option["name"]),
                        price_delta_cents=int(option["price_delta_cents"]),
                        is_default=bool(option["is_default"]),
                        is_active=bool(option["is_active"]),
                        position=index,
                    )
                )
                continue
            current.name = str(option["name"])
            current.price_delta_cents = int(option["price_delta_cents"])
            current.is_default = bool(option["is_default"])
            current.is_active = bool(option["is_active"])
            current.position = index
        for product_id in group.product_ids:
            linked = db.scalar(
                select(ProductModifierGroup).where(
                    ProductModifierGroup.product_id == product_id,
                    ProductModifierGroup.group_id == row.id,
                )
            )
            if linked is None:
                db.add(ProductModifierGroup(product_id=product_id, group_id=row.id, position=0))


def preview(db: Session, data: bytes, file_name: str, mode: str) -> dict[str, object]:
    plan = build_plan(db, data, file_name, mode)
    return plan.report(committed=False)


def _prior(db: Session, key: str) -> dict[str, object] | None:
    row = db.scalar(
        select(AuditLog).where(AuditLog.client_event_id == _event_id(key), AuditLog.action == "import.catalogue")
    )
    if row is None or not isinstance(row.new_values, dict):
        return None
    body = dict(row.new_values)
    body["replayed"] = True
    return body


def commit_workbook(
    db: Session,
    principal: Principal,
    data: bytes,
    file_name: str,
    mode: str,
    *,
    job_id: str,
    confirm: bool,
    idempotency_key: str,
) -> dict[str, object]:
    if not confirm:
        raise ApiError(422, "confirmation_required", "Confirm the import before any product is written.")
    prior = _prior(db, idempotency_key)
    if prior is not None:
        return prior
    if job_id != _job_id(data):
        raise ApiError(409, "preview_mismatch", "The file changed after the preview. Review it again.")
    plan = build_plan(db, data, file_name, mode)
    summary = plan.report(committed=False)
    summary["idempotency_key"] = idempotency_key
    if plan.errors:
        _audit(db, principal, summary, committed=False)
        db.commit()
        return summary
    try:
        _apply(db, plan, principal)
        summary = plan.report(committed=True)
        summary["idempotency_key"] = idempotency_key
        _audit(db, principal, summary, committed=True)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "conflict", "The import conflicted with another save. Nothing was changed.") from exc
    except ApiError:
        db.rollback()
        raise
    from app.services import list_cache

    list_cache.bump("models")
    return summary


def _audit(db: Session, principal: Principal, summary: dict[str, object], *, committed: bool) -> None:
    record(
        db,
        action_type="UPDATE",
        action="import.catalogue",
        target_entity="Catalogue",
        user=principal.user,
        store_id=principal.store_id,
        new_values=summary,
        details={
            "mode": summary.get("mode"),
            "workbook_version": xlsx.FORMAT_VERSION,
            "created": summary.get("created"),
            "updated": summary.get("updated"),
            "unchanged": summary.get("unchanged"),
            "failed": summary.get("failed"),
            "committed": committed,
            "store_id": str(principal.store_id or ""),
        },
        client_event_id=_event_id(str(summary.get("idempotency_key") or "")),
    )


def error_report(db: Session, data: bytes, file_name: str, mode: str) -> bytes:
    plan = build_plan(db, data, file_name, mode)
    rows: list[list[object]] = [["Sheet", "Row", "Field", "Message"]]
    for issue in plan.errors:
        rows.append([issue.sheet, issue.row, issue.field, issue.message])
    if len(rows) == 1:
        rows.append(["Workbook", "", "", "This workbook has no row errors."])
    sheets = xlsx.read_workbook(data, file_name)
    payload = [
        ("Errors", rows),
        *[(name, [list(row) for row in sheet_rows]) for name, sheet_rows in sheets.items() if name != xlsx.SHEET_META],
        (xlsx.SHEET_META, [list(row) for row in sheets.get(xlsx.SHEET_META, [])]),
    ]
    return xlsx.write_workbook(payload, hidden={xlsx.SHEET_META})
