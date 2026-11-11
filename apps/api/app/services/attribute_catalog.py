"""Default attribute templates and the rules that turn a spreadsheet header into a suggestion.

Templates are copied into the tenant. Editing a copy does not change this catalog or another tenant.
Serial, IMEI, batch, and expiry headers are tracking fields, not specifications.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from app.models.attribute import ProductAttributeDefinition

_KEY = re.compile(r"[^a-z0-9]")
_MEASUREMENT = re.compile(r"^([+-]?\d+(?:[.,]\d+)?)\s*([A-Za-z\"']+)?$")
_SLUG = re.compile(r"^[a-z][a-z0-9_]{0,31}$")

ELECTRONICS = ("electronics_wholesale",)
FASHION = ("retail_fashion",)
GROCERY = ("grocery",)
RETAIL = ("wholesale_retail",)
FOOD = ("restaurant", "cafe", "quick_service")


@dataclass(frozen=True)
class TemplateAttr:
    key: str
    name: str
    data_type: str
    unit: str = ""
    options: tuple[str, ...] = ()
    profiles: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    description: str = ""
    sort_order: int = 0
    filterable: bool = False


TEMPLATES: tuple[TemplateAttr, ...] = (
    TemplateAttr("brand", "Brand", "text", aliases=("brand", "make"), sort_order=10, filterable=True),
    TemplateAttr(
        "processor",
        "Processor",
        "text",
        profiles=ELECTRONICS,
        aliases=("processor", "cpu"),
        sort_order=20,
        filterable=True,
    ),
    TemplateAttr(
        "ram",
        "RAM",
        "measurement",
        unit="GB",
        profiles=ELECTRONICS,
        aliases=("ram", "memory", "memorysize"),
        description="Capacity only, such as 16 GB. A full configuration with its own SKU is a variant.",
        sort_order=30,
        filterable=True,
    ),
    TemplateAttr(
        "storage",
        "Storage",
        "text",
        profiles=ELECTRONICS,
        aliases=("storage", "ssd", "hdd", "storagecapacity"),
        sort_order=40,
        filterable=True,
    ),
    TemplateAttr(
        "gpu",
        "GPU",
        "text",
        profiles=ELECTRONICS,
        aliases=("gpu", "graphics", "graphicscard"),
        sort_order=50,
    ),
    TemplateAttr(
        "screen_size",
        "Screen size",
        "measurement",
        unit="in",
        profiles=ELECTRONICS,
        aliases=("screensize", "displaysize"),
        sort_order=60,
        filterable=True,
    ),
    TemplateAttr(
        "warranty",
        "Warranty",
        "text",
        profiles=ELECTRONICS,
        aliases=("warranty",),
        sort_order=70,
    ),
    TemplateAttr(
        "color",
        "Color",
        "text",
        profiles=ELECTRONICS + FASHION + RETAIL,
        aliases=("color", "colour"),
        sort_order=80,
        filterable=True,
    ),
    TemplateAttr("size", "Size", "text", profiles=FASHION, aliases=("size",), sort_order=90, filterable=True),
    TemplateAttr(
        "material",
        "Material",
        "text",
        profiles=FASHION + RETAIL,
        aliases=("material", "fabric"),
        sort_order=100,
        filterable=True,
    ),
    TemplateAttr("fit", "Fit", "text", profiles=FASHION, aliases=("fit",), sort_order=110),
    TemplateAttr("gender", "Gender", "text", profiles=FASHION, aliases=("gender",), sort_order=120, filterable=True),
    TemplateAttr(
        "weight",
        "Weight",
        "measurement",
        unit="kg",
        profiles=GROCERY + RETAIL,
        aliases=("weight", "netweight"),
        sort_order=130,
    ),
    TemplateAttr(
        "volume",
        "Volume",
        "measurement",
        unit="ml",
        profiles=GROCERY,
        aliases=("volume",),
        sort_order=140,
    ),
    TemplateAttr(
        "flavor",
        "Flavor",
        "text",
        profiles=GROCERY,
        aliases=("flavor", "flavour"),
        sort_order=150,
        filterable=True,
    ),
    TemplateAttr(
        "packaging",
        "Packaging type",
        "text",
        profiles=GROCERY,
        aliases=("packaging", "packagetype"),
        sort_order=160,
    ),
    TemplateAttr(
        "origin",
        "Country of origin",
        "text",
        profiles=GROCERY,
        aliases=("origin", "countryoforigin"),
        sort_order=170,
    ),
    TemplateAttr(
        "serving_size",
        "Serving size",
        "text",
        profiles=FOOD,
        aliases=("servingsize", "portion"),
        sort_order=180,
    ),
    TemplateAttr(
        "dietary",
        "Dietary classification",
        "text",
        profiles=FOOD,
        aliases=("dietary", "diet"),
        sort_order=190,
        filterable=True,
    ),
    TemplateAttr(
        "spice_level",
        "Spice level",
        "select",
        options=("Mild", "Medium", "Hot"),
        profiles=FOOD,
        aliases=("spicelevel", "spice"),
        sort_order=200,
        filterable=True,
    ),
    TemplateAttr(
        "preparation",
        "Preparation type",
        "text",
        profiles=FOOD,
        aliases=("preparation", "preptype"),
        sort_order=210,
    ),
)

_BY_KEY = {row.key: row for row in TEMPLATES}
_TRACKING = {"imei", "imeis", "serial", "serials", "serialnumber", "expiry", "expirydate", "batch", "batchnumber"}


def normalize_header(value: str) -> str:
    return _KEY.sub("", value.lower())


def slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    text = re.sub(r"_+", "_", text)[:32]
    if not text or not text[0].isalpha():
        text = f"attr_{text}"[:32]
    return text


def is_key(value: str) -> bool:
    return _SLUG.fullmatch(value) is not None


def for_profile(profile: str) -> list[TemplateAttr]:
    return [row for row in TEMPLATES if not row.profiles or profile in row.profiles]


def is_tracking_header(header: str) -> bool:
    key = normalize_header(header)
    return key in _TRACKING or key.startswith("imei") or key.startswith("serial")


def suggest(headers: list[str], definitions: list[ProductAttributeDefinition], used: set[str]) -> dict[str, str]:
    """Header suggestions. Each column is offered once. Ambiguous headers are left unmapped."""
    aliases: dict[str, list[str]] = {}
    for definition in definitions:
        if not definition.active:
            continue
        words = {normalize_header(definition.key), normalize_header(definition.name)}
        template = _BY_KEY.get(definition.template_key or definition.key)
        if template is not None:
            words.update(template.aliases)
        for word in words:
            if word:
                aliases.setdefault(word, []).append(definition.key)
    taken = set(used)
    mapping: dict[str, str] = {}
    for header in headers:
        if header in taken or is_tracking_header(header):
            continue
        matches = aliases.get(normalize_header(header), [])
        unique = list(dict.fromkeys(matches))
        if len(unique) != 1:
            continue
        key = unique[0]
        if key in mapping:
            continue
        mapping[key] = header
        taken.add(header)
    return mapping


@dataclass(frozen=True)
class Coerced:
    display: str
    text_value: str
    number_value: Decimal | None = None
    bool_value: bool | None = None
    date_value: date | None = None
    unit: str = ""


def coerce(definition: ProductAttributeDefinition, raw: str) -> Coerced:
    text = " ".join(raw.split())
    if not text:
        raise ValueError("is empty.")
    kind = definition.data_type
    if kind == "text":
        return Coerced(display=text[:200], text_value=text[:200])
    if kind in {"number", "decimal", "measurement"}:
        return _number(definition, text, integer=kind == "number")
    if kind == "boolean":
        value = _bool(text)
        return Coerced(display="Yes" if value else "No", text_value="true" if value else "false", bool_value=value)
    if kind == "date":
        parsed = _date(text)
        return Coerced(display=parsed.isoformat(), text_value=parsed.isoformat(), date_value=parsed)
    if kind == "select":
        chosen = _option(definition, text)
        return Coerced(display=chosen, text_value=chosen)
    if kind == "multi_select":
        parts = [_option(definition, part) for part in re.split(r"[,;/|]", text) if part.strip()]
        if not parts:
            raise ValueError("needs at least one value.")
        display = ", ".join(parts)
        return Coerced(display=display[:200], text_value=display[:200])
    raise ValueError("has an unsupported type.")


def _number(definition: ProductAttributeDefinition, text: str, *, integer: bool) -> Coerced:
    if definition.data_type == "measurement":
        match = _MEASUREMENT.fullmatch(text)
        if match is None:
            raise ValueError(f"“{text}” is not a measurement.")
        number_text, found = match.group(1), match.group(2) or ""
        unit = definition.unit or found
        if definition.unit and found and not _same_unit(found, definition.unit):
            raise ValueError(f"“{text}” does not use {definition.unit}.")
    else:
        number_text, unit = text.replace(",", ""), ""
    try:
        number = Decimal(number_text.replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError(f"“{text}” is not a number.") from exc
    if integer and number != number.to_integral_value():
        raise ValueError(f"“{text}” is not a whole number.")
    display = f"{_trim(number)} {unit}".strip() if unit else _trim(number)
    return Coerced(display=display[:200], text_value=display[:200], number_value=number, unit=unit)


def _same_unit(found: str, expected: str) -> bool:
    left = found.lower().rstrip("s")
    right = expected.lower().rstrip("s")
    if left == right:
        return True
    return (left in {'"', "in", "inch"} and right in {"in", "inch"}) or (left == "gb" and right == "gb")


def _trim(number: Decimal) -> str:
    text = format(number.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _bool(text: str) -> bool:
    value = text.lower()
    if value in {"1", "true", "yes", "y"}:
        return True
    if value in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"“{text}” is not yes or no.")


def _date(text: str) -> date:
    from app.services.import_parser import parse_date

    try:
        parsed = parse_date(text)
    except ValueError as exc:
        raise ValueError(f"“{text}” is not a date.") from exc
    if parsed is None:
        raise ValueError("is empty.")
    return parsed


def _option(definition: ProductAttributeDefinition, text: str) -> str:
    cleaned = " ".join(text.split())
    options = [str(item) for item in definition.options or []]
    if not options:
        return cleaned[:200]
    for option in options:
        if option.lower() == cleaned.lower():
            return option
    raise ValueError(f"“{cleaned}” is not one of: {', '.join(options)}.")
