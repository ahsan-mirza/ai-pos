import re
from pathlib import Path

import pytest
from sqlalchemy import select
from tests.test_open_price import labour_product
from tests.test_warranty import repair

from app.core import capabilities as catalog
from app.core.capabilities import Capability
from app.models import AuditLog
from app.services.settings_service import provision_profile
from wholesale_support import admin, device, event, imeis, push, seed

SHARED = Path(__file__).resolve().parents[3] / "packages" / "shared-types" / "src" / "capabilities.ts"
FOOD = ("restaurant", "cafe", "quick_service")
GATED = {
    Capability.WHOLESALE_PRICING: "/api/v1/pricing/matrix",
    Capability.QUOTES_LAYAWAY: "/api/v1/quotes",
    Capability.REPAIRS: "/api/v1/repairs",
    Capability.CHEQUES: "/api/v1/cheques",
    Capability.WARRANTY: "/api/v1/warranties",
    Capability.MULTI_CURRENCY: "/api/v1/currencies",
    Capability.TRADE_IN: "/api/v1/trade-ins",
    Capability.SERIAL_TRACKING: "/api/v1/inventory/serials",
}


def change_profile(client, headers: dict[str, str], profile: str, capabilities: list[str] | None = None, **extra):
    body = {"business_profile": profile, "capabilities": capabilities, **extra}
    return client.put("/api/v1/settings/profile", headers=headers, json=body)


def shared_catalog() -> tuple[dict[str, tuple[str, bool, list[str]]], dict[str, list[str] | None]]:
    """(capability -> (label, available, requires)) and (profile -> preset, None meaning every built module)."""
    source = SHARED.read_text(encoding="utf-8")
    specs = {
        match["id"]: (match["label"], match["available"] == "true", re.findall(r'"(\w+)"', match["requires"]))
        for match in re.finditer(
            r'\{ id: "(?P<id>\w+)", label: "(?P<label>[^"]+)".*?'
            r"available: (?P<available>true|false), requires: \[(?P<requires>[^\]]*)\] \}",
            source,
        )
    }
    named = {
        match["name"]: re.findall(r'"(\w+)"', match["items"])
        for match in re.finditer(r"const (?P<name>\w+): Capability\[\] = \[(?P<items>[^\]]*)\]", source)
    }
    presets_block = source.split("export const PROFILE_PRESETS", 1)[1]
    presets: dict[str, list[str] | None] = {}
    for match in re.finditer(r'id: "(?P<id>\w+)",.*?capabilities: (?P<caps>\w+|\[[^\]]*\])', presets_block, re.S):
        caps = match["caps"]
        presets[match["id"]] = named[caps] if caps in named else re.findall(r'"(\w+)"', caps)
    return specs, presets


def test_python_and_typescript_catalogs_match() -> None:
    specs, presets = shared_catalog()
    assert list(specs) == [capability.value for capability in catalog.ORDER]
    for capability, spec in catalog.SPECS.items():
        assert specs[capability.value] == (spec.label, spec.available, [required.value for required in spec.requires])
    assert set(presets) == set(catalog.PROFILES)
    for profile, preset in presets.items():
        expected = [capability.value for capability in catalog.PROFILES[profile]]
        assert preset == expected


@pytest.mark.parametrize("profile", sorted(catalog.PROFILES))
def test_every_preset_is_consistent(profile: str) -> None:
    preset = catalog.PROFILES[profile]
    assert not catalog.missing_dependencies(preset), f"{profile} preset breaks a dependency"
    resolved = catalog.resolve(profile, None)
    assert set(resolved.enabled) | set(resolved.planned) == set(preset)
    assert all(catalog.SPECS[capability].available for capability in resolved.enabled)
    assert not any(catalog.SPECS[capability].available for capability in resolved.planned)


