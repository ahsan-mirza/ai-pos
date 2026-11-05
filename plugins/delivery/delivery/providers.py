"""Provider catalogue. A listed marketplace is not a live integration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    code: str
    name: str
    kind: str
    status: str
    countries: tuple[str, ...]
    capabilities: tuple[str, ...]
    detail: str


def _waiting(code: str, name: str, kind: str, countries: tuple[str, ...]) -> Provider:
    return Provider(
        code=code,
        name=name,
        kind=kind,
        status="awaiting_partner",
        countries=countries,
        capabilities=(),
        detail="Partner API access is not approved. This provider cannot be activated.",
    )


PROVIDERS: tuple[Provider, ...] = (
    Provider(
        code="generic",
        name="Generic webhook",
        kind="generic",
        status="available",
        countries=(),
        capabilities=("orders",),
        detail="Uses the existing Delivery channels webhook. It is not a marketplace partnership.",
    ),
    _waiting("deliverect", "Deliverect", "aggregator", ()),
    _waiting("urbanpiper", "UrbanPiper", "aggregator", ()),
    _waiting("talabat", "Talabat", "marketplace", ("AE", "KW", "BH", "OM", "QA", "JO")),
    _waiting("foodpanda", "foodpanda", "marketplace", ()),
    _waiting("deliveroo", "Deliveroo", "marketplace", ()),
    _waiting("careem", "Careem", "marketplace", ("AE", "SA")),
    _waiting("keeta", "Keeta", "marketplace", ()),
    _waiting("noon_food", "Noon Food", "marketplace", ("AE", "SA")),
    _waiting("zomato", "Zomato", "marketplace", ()),
    _waiting("swiggy", "Swiggy", "marketplace", ()),
    _waiting("uber_eats", "Uber Eats", "marketplace", ()),
    _waiting("doordash", "DoorDash", "marketplace", ()),
)

BY_CODE = {provider.code: provider for provider in PROVIDERS}


def get_provider(code: str) -> Provider | None:
    return BY_CODE.get(code)
