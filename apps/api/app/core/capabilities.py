"""Business profiles and capabilities. Mirrors packages/shared-types/src/capabilities.ts; tests keep both in step.

Code checks capabilities, never profiles: a profile is only the preset a merchant starts from. Capabilities that are
still on the roadmap (`available=False`) can be chosen for a business but are never enabled.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ApiError


class Capability(StrEnum):
    SERIAL_TRACKING = "serial_tracking"
    WHOLESALE_PRICING = "wholesale_pricing"
    B2B_CREDIT = "b2b_credit"
    QUOTES_LAYAWAY = "quotes_layaway"
    MULTI_CURRENCY = "multi_currency"
    CHEQUES = "cheques"
    REPAIRS = "repairs"
    WARRANTY = "warranty"
    TRADE_IN = "trade_in"
    LOYALTY = "loyalty"
    PROMOTIONS = "promotions"
    VARIANTS_MATRIX = "variants_matrix"
    CONSIGNMENT = "consignment"
    WEIGHED_ITEMS = "weighed_items"
    FEFO = "fefo"
    MENU_MODIFIERS = "menu_modifiers"
    OPEN_ORDERS = "open_orders"
    TABLES = "tables"
    KDS = "kds"
    RECIPES = "recipes"
    SPLIT_BILLS = "split_bills"
    TIPS_SERVICE_CHARGE = "tips_service_charge"
    DELIVERY_CHANNELS = "delivery_channels"
    SALES_ORDERS = "sales_orders"
    CARD_TERMINALS = "card_terminals"
    BNPL = "bnpl"
    GIFT_CARDS = "gift_cards"
    TAX_FREE = "tax_free"
    ALTERATIONS = "alterations"
    FASHION_RENTAL = "fashion_rental"
    ONLINE_STORE = "online_store"
    CUSTOMER_REORDERS = "customer_reorders"
    DEEP_ANALYTICS = "deep_analytics"
    AXIZ_REACH = "axiz_reach"
    UAE_EINVOICING = "uae_einvoicing"


C = Capability


@dataclass(frozen=True)
class CapabilitySpec:
    label: str
    available: bool
    requires: tuple[Capability, ...] = ()


SPECS: dict[Capability, CapabilitySpec] = {
    C.WHOLESALE_PRICING: CapabilitySpec("Wholesale mode & tier pricing", True),
    C.QUOTES_LAYAWAY: CapabilitySpec("Quotations, holds & layaway", True),
    C.PROMOTIONS: CapabilitySpec("Promotions", True),
    C.MULTI_CURRENCY: CapabilitySpec("Foreign currency cash", True),
    C.SERIAL_TRACKING: CapabilitySpec("IMEI / serial tracking", True),
    C.VARIANTS_MATRIX: CapabilitySpec("Size & colour matrix", True),
    C.CONSIGNMENT: CapabilitySpec("Consignment stock", True),
    C.WEIGHED_ITEMS: CapabilitySpec("Weighed items & scales", True),
    C.FEFO: CapabilitySpec("Expiry-first stock (FEFO)", True),
    C.B2B_CREDIT: CapabilitySpec("B2B credit accounts", True),
    C.CHEQUES: CapabilitySpec("Cheques & PDCs", True),
    C.LOYALTY: CapabilitySpec("Loyalty points", True),
    C.REPAIRS: CapabilitySpec("Repairs", True),
    C.WARRANTY: CapabilitySpec("Warranties", True),
    C.TRADE_IN: CapabilitySpec("Trade-ins", True),
    C.MENU_MODIFIERS: CapabilitySpec("Menu modifiers", True),
    C.OPEN_ORDERS: CapabilitySpec("Open orders & tabs", True),
    C.TABLES: CapabilitySpec("Tables & floor plan", True, (C.OPEN_ORDERS,)),
    C.KDS: CapabilitySpec("Kitchen display", True),
    C.RECIPES: CapabilitySpec("Recipes & ingredients", True, (C.MENU_MODIFIERS,)),
    C.SPLIT_BILLS: CapabilitySpec("Split bills", True, (C.OPEN_ORDERS,)),
    C.TIPS_SERVICE_CHARGE: CapabilitySpec("Tips & service charge", True, (C.OPEN_ORDERS,)),
    C.DELIVERY_CHANNELS: CapabilitySpec("Delivery channels", True, (C.OPEN_ORDERS,)),
    C.SALES_ORDERS: CapabilitySpec("Sales orders & deliveries", True),
    C.CARD_TERMINALS: CapabilitySpec("Integrated card terminals", True),
    C.BNPL: CapabilitySpec("Buy now, pay later (Tabby, Tamara)", True),
    C.GIFT_CARDS: CapabilitySpec("Gift cards", True),
    C.TAX_FREE: CapabilitySpec("Tax-free for tourists", True),
    C.ALTERATIONS: CapabilitySpec("Alterations & tailoring", True),
    C.FASHION_RENTAL: CapabilitySpec("Fashion rental", True),
    C.ONLINE_STORE: CapabilitySpec("Online store", True),
    C.CUSTOMER_REORDERS: CapabilitySpec("Customer reorder plans", True),
    C.DEEP_ANALYTICS: CapabilitySpec("Deep analytics", True),
    C.AXIZ_REACH: CapabilitySpec("AxizReach — Customer Engagement", True),
    C.UAE_EINVOICING: CapabilitySpec("UAE e-Invoicing", True),
}
ORDER: tuple[Capability, ...] = tuple(SPECS)
BUILT_TODAY: tuple[Capability, ...] = tuple(capability for capability in ORDER if SPECS[capability].available)

DEFAULT_PROFILE = "electronics_wholesale"
# Spelled out rather than "everything built": grocery and restaurant modules must not appear in an
# electronics shop just because they ship.
ELECTRONICS_WHOLESALE: tuple[Capability, ...] = (
    C.WHOLESALE_PRICING,
    C.QUOTES_LAYAWAY,
    C.PROMOTIONS,
    C.MULTI_CURRENCY,
    C.SERIAL_TRACKING,
    C.VARIANTS_MATRIX,
    C.CONSIGNMENT,
    C.B2B_CREDIT,
    C.CHEQUES,
    C.LOYALTY,
    C.REPAIRS,
    C.WARRANTY,
    C.TRADE_IN,
    C.CARD_TERMINALS,
    C.BNPL,
)
WHOLESALE_RETAIL: tuple[Capability, ...] = (
    C.WHOLESALE_PRICING,
    C.SALES_ORDERS,
    C.B2B_CREDIT,
    C.QUOTES_LAYAWAY,
    C.PROMOTIONS,
    C.LOYALTY,
    C.MULTI_CURRENCY,
    C.CARD_TERMINALS,
    C.CUSTOMER_REORDERS,
)
PROFILES: dict[str, tuple[Capability, ...]] = {
    "electronics_wholesale": ELECTRONICS_WHOLESALE,
    "wholesale_retail": WHOLESALE_RETAIL,
    "retail_fashion": (
        C.QUOTES_LAYAWAY,
        C.LOYALTY,
        C.PROMOTIONS,
        C.MULTI_CURRENCY,
        C.VARIANTS_MATRIX,
        C.CONSIGNMENT,
        C.GIFT_CARDS,
    ),
    "grocery": (C.LOYALTY, C.PROMOTIONS, C.WEIGHED_ITEMS, C.FEFO),
    "restaurant": (
        C.LOYALTY,
        C.PROMOTIONS,
        C.MULTI_CURRENCY,
        C.TABLES,
        C.OPEN_ORDERS,
        C.MENU_MODIFIERS,
        C.KDS,
        C.RECIPES,
        C.SPLIT_BILLS,
        C.TIPS_SERVICE_CHARGE,
    ),
    "cafe": (C.LOYALTY, C.PROMOTIONS, C.MENU_MODIFIERS, C.OPEN_ORDERS, C.KDS, C.RECIPES),
    # Pay first at the counter; delivery-app orders still arrive as open orders.
    "quick_service": (
        C.LOYALTY,
        C.PROMOTIONS,
        C.MENU_MODIFIERS,
        C.OPEN_ORDERS,
        C.KDS,
        C.RECIPES,
        C.DELIVERY_CHANNELS,
    ),
}
FOOD_AND_BEVERAGE = frozenset({"restaurant", "cafe", "quick_service"})
PROFILE_LABELS: dict[str, str] = {
    "electronics_wholesale": "Electronics",
    "wholesale_retail": "Wholesale & Retail",
    "retail_fashion": "Fashion & Retail",
    "grocery": "Grocery & Supermarket",
    "restaurant": "Restaurant",
    "cafe": "Cafe",
    "quick_service": "Quick Service",
}

# What a business of each type may switch on by itself once onboarding is done. Anything else needs IT support
# (a module request, or a business-type migration); each set holds its preset and the modules those depend on.
_RETAIL_CORE = (
    C.WHOLESALE_PRICING,
    C.QUOTES_LAYAWAY,
    C.PROMOTIONS,
    C.MULTI_CURRENCY,
    C.B2B_CREDIT,
    C.CHEQUES,
    C.LOYALTY,
    C.SALES_ORDERS,
    C.CARD_TERMINALS,
    C.BNPL,
    C.GIFT_CARDS,
    C.TAX_FREE,
    C.ONLINE_STORE,
    C.DEEP_ANALYTICS,
    C.AXIZ_REACH,
    C.UAE_EINVOICING,
)
_FOOD_CORE = (
    C.LOYALTY,
    C.PROMOTIONS,
    C.MULTI_CURRENCY,
    C.FEFO,
    C.MENU_MODIFIERS,
    C.OPEN_ORDERS,
    C.TABLES,
    C.KDS,
    C.RECIPES,
    C.SPLIT_BILLS,
    C.TIPS_SERVICE_CHARGE,
    C.DELIVERY_CHANNELS,
    C.CARD_TERMINALS,
    C.DEEP_ANALYTICS,
    C.AXIZ_REACH,
    C.UAE_EINVOICING,
)
COMPATIBLE: dict[str, frozenset[Capability]] = {
    "electronics_wholesale": frozenset(
        (*_RETAIL_CORE, C.SERIAL_TRACKING, C.VARIANTS_MATRIX, C.CONSIGNMENT, C.REPAIRS, C.WARRANTY, C.TRADE_IN)
    ),
    "wholesale_retail": frozenset((*_RETAIL_CORE, C.CUSTOMER_REORDERS, C.REPAIRS)),
    "retail_fashion": frozenset(
        (*_RETAIL_CORE, C.VARIANTS_MATRIX, C.CONSIGNMENT, C.SERIAL_TRACKING, C.ALTERATIONS, C.FASHION_RENTAL)
    ),
    "grocery": frozenset((*_RETAIL_CORE, C.WEIGHED_ITEMS, C.FEFO, C.CONSIGNMENT, C.VARIANTS_MATRIX)),
    "restaurant": frozenset(_FOOD_CORE),
    "cafe": frozenset(_FOOD_CORE),
    "quick_service": frozenset(_FOOD_CORE),
}


def compatible(profile: str) -> tuple[Capability, ...]:
    """The modules this business type can switch on by itself, in catalogue order."""
    allowed = COMPATIBLE.get(profile, frozenset(PROFILES.get(profile, ())))
    return tuple(capability for capability in ORDER if capability in allowed)


@dataclass(frozen=True)
class Catalogue:
    """Base is the business-type preset. Optional is everything else that type may switch on."""

    base: tuple[Capability, ...]
    optional: tuple[Capability, ...]


def catalogue(profile: str) -> Catalogue:
    """Included modules versus the extra modules this business type is allowed to turn on.

    Dependencies of an optional module stay inside the combined set, so turning one on never
    requires a module the business type is not allowed to use.
    """
    preset = set(PROFILES.get(profile, ()))
    base = tuple(capability for capability in ORDER if capability in preset)
    optional = tuple(capability for capability in compatible(profile) if capability not in preset)
    return Catalogue(base=base, optional=optional)


# Self-service signup: each business type that can go live, refined by a sub-type into a module selection.
# A profile in PROFILES but missing here still joins the waitlist.
_GROCERY_COUNTER: tuple[Capability, ...] = (
    C.LOYALTY,
    C.PROMOTIONS,
    C.WEIGHED_ITEMS,
    C.FEFO,
    C.CARD_TERMINALS,
)
SUB_TYPES: dict[str, dict[str, tuple[Capability, ...]]] = {
    "electronics_wholesale": {
        "electronics_retail": (
            C.PROMOTIONS,
            C.MULTI_CURRENCY,
            C.SERIAL_TRACKING,
            C.LOYALTY,
            C.REPAIRS,
            C.WARRANTY,
            C.TRADE_IN,
            C.CARD_TERMINALS,
            C.BNPL,
        ),
        "electronics_b2b": ELECTRONICS_WHOLESALE,
        # Retail modules are already inside the wholesale preset, so both is that full set.
        "electronics_both": ELECTRONICS_WHOLESALE,
    },
    "wholesale_retail": {
        "wholesale_distributor": WHOLESALE_RETAIL,
        "retail_shop": (
            C.PROMOTIONS,
            C.LOYALTY,
            C.QUOTES_LAYAWAY,
            C.CARD_TERMINALS,
            C.CUSTOMER_REORDERS,
            C.MULTI_CURRENCY,
        ),
    },
    "retail_fashion": {
        "fashion_boutique": (
            C.QUOTES_LAYAWAY,
            C.LOYALTY,
            C.PROMOTIONS,
            C.MULTI_CURRENCY,
            C.VARIANTS_MATRIX,
            C.GIFT_CARDS,
            C.ALTERATIONS,
        ),
        "fashion_chain": PROFILES["retail_fashion"],
    },
    "grocery": {
        "grocery_shop": _GROCERY_COUNTER,
        "grocery_supermarket": (*_GROCERY_COUNTER, C.GIFT_CARDS, C.MULTI_CURRENCY),
        "grocery_cash_carry": (
            C.LOYALTY,
            C.PROMOTIONS,
            C.WEIGHED_ITEMS,
            C.FEFO,
            C.WHOLESALE_PRICING,
            C.QUOTES_LAYAWAY,
            C.B2B_CREDIT,
            C.CHEQUES,
            C.SALES_ORDERS,
            C.CARD_TERMINALS,
        ),
    },
    # Food & beverage: the starter kit seats guests (floor plan) only where TABLES is on.
    "restaurant": {
        "full_service": (*PROFILES["restaurant"], C.CARD_TERMINALS),
        "restaurant_delivery": (*PROFILES["restaurant"], C.DELIVERY_CHANNELS, C.CARD_TERMINALS),
    },
    "cafe": {
        "counter_cafe": (*PROFILES["cafe"], C.CARD_TERMINALS),
        "sit_down_cafe": (*PROFILES["cafe"], C.TABLES, C.SPLIT_BILLS, C.TIPS_SERVICE_CHARGE, C.CARD_TERMINALS),
    },
    "quick_service": {
        "qsr_counter": (
            *(capability for capability in PROFILES["quick_service"] if capability != C.DELIVERY_CHANNELS),
            C.CARD_TERMINALS,
        ),
        "qsr_delivery": (*PROFILES["quick_service"], C.CARD_TERMINALS),
    },
}


def parse(values: Iterable[str]) -> list[Capability]:
    """Known capabilities from stored or submitted ids, deduplicated, in catalogue order."""
    known = {capability.value for capability in Capability}
    chosen = {value for value in values if value in known}
    return [capability for capability in ORDER if capability.value in chosen]


def missing_dependencies(selected: Iterable[Capability]) -> dict[Capability, list[Capability]]:
    chosen = set(selected)
    return {
        capability: [required for required in SPECS[capability].requires if required not in chosen]
        for capability in chosen
        if any(required not in chosen for required in SPECS[capability].requires)
    }


# Modules the Windows register already implements. Anything else stays an admin-portal feature.
REGISTER_CAPABILITIES: frozenset[Capability] = frozenset(
    {
        Capability.WHOLESALE_PRICING,
        Capability.QUOTES_LAYAWAY,
        Capability.PROMOTIONS,
        Capability.MULTI_CURRENCY,
        Capability.SERIAL_TRACKING,
        Capability.VARIANTS_MATRIX,
        Capability.WEIGHED_ITEMS,
        Capability.B2B_CREDIT,
        Capability.CHEQUES,
        Capability.LOYALTY,
        Capability.REPAIRS,
        Capability.TRADE_IN,
        Capability.MENU_MODIFIERS,
        Capability.OPEN_ORDERS,
        Capability.TABLES,
        Capability.KDS,
        Capability.SPLIT_BILLS,
        Capability.TIPS_SERVICE_CHARGE,
        Capability.DELIVERY_CHANNELS,
        Capability.SALES_ORDERS,
        Capability.CARD_TERMINALS,
        Capability.BNPL,
        Capability.GIFT_CARDS,
        Capability.CUSTOMER_REORDERS,
        Capability.FASHION_RENTAL,
    }
)


@dataclass(frozen=True)
class Resolved:
    enabled: tuple[Capability, ...]
    planned: tuple[Capability, ...]


def resolve(
    profile: str,
    selection: Sequence[str] | None,
    managed: Mapping[str, str] | None = None,
    purchased: Iterable[str] | None = None,
) -> Resolved:
    """The profile preset, or the stored selection when set, plus paid add-on modules that fit this
    business type, then IT support's overrides. Roadmap modules become planned, and a module missing
    what it needs stays off."""
    allowed = set(compatible(profile))
    if selection is None:
        chosen = [capability for capability in PROFILES.get(profile, ()) if capability in allowed]
    else:
        chosen = [capability for capability in parse(selection) if capability in allowed]
    if purchased:
        extra = {capability.value for capability in parse(purchased) if capability in allowed}
        chosen = parse({capability.value for capability in chosen} | extra)
    if managed:
        # Support may force a module this type does not normally offer. The console marks fits_type false.
        forced_on = {value for value, state in managed.items() if state == "on"}
        forced_off = {value for value, state in managed.items() if state == "off"}
        values = ({capability.value for capability in chosen} | forced_on) - forced_off
        chosen = parse(values)
    blocked = set(missing_dependencies(chosen))
    return Resolved(
        enabled=tuple(c for c in chosen if SPECS[c].available and c not in blocked),
        planned=tuple(c for c in chosen if not SPECS[c].available),
    )


def enabled_capabilities(db: Session) -> frozenset[Capability]:
    from app.services.settings_service import cached_settings

    return frozenset(cached_settings(db).capabilities)


def has_capability(db: Session, capability: Capability) -> bool:
    return capability in enabled_capabilities(db)


def require_capability(capability: Capability) -> Callable[..., None]:
    """Router dependency: 403 when the business has this module switched off.

    A signed-in user also needs access when the module is a paid add-on. A register using only
    its device token is unchanged; the user's own token is what the till sends once they unlock.
    """

    def dependency(db: Annotated[Session, Depends(get_db)], request: Request) -> None:
        if not has_capability(db, capability):
            raise ApiError(
                403,
                "capability_disabled",
                f"{SPECS[capability].label} is not enabled for this business. "
                "A business-wide admin can turn it on in Store Settings.",
            )
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            return
        from app.core.config import get_settings
        from app.core.deps import get_principal
        from app.services.addon_access import enforce_user

        principal = get_principal(db, get_settings(), authorization=header)
        enforce_user(db, principal, capability.value)

    return dependency