def test_b2b_credit_follows_the_business_type(client) -> None:
    seed(client)
    headers, _ = admin(client)
    current = client.get("/api/v1/settings", headers=headers).json()
    assert "b2b_credit" in current["capabilities"]

    fashion = change_profile(client, headers, "retail_fashion")
    assert fashion.status_code == 200, fashion.text
    assert "b2b_credit" not in fashion.json()["capabilities"]
    fashion_plus = [item.value for item in catalog.PROFILES["retail_fashion"]] + ["b2b_credit"]
    enabled = change_profile(client, headers, "retail_fashion", capabilities=fashion_plus)
    assert enabled.status_code == 200, enabled.text
    assert "b2b_credit" in enabled.json()["capabilities"]

    grocery = [item.value for item in catalog.PROFILES["grocery"]]
    assert "b2b_credit" not in grocery
    grocery_on = change_profile(client, headers, "grocery", capabilities=[*grocery, "b2b_credit"])
    assert grocery_on.status_code == 200, grocery_on.text

    for profile in FOOD:
        assert catalog.Capability.B2B_CREDIT not in catalog.compatible(profile)


@pytest.mark.parametrize("profile", FOOD)
def test_food_service_cannot_enable_b2b_credit(client, profile: str) -> None:
    headers, _ = admin(client)
    opened = change_profile(client, headers, profile, complete_onboarding=True)
    assert opened.status_code == 200, opened.text
    preset = [item.value for item in catalog.PROFILES[profile]]
    refused = change_profile(client, headers, profile, capabilities=[*preset, "b2b_credit"])
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "module_not_available"


def test_existing_installs_keep_every_built_module(client) -> None:
    body = client.get("/api/v1/settings", headers=device()).json()
    assert body["business_profile"] == "electronics_wholesale"
    assert body["capabilities"] == [capability.value for capability in catalog.ELECTRONICS_WHOLESALE]
    assert body["planned_capabilities"] == []
    seed(client)
    headers, _ = admin(client)
    for path in GATED.values():
        assert client.get(path, headers=headers).status_code != 403, path


@pytest.mark.parametrize("profile", FOOD)
def test_food_and_beverage_presets_enable_only_shipped_modules(client, profile: str) -> None:
    headers, _ = admin(client)
    response = change_profile(client, headers, profile)
    assert response.status_code == 200, response.text
    body = response.json()
    resolved = catalog.resolve(profile, None)
    assert body["capabilities"] == [capability.value for capability in resolved.enabled]
    assert body["planned_capabilities"] == [capability.value for capability in resolved.planned]
    assert {"loyalty", "promotions"} <= set(body["capabilities"])
    unshipped = {spec for spec, value in catalog.SPECS.items() if not value.available}
    assert not unshipped & set(catalog.parse(body["capabilities"]))


def test_switching_profile_gates_routers_and_takes_effect_immediately(client) -> None:
    seed(client)
    headers, _ = admin(client)
    assert client.get("/api/v1/repairs", headers=headers).status_code == 200
    assert change_profile(client, headers, "cafe").status_code == 200
    for path in GATED.values():
        blocked = client.get(path, headers=headers)
        assert blocked.status_code == 403, path
        assert blocked.json()["error"]["code"] == "capability_disabled"
    quotes = client.get("/api/v1/quotes", headers=headers).json()["error"]["message"]
    assert quotes.startswith("Quotations, holds & layaway is not enabled")
    assert client.get("/api/v1/loyalty/settings", headers=headers).status_code == 200
    assert client.get("/api/v1/promotions", headers=headers).status_code == 200
    assert client.get("/api/v1/inventory/availability", headers=headers).status_code != 403

    assert change_profile(client, headers, "electronics_wholesale").status_code == 200
    for path in GATED.values():
        assert client.get(path, headers=headers).status_code != 403, path


