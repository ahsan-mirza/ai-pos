"""Which specification keys each business type may save.

Keys are the field names in packages/shared-types/src/specifications.ts.
A key with no owner is a merchant-defined detail and is allowed everywhere.
A key owned by another business type is rejected. There is no fallback profile.
"""

import re
from collections.abc import Iterable

ELECTRONICS = frozenset(
    {
        "processor",
        "ram",
        "storage",
        "graphics",
        "screen_size",
        "os",
        "color",
        "network",
        "battery",
        "capacity_litres",
        "defrost_type",
        "energy_rating",
        "compressor",
        "door_style",
        "display_tech",
        "resolution",
        "refresh_rate",
    }
)
FASHION = frozenset(
    {
        "size",
        "color",
        "fabric",
        "gender_fit",
        "length",
        "sleeve",
        "neckline",
        "material",
        "width",
    }
)
RESTAURANT = frozenset(
    {
        "patty_type",
        "patty_quantity",
        "bun_type",
        "cheese_type",
        "spice_level",
        "serving_size",
        "dietary",
        "allergens",
        "pizza_size",
        "crust",
        "bread",
        "filling",
        "beverage_size",
        "temperature",
    }
)
CAFE = frozenset(
    {
        "beverage_size",
        "temperature",
        "milk_type",
        "sugar_level",
        "flavor",
        "caffeine",
        "dietary",
        "allergens",
    }
)
GROCERY = frozenset({"net_weight", "storage_temperature", "packaging", "grade", "origin"})

OWNED: dict[str, frozenset[str]] = {
    "electronics_wholesale": ELECTRONICS,
    "retail_fashion": FASHION,
    "grocery": GROCERY,
    "restaurant": RESTAURANT,
    "cafe": CAFE,
    "quick_service": RESTAURANT,
    "wholesale_retail": frozenset(),
}

_ALL = frozenset().union(*OWNED.values())


def _text(value: str) -> str:
    return value.lower()


def _mentions(value: str, words: tuple[str, ...]) -> bool:
    return any(word in value for word in words)


def _has_term(value: str, terms: tuple[str, ...]) -> bool:
    return any(re.search(rf"(^|[^a-z]){term}(?:es|s)?([^a-z]|$)", value) for term in terms)


_DRESS = ("dress", "gown", "abaya", "jalabiya", "kaftan", "jilbab")
_FOOTWEAR = ("shoe", "footwear", "sneaker", "sandal", "heel", "boot", "loafer", "slipper")
_BAGS = ("bag", "handbag", "clutch", "tote", "purse", "wallet")
_CLOTHING = (
    "apparel",
    "fashion",
    "clothing",
    "garment",
    "shirt",
    "top",
    "tee",
    "jean",
    "trouser",
    "pant",
    "skirt",
    "blouse",
    "hijab",
    "scarf",
    "jacket",
    "coat",
    "sweater",
    "hoodie",
    "short",
)

_LAPTOP = frozenset({"processor", "ram", "storage", "graphics", "screen_size", "os"})
_MOBILE = frozenset({"storage", "ram", "color", "network", "battery"})
_FRIDGE = frozenset({"capacity_litres", "defrost_type", "energy_rating", "compressor", "door_style"})
_TV = frozenset({"screen_size", "display_tech", "resolution", "refresh_rate"})
_FASHION_CLOTHING = frozenset({"size", "color", "fabric", "gender_fit"})
_FASHION_DRESS = frozenset({"size", "color", "fabric", "length", "sleeve", "neckline", "gender_fit"})
_FASHION_FOOTWEAR = frozenset({"size", "color", "material", "width"})
_FASHION_BAG = frozenset({"size", "color", "material"})
_BURGER = frozenset(
    {"patty_type", "patty_quantity", "bun_type", "cheese_type", "spice_level", "serving_size", "dietary", "allergens"}
)
_PIZZA = frozenset({"pizza_size", "crust", "spice_level", "dietary", "allergens"})
_SANDWICH = frozenset({"bread", "filling", "spice_level", "allergens"})
_FOOD_DRINK = frozenset({"beverage_size", "temperature"})
_DESSERT = frozenset({"serving_size", "dietary", "allergens"})
_MAIN = frozenset({"serving_size", "spice_level", "dietary", "allergens"})
_CAFE_DRINK = frozenset({"beverage_size", "temperature", "milk_type", "sugar_level", "flavor", "caffeine"})
_CAFE_BAKERY = frozenset({"dietary", "allergens"})
_GROCERY_ITEM = frozenset({"net_weight", "storage_temperature", "packaging", "grade", "origin"})


