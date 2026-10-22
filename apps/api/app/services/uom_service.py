"""Units of measure: the packs a product can be sold in, each a whole number of base units (pieces). Stock and sale
quantities always count base units; a sale line keeps the pack code and its factor. PIECE, BOX_10 and CARTON_100
are built in; a business adds its own (CASE_24, PACK_6, ...) in the units_of_measure table. Weighed goods count
grams through Product.sold_by_weight and are sold by the gram, not in packs."""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.product import Product
from app.models.sale_item import SaleItem
from app.models.uom import UnitOfMeasure
from app.schemas.payloads import UnitOption
from app.schemas.uom import UnitCreate, UnitOut, UnitUpdate

PIECE = "PIECE"
# code -> (name, short name, factor). Fixed: registers that have never synced still know them.
SYSTEM_UNITS: dict[str, tuple[str, str, int]] = {
    PIECE: ("Piece", "Pcs", 1),
    "BOX_10": ("Box of 10", "Box", 10),
    "CARTON_100": ("Carton of 100", "Carton", 100),
}
_CACHE_KEY = "uom_units"


def _system(code: str) -> UnitOption:
    name, short, factor = SYSTEM_UNITS[code]
    return UnitOption(code=code, name=name, short_name=short, factor=factor)


def units(db: Session) -> dict[str, tuple[UnitOption, bool]]:
    """Every known unit by code, with whether it may be newly assigned. Cached for the session."""
    cached = db.info.get(_CACHE_KEY)
    if cached is not None:
        return cached
    known: dict[str, tuple[UnitOption, bool]] = {code: (_system(code), True) for code in SYSTEM_UNITS}
    for row in db.scalars(select(UnitOfMeasure)):
        known[row.code] = (
            UnitOption(code=row.code, name=row.name, short_name=row.short_name, factor=row.factor),
            row.is_active,
        )
    db.info[_CACHE_KEY] = known
    return known


def _forget(db: Session) -> None:
    db.info.pop(_CACHE_KEY, None)


def factor_of(db: Session, code: str) -> int | None:
    found = units(db).get(code)
    return found[0].factor if found else None


def options_for(db: Session, codes: Iterable[str] | None) -> list[UnitOption]:
    """The given packs (always including the piece), smallest first, for the register and documents."""
    known = units(db)
    wanted = dict.fromkeys([PIECE, *(codes or [])])
    return sorted((known[code][0] for code in wanted if code in known), key=lambda option: option.factor)


def label(db: Session, code: str) -> str:
    found = units(db).get(code)
    return found[0].name if found else code.replace("_", " ").title()


def check_sellable(db: Session, codes: list[str], *, serialized: bool, weighed: bool) -> list[str]:
    """Validates a product's packs and returns them with the piece first and duplicates removed."""
    known = units(db)
    cleaned = list(dict.fromkeys([PIECE, *codes]))
    if (serialized or weighed) and cleaned != [PIECE]:
        what = "Serialized products" if serialized else "Weighed products"
        raise ApiError(422, "invalid_request", f"{what} are sold by the {'piece' if serialized else 'gram'} only.")
    for code in cleaned:
        found = known.get(code)
        if found is None:
            raise ApiError(422, "unknown_unit", f"There is no unit {code}. Add it under Units first.")
        if not found[1]:
            raise ApiError(422, "inactive_unit", f"{found[0].name} is switched off.")
    return cleaned


def _product_counts(db: Session) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sellable in db.scalars(select(Product.sellable_units)):
        for code in sellable or []:
            counts[code] = counts.get(code, 0) + 1
    return counts


def list_units(db: Session) -> list[UnitOut]:
    counts = _product_counts(db)
    rows = [
        UnitOut(**_system(code).model_dump(), id=None, is_system=True, is_active=True, products=counts.get(code, 0))
        for code in SYSTEM_UNITS
    ]
    for row in db.scalars(select(UnitOfMeasure).order_by(UnitOfMeasure.factor, UnitOfMeasure.code)):
        rows.append(
            UnitOut(
                id=row.id,
                code=row.code,
                name=row.name,
                short_name=row.short_name,
                factor=row.factor,
                is_system=False,
                is_active=row.is_active,
                products=counts.get(row.code, 0),
            )
        )
    return sorted(rows, key=lambda row: (row.factor, row.code))


def _out(db: Session, row: UnitOfMeasure) -> UnitOut:
    return next(item for item in list_units(db) if item.id == row.id)


def create_unit(db: Session, data: UnitCreate) -> UnitOut:
    if data.code in SYSTEM_UNITS:
        raise ApiError(409, "conflict", f"{data.code} is a built-in unit.")
    if db.scalar(select(UnitOfMeasure.id).where(UnitOfMeasure.code == data.code)) is not None:
        raise ApiError(409, "conflict", f"A unit called {data.code} already exists.")
    row = UnitOfMeasure(code=data.code, name=data.name, short_name=data.short_name, factor=data.factor)
    db.add(row)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise ApiError(409, "conflict", f"A unit called {data.code} already exists.") from error
    _forget(db)
    return _out(db, row)


def _custom(db: Session, unit_id: uuid.UUID) -> UnitOfMeasure:
    row = db.get(UnitOfMeasure, unit_id)
    if row is None:
        raise ApiError(404, "not_found", "Unit was not found.")
    return row


def update_unit(db: Session, unit_id: uuid.UUID, data: UnitUpdate) -> UnitOut:
    row = _custom(db, unit_id)
    if data.name is not None:
        row.name = " ".join(data.name.split())
    if data.short_name is not None:
        row.short_name = " ".join(data.short_name.split())
    if data.is_active is False and row.is_active:
        used = _product_counts(db).get(row.code, 0)
        if used:
            products = f"{used} product{'s' if used != 1 else ''}"
            raise ApiError(409, "unit_in_use", f"{products} still sell in {row.name}; remove it there first.")
    if data.is_active is not None:
        row.is_active = data.is_active
    db.commit()
    _forget(db)
    return _out(db, row)


def delete_unit(db: Session, unit_id: uuid.UUID) -> None:
    row = _custom(db, unit_id)
    used = _product_counts(db).get(row.code, 0)
    if used:
        raise ApiError(409, "unit_in_use", f"{used} product{'s' if used != 1 else ''} still sell in {row.name}.")
    sold = db.scalar(select(func.count()).select_from(SaleItem).where(SaleItem.unit_type == row.code)) or 0
    if sold:
        raise ApiError(409, "unit_in_use", f"{row.name} is on {sold} past sale lines; switch it off instead.")
    db.delete(row)
    db.commit()
    _forget(db)