def test_custom_module_selection_and_dependencies(client) -> None:
    headers, _ = admin(client)
    missing = change_profile(client, headers, "cafe", ["tables", "loyalty"])
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "capability_dependencies"
    assert "open_orders" in missing.json()["error"]["message"]
    assert change_profile(client, headers, "cafe", ["tables"]).status_code == 422
    assert change_profile(client, headers, "cafe", ["teleport"]).status_code == 422
    assert change_profile(client, headers, "bakery").status_code == 422

    # A module still on the roadmap is kept as planned, never enabled (none once everything has shipped).
    unshipped = [cap.value for cap, spec in catalog.SPECS.items() if not spec.available and not spec.requires][:1]
    chosen = change_profile(
        client, headers, "retail_fashion", ["quotes_layaway", "b2b_credit", "variants_matrix", *unshipped]
    )
    assert chosen.status_code == 200, chosen.text
    body = chosen.json()
    assert body["business_profile"] == "retail_fashion"
    assert body["capabilities"] == ["quotes_layaway", "variants_matrix", "b2b_credit"]
    assert body["planned_capabilities"] == unshipped
    assert client.get("/api/v1/quotes", headers=headers).status_code == 200
    assert client.get("/api/v1/repairs", headers=headers).status_code == 403


def test_profile_changes_are_audited_and_complete_onboarding(client, session) -> None:
    headers, _ = admin(client)
    assert client.get("/api/v1/settings", headers=headers).json()["onboarded"] is False
    response = change_profile(client, headers, "grocery", complete_onboarding=True)
    assert response.status_code == 200 and response.json()["onboarded"] is True
    entry = session.scalar(select(AuditLog).where(AuditLog.action == "settings.profile"))
    assert entry is not None
    assert entry.old_values["business_profile"] == "electronics_wholesale"
    assert entry.new_values == {
        "business_profile": "grocery",
        "capabilities": ["loyalty", "promotions", "weighed_items", "fefo"],
    }
    assert entry.details["planned"] == []


@pytest.mark.parametrize("profile", sorted(catalog.PROFILES))
def test_each_business_type_can_keep_its_preset_after_onboarding(profile: str) -> None:
    allowed = set(catalog.compatible(profile))
    assert set(catalog.PROFILES[profile]) <= allowed
    assert not catalog.missing_dependencies(allowed), f"{profile} lists a module without what it needs"
    for sub_types in catalog.SUB_TYPES.get(profile, {}).values():
        assert set(sub_types) <= allowed


def signup_cards() -> dict[str, list[str]]:
    """profile -> sub-type ids, parsed from SIGNUP_BUSINESS_CARDS in packages/shared-types/src/signup.ts."""
    source = (SHARED.parent / "signup.ts").read_text(encoding="utf-8")
    block = source.split("export const SIGNUP_BUSINESS_CARDS", 1)[1].split("\n];", 1)[0]
    cards: dict[str, list[str]] = {}
    for chunk in re.split(r'\n  \{\n    profile: "', block)[1:]:
        profile = chunk.split('"', 1)[0]
        cards[profile] = re.findall(r'id: "(\w+)"', chunk)
    return cards


def test_signup_cards_match_the_sub_types_that_can_go_live() -> None:
    cards = signup_cards()
    live = {profile: list(sub_types) for profile, sub_types in catalog.SUB_TYPES.items()}
    assert {profile: subs for profile, subs in cards.items() if subs} == live
    assert set(cards) <= set(catalog.PROFILES)
    for profile in FOOD:
        assert profile in live, f"{profile} should sign up on its own"


@pytest.mark.parametrize("profile,sub_type", [(p, s) for p in FOOD for s in catalog.SUB_TYPES[p]])
def test_food_sub_types_keep_their_modules_working(profile: str, sub_type: str) -> None:
    chosen = catalog.SUB_TYPES[profile][sub_type]
    assert not catalog.missing_dependencies(chosen)
    resolved = catalog.resolve(profile, [capability.value for capability in chosen])
    assert Capability.MENU_MODIFIERS in resolved.enabled
    assert Capability.KDS in resolved.enabled
    seats_guests = Capability.TABLES in resolved.enabled
    assert seats_guests == (sub_type in {"full_service", "restaurant_delivery", "sit_down_cafe"})


