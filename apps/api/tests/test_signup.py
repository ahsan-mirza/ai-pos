"""Self-service signup on the bare domain: one-time code, business type, store address, provisioning and handoff."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import build_engine
from app.main import create_app
from app.models import Base
from app.tenancy import provisioning, registry, signup_service
from app.tenancy.models import ControlBase, SignupRequest, Tenant

PASSWORD = "owner-password-1"


def _create_all(url: str) -> None:
    engine = build_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()


@pytest.fixture()
def signup(tmp_path, monkeypatch):
    os.environ["CONTROL_DATABASE_URL"] = f"sqlite:///{(tmp_path / 'control.db').as_posix()}"
    os.environ["TENANT_DATABASE_URL_TEMPLATE"] = f"sqlite:///{tmp_path.as_posix()}/{{database}}.db"
    os.environ["SIGNUP_MAX_PER_HOUR"] = "3"
    get_settings.cache_clear()
    registry.invalidate()
    registry._control_factory.cache_clear()
    engine = build_engine(os.environ["CONTROL_DATABASE_URL"])
    ControlBase.metadata.create_all(engine)
    engine.dispose()
    monkeypatch.setattr(provisioning, "migrate", _create_all)
    yield TestClient(create_app())
    for name in ("CONTROL_DATABASE_URL", "TENANT_DATABASE_URL_TEMPLATE", "SIGNUP_MAX_PER_HOUR"):
        del os.environ[name]
    get_settings.cache_clear()
    registry.invalidate()
    registry._control_factory.cache_clear()


def _start(client: TestClient, email: str = "sara@alnoor.ae", phone: str = "+971 50 123 4567") -> dict:
    response = client.post(
        "/api/v1/signup/start",
        json={"email": email, "phone": phone, "full_name": "Sara Al Noor", "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _post(client: TestClient, started: dict, path: str, body: dict | None = None):
    return client.post(
        f"/api/v1/signup/{started['id']}/{path}", headers={"X-Signup-Token": started["token"]}, json=body
    )


def _status(client: TestClient, started: dict) -> dict:
    response = client.get(f"/api/v1/signup/{started['id']}/status", headers={"X-Signup-Token": started["token"]})
    assert response.status_code == 200, response.text
    return response.json()


def _verified(client: TestClient, **start) -> dict:
    started = _start(client, **start)
    assert _post(client, started, "verify", {"code": started["dev_code"]}).json()["status"] == "VERIFIED"
    return started


def _store(slug: str = "alnoor") -> dict:
    return {"store_name": "Al Noor Mobiles", "slug": slug, "currency": "AED", "country": "AE", "trn": None}


def _tenant_headers(slug: str, token: str | None = None) -> dict[str, str]:
    headers = {"X-Tenant-Domain": f"{slug}.qios.ae"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def test_signup_provisions_a_practice_store_and_hands_the_owner_over(signup: TestClient) -> None:
    started = _start(signup)
    assert started["channel"] == "log" and len(started["dev_code"]) == 6
    assert started["sent_to"].startswith("+971") and "123" not in started["sent_to"][4:-3]

    wrong = _post(signup, started, "verify", {"code": "000000" if started["dev_code"] != "000000" else "111111"})
    assert (wrong.status_code, wrong.json()["error"]["code"]) == (422, "wrong_code")
    assert "4 attempts left" in wrong.json()["error"]["message"]
    assert _post(signup, started, "verify", {"code": started["dev_code"]}).json()["status"] == "VERIFIED"

    chosen = _post(signup, started, "business", {"profile": "electronics_wholesale", "sub_type": "electronics_retail"})
    assert chosen.json()["sub_type"] == "electronics_retail"
    assert signup.get("/api/v1/signup/slug-check", params={"slug": "alnoor"}).json()["available"] is True

    queued = _post(signup, started, "store", _store())
    assert queued.status_code == 200, queued.text
    assert queued.json()["status"] == "PROVISIONING"

    state = _status(signup, started)
    assert state["status"] == "READY", state
    assert [step["state"] for step in state["steps"]] == ["done"] * 7
    assert state["owner_username"] == "sara" and state["handoff_token"]
    assert signup.get("/api/v1/signup/slug-check", params={"slug": "alnoor"}).json()["available"] is False

    elsewhere = signup.post(
        "/api/v1/auth/handoff", headers=_tenant_headers("other"), json={"token": state["handoff_token"]}
    )
    assert elsewhere.status_code == 404

    handed = signup.post(
        "/api/v1/auth/handoff", headers=_tenant_headers("alnoor"), json={"token": state["handoff_token"]}
    )
    assert handed.status_code == 200, handed.text
    token = handed.json()["access_token"]
    assert handed.json()["user"]["username"] == "sara"
    again = signup.post(
        "/api/v1/auth/handoff", headers=_tenant_headers("alnoor"), json={"token": state["handoff_token"]}
    )
    assert (again.status_code, again.json()["error"]["code"]) == (401, "invalid_handoff")
    assert _status(signup, started)["handoff_token"] is None

    settings = signup.get("/api/v1/settings", headers=_tenant_headers("alnoor", token)).json()
    assert settings["practice_mode"] is True and settings["onboarded"] is True
    assert settings["currency"] == "AED" and settings["business_profile"] == "electronics_wholesale"
    assert "repairs" in settings["capabilities"] and "wholesale_pricing" not in settings["capabilities"]

    checklist = signup.get("/api/v1/onboarding/checklist", headers=_tenant_headers("alnoor", token)).json()
    assert checklist["store_name"] == "Al Noor Mobiles"
    assert {item["key"]: item["done"] for item in checklist["items"]}["real_product"] is False

    login = signup.post(
        "/api/v1/auth/login-password",
        headers=_tenant_headers("alnoor"),
        json={"username": "sara", "password": PASSWORD},
    )
    assert login.status_code == 200, login.text

    live = signup.post(
        "/api/v1/onboarding/go-live", headers=_tenant_headers("alnoor", token), json={"confirm": "al noor mobiles"}
    )
    assert live.status_code == 200, live.text
    assert live.json()["sample_products_removed"] == 6 and live.json()["sample_customers_removed"] == 2


def test_handoff_tokens_only_open_their_own_store(signup: TestClient, tmp_path) -> None:
    for slug in ("alnoor", "bravo"):
        started = _verified(signup, email=f"owner@{slug}.ae", phone=f"+97150{len(slug)}000000")
        _post(signup, started, "business", {"profile": "retail_fashion", "sub_type": "fashion_boutique"})
        assert _post(signup, started, "store", _store(slug)).status_code == 200
        if slug == "alnoor":
            token = _status(signup, started)["handoff_token"]
    refused = signup.post("/api/v1/auth/handoff", headers=_tenant_headers("bravo"), json={"token": token})
    assert (refused.status_code, refused.json()["error"]["code"]) == (401, "invalid_handoff")
    assert "another store" in refused.json()["error"]["message"]
    assert (
        signup.post("/api/v1/auth/handoff", headers=_tenant_headers("alnoor"), json={"token": token}).status_code == 200
    )


def test_wrong_codes_lock_the_attempt_until_a_new_code_is_sent(signup: TestClient, monkeypatch) -> None:
    started = _start(signup)
    wrong = "000000" if started["dev_code"] != "000000" else "111111"
    for _ in range(signup_service.MAX_OTP_ATTEMPTS):
        assert _post(signup, started, "verify", {"code": wrong}).status_code == 422
    locked = _post(signup, started, "verify", {"code": started["dev_code"]})
    assert (locked.status_code, locked.json()["error"]["code"]) == (429, "too_many_attempts")

    too_soon = _post(signup, started, "resend")
    assert (too_soon.status_code, too_soon.json()["error"]["code"]) == (429, "resend_too_soon")
    monkeypatch.setattr(signup_service, "RESEND_SECONDS", 0)
    fresh = _post(signup, started, "resend")
    assert fresh.status_code == 200, fresh.text
    assert _post(signup, started, "verify", {"code": fresh.json()["dev_code"]}).json()["status"] == "VERIFIED"


def test_every_step_needs_the_signup_token(signup: TestClient) -> None:
    started = _start(signup)
    anonymous = signup.get(f"/api/v1/signup/{started['id']}/status")
    assert anonymous.status_code == 404
    forged = signup.get(f"/api/v1/signup/{started['id']}/status", headers={"X-Signup-Token": "not-the-token"})
    assert forged.status_code == 404
    early = _post(signup, started, "business", {"profile": "electronics_wholesale", "sub_type": "electronics_retail"})
    assert (early.status_code, early.json()["error"]["code"]) == (409, "wrong_step")


def test_signups_are_rate_limited_per_email_or_phone(signup: TestClient) -> None:
    for _ in range(3):
        _start(signup)
    blocked = signup.post(
        "/api/v1/signup/start",
        json={"email": "other@alnoor.ae", "phone": "+971501234567", "full_name": "Sara", "password": PASSWORD},
    )
    assert (blocked.status_code, blocked.json()["error"]["code"]) == (429, "too_many_signups")


def test_store_addresses_must_be_valid_and_free(signup: TestClient) -> None:
    reserved = signup.get("/api/v1/signup/slug-check", params={"slug": "www"}).json()
    assert reserved["available"] is False and "reserved" in reserved["reason"]
    with registry.control_session(get_settings()) as db:
        db.add(Tenant(slug="alpha", name="Alpha", status="active", database_url_encrypted="x"))
        db.commit()
    taken = signup.get("/api/v1/signup/slug-check", params={"slug": "Alpha"}).json()
    assert taken == {"slug": "alpha", "available": False, "reason": "That address is taken.", "suggestion": "alpha-2"}

    started = _verified(signup)
    _post(signup, started, "business", {"profile": "electronics_wholesale", "sub_type": "electronics_b2b"})
    clash = _post(signup, started, "store", _store("alpha"))
    assert (clash.status_code, clash.json()["error"]["code"]) == (409, "slug_unavailable")
    country = _post(signup, started, "store", {**_store("beta"), "country": "US"})
    assert country.json()["error"]["code"] == "unsupported_country"


def test_coming_soon_business_types_join_the_waitlist(signup: TestClient) -> None:
    started = _verified(signup)
    waiting = _post(signup, started, "business", {"profile": "grocery", "sub_type": None})
    assert waiting.json()["status"] == "WAITLIST"
    blocked = _post(signup, started, "store", _store())
    assert (blocked.status_code, blocked.json()["error"]["code"]) == (409, "wrong_step")
    back = _post(signup, started, "business", {"profile": "retail_fashion", "sub_type": "fashion_chain"})
    assert back.json()["status"] == "VERIFIED"
    unknown = _post(signup, started, "business", {"profile": "retail_fashion", "sub_type": "kiosk"})
    assert unknown.json()["error"]["code"] == "unknown_sub_type"


def _food_store(signup: TestClient, slug: str, profile: str, sub_type: str) -> tuple[str, dict]:
    started = _verified(signup, email=f"owner@{slug}.ae", phone=f"+97150{len(slug)}111111")
    chosen = _post(signup, started, "business", {"profile": profile, "sub_type": sub_type})
    assert chosen.json()["status"] == "VERIFIED", chosen.text
    assert _post(signup, started, "store", {**_store(slug), "store_name": slug.title()}).status_code == 200
    state = _status(signup, started)
    assert state["status"] == "READY", state
    handed = signup.post("/api/v1/auth/handoff", headers=_tenant_headers(slug), json={"token": state["handoff_token"]})
    assert handed.status_code == 200, handed.text
    return handed.json()["access_token"], state


def test_restaurants_start_with_a_menu_meals_tables_and_a_kitchen(signup: TestClient) -> None:
    token, state = _food_store(signup, "grill", "restaurant", "full_service")
    samples_step = next(step["label"] for step in state["steps"] if step["key"] == "samples")
    assert "menu, meals, tables and kitchen" in samples_step
    headers = _tenant_headers("grill", token)
    settings = signup.get("/api/v1/settings", headers=headers).json()
    assert {"tables", "open_orders", "kds", "menu_modifiers", "split_bills"} <= set(settings["capabilities"])
    store_id = signup.get("/api/v1/stores", headers=headers).json()[0]["id"]

    floor = signup.get("/api/v1/dining/floor", headers=headers, params={"store_id": store_id}).json()
    assert [(area["name"], len(area["tables"])) for area in floor["areas"]] == [("Main hall", 8), ("Terrace", 4)]
    stations = signup.get("/api/v1/kds/stations", headers=headers, params={"store_id": store_id}).json()
    assert sorted(station["name"] for station in stations) == ["Bar", "Kitchen"]
    menu = signup.get("/api/v1/menu/register", headers=headers).json()
    assert sorted(group["name"] for group in menu["groups"]) == ["Add-ons", "Cooking", "Juice"]
    meals = signup.get("/api/v1/menu/combos", headers=headers).json()
    assert sorted(meal["name"] for meal in meals) == ["Burger Meal", "Business Lunch"]

    # A practice order of a Burger Meal: the burger goes to the kitchen, the drink to the bar.
    meal = next(meal for meal in meals if meal["name"] == "Burger Meal")
    picks = [
        {"slot_id": slot["id"], "product_id": next(o for o in slot["options"] if o["is_default"])["product_id"]}
        for slot in meal["slots"]
    ]
    table = floor["areas"][0]["tables"][2]
    order = signup.post(
        "/api/v1/orders",
        headers=headers,
        json={
            "id": "00000000-0000-4000-8000-0000000000f1",
            "store_id": store_id,
            "table_id": table["id"],
            "covers": 2,
            "items": [
                {
                    "id": "00000000-0000-4000-8000-0000000000f2",
                    "product_id": meal["product_id"],
                    "quantity": 1,
                    "unit_price_cents": meal["price_cents"],
                    "components": picks,
                }
            ],
        },
    )
    assert order.status_code == 201, order.text
    sent = signup.post(f"/api/v1/orders/{order.json()['id']}/send", headers=headers, json={"revision": 1})
    assert sent.status_code == 200, sent.text
    for station in stations:
        tickets = signup.get(f"/api/v1/kds/stations/{station['id']}/tickets", headers=headers).json()["tickets"]
        names = [item["product_name"] for ticket in tickets for item in ticket["items"]]
        assert names == (["Soft drink"] if station["name"] == "Bar" else ["Classic beef burger", "French fries"])

    checklist = signup.get("/api/v1/onboarding/checklist", headers=headers).json()
    assert next(item for item in checklist["items"] if item["key"] == "real_product")["label"] == (
        "Add your first real menu item"
    )
    live = signup.post("/api/v1/onboarding/go-live", headers=headers, json={"confirm": "Grill"})
    assert live.status_code == 200, live.text
    assert live.json()["sample_products_removed"] == 19 + 2 + 6
    assert signup.get("/api/v1/menu/combos", headers=headers).json() == []
    assert signup.get("/api/v1/menu/register", headers=headers).json()["groups"] == []
    assert signup.get("/api/v1/orders", headers=headers, params={"store_id": store_id}).json() == []
    kept = signup.get("/api/v1/dining/floor", headers=headers, params={"store_id": store_id}).json()
    assert sum(len(area["tables"]) for area in kept["areas"]) == 12
    assert len(signup.get("/api/v1/kds/stations", headers=headers, params={"store_id": store_id}).json()) == 2


@pytest.mark.parametrize(
    "profile,sub_type,tables",
    [("cafe", "counter_cafe", 0), ("cafe", "sit_down_cafe", 6), ("quick_service", "qsr_counter", 0)],
)
def test_counter_service_kits_skip_the_floor_plan(signup: TestClient, profile: str, sub_type: str, tables: int) -> None:
    slug = sub_type.replace("_", "")
    token, _ = _food_store(signup, slug, profile, sub_type)
    headers = _tenant_headers(slug, token)
    store_id = signup.get("/api/v1/stores", headers=headers).json()[0]["id"]
    floor = signup.get("/api/v1/dining/floor", headers=headers, params={"store_id": store_id})
    seated = sum(len(area["tables"]) for area in floor.json()["areas"]) if floor.status_code == 200 else 0
    assert seated == tables
    assert len(signup.get("/api/v1/menu/combos", headers=headers).json()) >= 2
    assert len(signup.get("/api/v1/kds/stations", headers=headers, params={"store_id": store_id}).json()) == 2


def test_a_failed_step_can_be_retried(signup: TestClient, monkeypatch) -> None:
    started = _verified(signup)
    _post(signup, started, "business", {"profile": "electronics_wholesale", "sub_type": "electronics_retail"})

    def broken(job) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setitem(provisioning.STEP_FUNCTIONS, "samples", broken)
    _post(signup, started, "store", _store())
    failed = _status(signup, started)
    assert failed["status"] == "FAILED" and failed["error"] == "samples: disk full"
    assert [step["state"] for step in failed["steps"]][-2:] == ["failed", "pending"]

    monkeypatch.setitem(provisioning.STEP_FUNCTIONS, "samples", provisioning.step_samples)
    assert _post(signup, started, "retry").status_code == 200
    assert _status(signup, started)["status"] == "READY"
    with registry.control_session(get_settings()) as db:
        assert len(db.scalars(select(Tenant).where(Tenant.slug == "alnoor")).all()) == 1
        assert db.scalar(select(SignupRequest.tenant_id)) is not None
