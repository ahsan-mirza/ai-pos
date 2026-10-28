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
from app.tenancy.models import ControlBase, SignupRequest, Subscription, Tenant

PASSWORD = "Owner-password-1"


def _create_all(url: str) -> None:
    engine = build_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()


@pytest.fixture()
def signup(tmp_path, monkeypatch):
    previous_database = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite:///{(tmp_path / 'shared.db').as_posix()}"
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
    if previous_database is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous_database
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


def _allow_go_live(slug: str) -> None:
    """Marks the trial subscription paid. Direct Go live stays refused until this happens."""
    from datetime import UTC, datetime, timedelta

    with registry.control_session(get_settings()) as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == slug))
        assert tenant is not None
        row = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id))
        assert row is not None
        row.status = "active"
        row.current_period_end = datetime.now(UTC) + timedelta(days=30)
        db.commit()


def _store(slug: str = "alnoor") -> dict:
    return {"store_name": "Al Noor Mobiles", "slug": slug, "currency": "AED", "country": "AE", "trn": None}


def _tenant_headers(slug: str, token: str | None = None) -> dict[str, str]:
    headers = {"X-Tenant-Domain": f"{slug}.axizpos.com"}
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

    headers = _tenant_headers("alnoor", token)
    checklist = signup.get("/api/v1/onboarding/checklist", headers=headers).json()
    assert checklist["store_name"] == "Al Noor Mobiles"
    by_key = {item["key"]: item for item in checklist["items"]}
    assert by_key["catalogue"]["done"] is False
    assert by_key["explore"]["done"] is False
    assert by_key["configure"]["done"] is True
    assert checklist["subscription_state"] == "trial"
    assert by_key["activate"]["blocked"]
    blocked = signup.post(
        "/api/v1/onboarding/go-live",
        headers=headers,
        json={"confirm": "al noor mobiles", "mode": "keep", "opening_stock": "keep", "tax_acknowledged": True},
    )
    assert (blocked.status_code, blocked.json()["error"]["code"]) == (409, "subscription_unverified")
    explored = signup.post("/api/v1/onboarding/explore", headers=headers).json()
    assert next(item for item in explored["items"] if item["key"] == "explore")["done"] is True
    again = signup.post("/api/v1/onboarding/explore", headers=headers).json()
    assert next(item for item in again["items"] if item["key"] == "explore")["done"] is True
    refused_skip = signup.post("/api/v1/onboarding/skip", headers=headers, json={"key": "activate"})
    assert (refused_skip.status_code, refused_skip.json()["error"]["code"]) == (422, "invalid_step")
    skipped = signup.post("/api/v1/onboarding/skip", headers=headers, json={"key": "invite"}).json()
    team = next(item for item in skipped["items"] if item["key"] == "team")
    assert team["skipped"] is True and team["done"] is False
    kept = signup.get("/api/v1/onboarding/checklist", headers=headers).json()
    assert next(item for item in kept["items"] if item["key"] == "team")["skipped"] is True
    _allow_go_live("alnoor")

    login = signup.post(
        "/api/v1/auth/login-password",
        headers=_tenant_headers("alnoor"),
        json={"username": "sara", "password": PASSWORD},
    )
    assert login.status_code == 200, login.text

    live = signup.post(
        "/api/v1/onboarding/go-live",
        headers=_tenant_headers("alnoor", token),
        json={"confirm": "al noor mobiles", "mode": "keep", "opening_stock": "keep", "tax_acknowledged": True},
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
    monkeypatch.setattr(signup_service, "_code_seconds", lambda _settings: 0)
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
    settings = get_settings()
    previous = settings.signup_max_per_hour
    settings.signup_max_per_hour = 0
    try:
        blocked = signup.post(
            "/api/v1/signup/start",
            json={"email": "rate@alnoor.ae", "phone": "+971 50 000 1888", "full_name": "Sara", "password": PASSWORD},
        )
        assert (blocked.status_code, blocked.json()["error"]["code"]) == (429, "too_many_signups")
    finally:
        settings.signup_max_per_hour = previous


def test_the_same_email_or_phone_resumes_the_saved_signup(signup: TestClient) -> None:
    started = _verified(signup)
    chosen = _post(signup, started, "business", {"profile": "electronics_wholesale", "sub_type": "electronics_both"})
    assert chosen.status_code == 200, chosen.text

    duplicate = signup.post(
        "/api/v1/signup/start",
        json={
            "email": "sara@alnoor.ae",
            "phone": "+971 50 123 4567",
            "full_name": "Sara Al Noor",
            "password": PASSWORD,
        },
    )
    assert (duplicate.status_code, duplicate.json()["error"]["code"]) == (409, "signup_exists")
    same_phone = signup.post(
        "/api/v1/signup/start",
        json={"email": "other@alnoor.ae", "phone": "+971501234567", "full_name": "Sara", "password": PASSWORD},
    )
    assert same_phone.json()["error"]["code"] == "signup_exists"

    wrong = signup.post("/api/v1/signup/resume", json={"email": "sara@alnoor.ae", "password": "Wrong-password-1"})
    assert (wrong.status_code, wrong.json()["error"]["code"]) == (401, "signup_login_failed")

    resumed = signup.post("/api/v1/signup/resume", json={"email": "Sara@AlNoor.ae", "password": PASSWORD})
    assert resumed.status_code == 200, resumed.text
    body = resumed.json()
    assert body["id"] == started["id"]
    stale = signup.get(
        f"/api/v1/signup/{started['id']}/status", headers={"X-Signup-Token": started["token"]}
    )
    assert stale.status_code == 404
    current = signup.get(f"/api/v1/signup/{body['id']}/status", headers={"X-Signup-Token": body["token"]})
    assert current.status_code == 200, current.text
    assert current.json()["status"] == "VERIFIED"
    assert current.json()["sub_type"] == "electronics_both"
    with registry.control_session(get_settings()) as db:
        assert len(db.scalars(select(SignupRequest).where(SignupRequest.email == "sara@alnoor.ae")).all()) == 1


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
    unknown = _post(signup, started, "store", {**_store("gamma"), "country": "ZZ"})
    assert unknown.status_code == 422 and unknown.json()["error"]["code"] == "unsupported_country"
    country = _post(signup, started, "store", {**_store("beta"), "country": "US", "currency": "AED"})
    assert country.status_code == 200, country.text
    with registry.control_session(get_settings()) as db:
        saved = db.scalar(select(SignupRequest).where(SignupRequest.slug == "beta"))
        assert saved is not None and saved.country == "US" and saved.currency == "USD"


@pytest.mark.parametrize(
    ("sub_type", "slug"),
    [
        ("grocery_shop", "gshop"),
        ("grocery_supermarket", "gsuper"),
        ("grocery_cash_carry", "gcarry"),
    ],
)
def test_grocery_sub_types_provision_their_kits(signup: TestClient, sub_type: str, slug: str) -> None:
    from app.core import capabilities as catalog

    token, _state = _food_store(signup, slug, "grocery", sub_type)
    settings = signup.get("/api/v1/settings", headers=_tenant_headers(slug, token)).json()
    assert set(settings["capabilities"]) == {item.value for item in catalog.SUB_TYPES["grocery"][sub_type]}


def test_grocery_shop_practice_stock_is_weighed_and_the_milk_expires(signup: TestClient) -> None:
    token, _state = _food_store(signup, "gpractice", "grocery", "grocery_shop")
    headers = _tenant_headers("gpractice", token)
    products = signup.get("/api/v1/products", headers=headers, params={"limit": 200}).json()
    by_sku = {row["sku"]: row for row in products}
    bananas = by_sku["SAMPLE-BANANA-1KG"]
    tomatoes = by_sku["SAMPLE-TOMATO-1KG"]
    assert (bananas["sold_by_weight"], bananas["plu_code"], bananas["tare_grams"], bananas["stock_quantity"]) == (
        True,
        "900001",
        0,
        20000,
    )
    assert (tomatoes["sold_by_weight"], tomatoes["plu_code"], tomatoes["tare_grams"], tomatoes["stock_quantity"]) == (
        True,
        "900002",
        20,
        15000,
    )
    expiring = signup.get("/api/v1/inventory/expiring", headers=headers).json()
    milk = next(row for row in expiring if row["sku"] == "SAMPLE-MILK-1L")
    assert milk["quantity_remaining"] == 48 and 0 <= milk["days_left"] <= 7
    keys = signup.get("/api/v1/settings", headers=headers).json()["module_settings"]["department_keys"]["keys"]
    assert [key["label"] for key in keys] == ["Produce", "Dairy", "Bakery", "Pantry"]


def test_unknown_grocery_sub_type_is_rejected(signup: TestClient) -> None:
    started = _verified(signup)
    unknown = _post(signup, started, "business", {"profile": "grocery", "sub_type": "kiosk"})
    assert unknown.json()["error"]["code"] == "unknown_sub_type"


def test_a_profile_missing_from_sub_types_still_joins_the_waitlist(signup: TestClient, monkeypatch) -> None:
    from app.core import capabilities as catalog

    without_grocery = {key: value for key, value in catalog.SUB_TYPES.items() if key != "grocery"}
    monkeypatch.setattr(catalog, "SUB_TYPES", without_grocery)
    started = _verified(signup)
    waiting = _post(signup, started, "business", {"profile": "grocery", "sub_type": None})
    assert waiting.json()["status"] == "WAITLIST"
    blocked = _post(signup, started, "store", _store("waitlist"))
    assert (blocked.status_code, blocked.json()["error"]["code"]) == (409, "wrong_step")


def _mobile(seed: str) -> str:
    """A valid UAE mobile. Slug length must not change the digit count."""
    number = sum((index + 1) * ord(char) for index, char in enumerate(seed)) % 10_000_000
    return f"+97150{number:07d}"


def _food_store(signup: TestClient, slug: str, profile: str, sub_type: str) -> tuple[str, dict]:
    started = _verified(signup, email=f"owner@{slug}.ae", phone=_mobile(slug))
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
    assert next(item for item in checklist["items"] if item["key"] == "catalogue")["label"] == (
        "Add your first menu items"
    )
    _allow_go_live("grill")
    live = signup.post(
        "/api/v1/onboarding/go-live",
        headers=headers,
        json={"confirm": "Grill", "mode": "keep", "opening_stock": "keep", "tax_acknowledged": True},
    )
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


def test_development_emails_a_fresh_code_and_accepts_the_optional_code(signup: TestClient, monkeypatch) -> None:
    settings = get_settings()
    previous = (settings.app_env, settings.signup_otp_code, settings.signup_otp_channel)
    settings.app_env = "development"
    settings.signup_otp_code = "742466"
    settings.signup_otp_channel = "email"
    sent: list[str] = []

    def capture(_settings, provider: str, message) -> str:
        assert provider == "smtp"
        sent.append(message.body)
        return "sent"

    monkeypatch.setattr(signup_service.messaging_providers, "deliver", capture)
    try:
        started = _start(signup, email="mail@alnoor.ae", phone="+971 50 000 0002")
        assert started["channel"] == "email" and started["dev_code"] is None
        assert started["expires_in_seconds"] == settings.signup_otp_minutes * 60
        assert started["resend_after_seconds"] == started["expires_in_seconds"]
        assert sent and "742466" not in sent[0]
        emailed = sent[0].split("is ", 1)[1][:6]
        assert _post(signup, started, "verify", {"code": "742466"}).json()["status"] == "VERIFIED"

        again = _start(signup, email="mail2@alnoor.ae", phone="+971 50 000 0003")
        assert _post(signup, again, "verify", {"code": emailed}).status_code == 422
        fresh = sent[-1].split("is ", 1)[1][:6]
        assert _post(signup, again, "verify", {"code": fresh}).json()["status"] == "VERIFIED"
    finally:
        settings.app_env, settings.signup_otp_code, settings.signup_otp_channel = previous


def test_a_configured_signup_code_is_accepted_without_sending(signup: TestClient, monkeypatch) -> None:
    settings = get_settings()
    previous = settings.signup_otp_code
    settings.signup_otp_code = "101010"

    def refuse(*_args, **_kwargs) -> str:
        raise AssertionError("a fixed signup code is not sent")

    monkeypatch.setattr(signup_service.messaging_providers, "deliver", refuse)
    try:
        started = _start(signup, email="fixed@alnoor.ae", phone="+971 50 000 0001")
        assert started["dev_code"] == "101010"
        assert _post(signup, started, "verify", {"code": "101010"}).json()["status"] == "VERIFIED"
    finally:
        settings.signup_otp_code = previous


def test_signup_country_sets_the_store_currency() -> None:
    import re
    from pathlib import Path

    from app.tenancy.countries import COUNTRY_CURRENCIES, currency_for_country

    source = (Path(__file__).resolve().parents[3] / "packages" / "shared-types" / "src" / "countries.ts").read_text(
        encoding="utf-8"
    )
    block = source.split("export const COUNTRY_CURRENCIES", 1)[1].split("} as const", 1)[0]
    found = dict(re.findall(r'([A-Z]{2}): "([A-Z]{3})"', block))
    assert found == COUNTRY_CURRENCIES
    assert currency_for_country("AE") == "AED"
    assert currency_for_country("SA") == "SAR"
    assert currency_for_country("FR") == "EUR"
    assert currency_for_country("GB") == "GBP"
    assert currency_for_country("IN") == "INR"
    assert currency_for_country("PK") == "PKR"
    assert currency_for_country("CN") == "CNY"
    assert currency_for_country("KW") == "KWD"
    assert currency_for_country("US") == "USD"
    assert currency_for_country("JP") == "USD"
    assert currency_for_country("ZZ") == "USD"