def test_business_type_locks_after_onboarding_and_only_fitting_modules_switch_on(client) -> None:
    headers, _ = admin(client)
    assert change_profile(client, headers, "cafe").status_code == 200
    assert change_profile(client, headers, "electronics_wholesale", complete_onboarding=True).status_code == 200

    locked = change_profile(client, headers, "cafe")
    assert locked.status_code == 409
    assert locked.json()["error"]["code"] == "business_type_locked"
    assert "support@axizpos.com" in locked.json()["error"]["message"]

    wrong = change_profile(client, headers, "electronics_wholesale", ["loyalty", "weighed_items"])
    assert wrong.status_code == 422 and wrong.json()["error"]["code"] == "module_not_available"

    trimmed = [c.value for c in catalog.ELECTRONICS_WHOLESALE if c is not Capability.TRADE_IN]
    assert change_profile(client, headers, "electronics_wholesale", trimmed).status_code == 200

    modules = client.get("/api/v1/tenant/modules", headers=headers)
    assert modules.status_code == 200, modules.text
    body = modules.json()
    assert (body["business_profile"], body["profile_label"], body["locked"]) == (
        "electronics_wholesale",
        "Electronics",
        True,
    )
    assert body["enabled"] == [c.value for c in catalog.ORDER if c.value in trimmed]
    assert "trade_in" in body["available"] and "weighed_items" not in body["available"]
    assert body["support_email"] == "support@axizpos.com"
    assert client.get("/api/v1/tenant/modules", headers=device()).status_code == 200
    assert client.get("/api/v1/tenant/modules").status_code == 401


def test_only_business_wide_admins_change_the_profile(client) -> None:
    cashier = client.post("/api/v1/auth/login-pin", json={"username": "cashier", "pin": "1357"}, headers=device())
    token = cashier.json()["access_token"]
    denied = change_profile(client, {"Authorization": f"Bearer {token}"}, "cafe")
    assert denied.status_code == 403


def test_registers_still_sync_work_from_a_disabled_module(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    assert push(client, [event("labour-product", "product", labour_product())]).status_code == 200
    assert change_profile(client, headers, "cafe").status_code == 200

    ticket = repair(imeis(1, "35391805313")[0])
    response = push(client, [event("offline-repair", "repair_ticket", ticket)])
    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["status"] == "applied"
    note = session.scalar(select(AuditLog).where(AuditLog.action == "sync.capability_disabled"))
    assert note is not None
    assert note.details["modules"] == ["repairs"]
    assert str(note.target_entity_id) == ticket["id"]


def test_tenant_profile_names_the_business_type_and_its_modules(client) -> None:
    seed(client)
    headers, _ = admin(client)
    electronics = client.get("/api/v1/tenant/profile", headers=headers)
    assert electronics.status_code == 200, electronics.text
    assert electronics.json()["business_type"] == "electronics_wholesale"
    assert "serial_tracking" in electronics.json()["enabled_modules"]
    assert "kds" not in electronics.json()["enabled_modules"]

    assert change_profile(client, headers, "restaurant").status_code == 200
    restaurant = client.get("/api/v1/tenant/profile", headers=headers).json()
    assert restaurant["business_type"] == "restaurant"
    assert "kds" in restaurant["enabled_modules"]
    assert "serial_tracking" not in restaurant["enabled_modules"]
    assert "repairs" not in restaurant["enabled_modules"]


def test_provisioning_sets_the_preset_and_leaves_onboarding_to_the_admin(client, session) -> None:
    provision_profile(session, "quick_service")
    body = client.get("/api/v1/settings", headers=device()).json()
    assert body["business_profile"] == "quick_service"
    assert body["onboarded"] is False
    assert "delivery_channels" in body["capabilities"]
    assert body["planned_capabilities"] == []