def template_keys(profile: str | None, category: str, sub_category: str = "", product_name: str = "") -> frozenset[str]:
    """Field keys for this business type and category. Empty when nothing matches."""
    both = " ".join(_text(part) for part in (category, sub_category, product_name) if part).strip()
    if both == "" or not profile:
        return frozenset()
    if profile == "electronics_wholesale":
        return _electronics(both, _text(category), _text(sub_category), _text(product_name))
    if profile == "retail_fashion":
        return _fashion(both)
    if profile == "grocery":
        return _grocery(both)
    if profile in {"restaurant", "quick_service"}:
        return _restaurant(both)
    if profile == "cafe":
        return _cafe(both)
    return frozenset()


def _electronics(both: str, category: str, sub: str, product_name: str) -> frozenset[str]:
    if _mentions(both, ("refrigerator", "fridge", "freezer")):
        return _FRIDGE
    if re.search(r"(^|[^a-z])tv([^a-z]|$)|television|soundbar", both):
        return _TV
    if _mentions(both, ("phone", "mobile", "smartphone", "tablet", "ipad", "handset")):
        return _MOBILE
    computer = (
        _mentions(category, ("laptop", "desktop", "notebook", "macbook"))
        or _mentions(sub, ("laptop", "desktop", "notebook", "macbook"))
        or _mentions(product_name, ("laptop", "notebook", "macbook"))
    )
    computer_category = _mentions(category, ("computer",)) and (
        sub == "" or _mentions(sub, ("laptop", "desktop", "notebook"))
    )
    if computer or computer_category:
        return _LAPTOP
    return frozenset()


def _fashion(both: str) -> frozenset[str]:
    dress = _has_term(both, _DRESS)
    footwear = _has_term(both, _FOOTWEAR)
    clothing = _has_term(both, _CLOTHING)
    if dress and not _has_term(both, ("shoe", "boot", "sandal", "sneaker")):
        return _FASHION_DRESS
    if footwear and not _has_term(both, ("jean", "trouser", "pant")):
        return _FASHION_FOOTWEAR
    if _has_term(both, _BAGS):
        return _FASHION_BAG
    if clothing or dress:
        return _FASHION_CLOTHING
    return frozenset()


def _restaurant(both: str) -> frozenset[str]:
    if _mentions(both, ("burger",)):
        return _BURGER
    if _mentions(both, ("pizza",)):
        return _PIZZA
    if _mentions(both, ("sandwich", "wrap")):
        return _SANDWICH
    if _mentions(both, ("dessert", "cake", "sweet")):
        return _DESSERT
    if _mentions(both, ("drink", "beverage", "juice", "soda", "coffee", "tea")):
        return _FOOD_DRINK
    if _mentions(both, ("main", "appetizer", "starter", "grill", "course")):
        return _MAIN
    return frozenset()


def _cafe(both: str) -> frozenset[str]:
    if _mentions(both, ("coffee", "tea", "latte", "espresso", "chai", "juice", "drink")):
        return _CAFE_DRINK
    if _mentions(both, ("bakery", "muffin", "croissant", "pastry", "cookie", "dessert", "cake")):
        return _CAFE_BAKERY
    return frozenset()


def _grocery(both: str) -> frozenset[str]:
    if _mentions(
        both,
        (
            "dairy",
            "milk",
            "fruit",
            "vegetable",
            "produce",
            "bakery",
            "frozen",
            "beverage",
            "household",
            "grocery",
            "meat",
            "pantry",
        ),
    ):
        return _GROCERY_ITEM
    return frozenset()


def foreign_specification_keys(
    profile: str | None,
    keys: Iterable[str],
    *,
    category: str = "",
    sub_category: str = "",
    product_name: str = "",
) -> list[str]:
    """Owned keys that this business type and category do not use. Custom keys are kept."""
    allowed = template_keys(profile, category, sub_category, product_name)
    foreign: list[str] = []
    for key in keys:
        name = key.strip().lower().replace(" ", "_")
        if name in _ALL and name not in allowed and name not in foreign:
            foreign.append(name)
    return foreign
