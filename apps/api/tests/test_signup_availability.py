"""Advisory availability checks. PostgreSQL stays authoritative; the Bloom filter only skips a proven miss."""

import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import build_engine
from app.core.errors import ApiError
from app.main import create_app
from app.models import Base
from app.schemas.signup import SignupStart
from app.services import availability, bloom_filter
from app.tenancy import provisioning, registry, signup_service
from app.tenancy.models import ControlBase, SignupRequest, SignupSlugHold

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
    availability.reset_stats()
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


def _start(client: TestClient, email: str = "sara@alnoor.ae", phone: str = "+971501234567") -> dict:
    response = client.post(
        "/api/v1/signup/start",
        json={"email": email, "phone": phone, "full_name": "Unique Person", "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _verified(client: TestClient, email: str, phone: str) -> dict:
    started = _start(client, email, phone)
    verified = client.post(
        f"/api/v1/signup/{started['id']}/verify",
        headers={"X-Signup-Token": started["token"]},
        json={"code": started["dev_code"]},
    )
    assert verified.json()["status"] == "VERIFIED", verified.text
    return started


def _business(client: TestClient, started: dict) -> None:
    chosen = client.post(
        f"/api/v1/signup/{started['id']}/business",
        headers={"X-Signup-Token": started["token"]},
        json={"profile": "electronics_wholesale", "sub_type": "electronics_retail"},
    )
    assert chosen.status_code == 200, chosen.text


def test_email_and_phone_availability_follow_signup_normalization(signup: TestClient, monkeypatch) -> None:
    sent: list[str] = []

    def capture(*_args, **_kwargs) -> str:
        sent.append("sent")
        return "sent"

    monkeypatch.setattr(signup_service.messaging_providers, "deliver", capture)
    _start(signup)
    sent.clear()
    email = signup.post("/api/v1/signup/availability/email", json={"email": " Sara@AlNoor.ae "})
    phone = signup.post("/api/v1/signup/availability/phone", json={"phone": "0501234567"})
    fresh = signup.post("/api/v1/signup/availability/email", json={"email": "other@alnoor.ae"})
    assert email.status_code == 200, email.text
    assert email.json() == {"available": False, "code": "taken"}
    assert phone.json() == {"available": False, "code": "taken"}
    assert fresh.json() == {"available": True, "code": "available"}
    assert "Unique Person" not in email.text
    assert "sara@" not in email.text
    assert sent == []


def test_invalid_identifiers_are_rejected_before_a_lookup(signup: TestClient) -> None:
    email = signup.post("/api/v1/signup/availability/email", json={"email": "not-an-email"})
    phone = signup.post("/api/v1/signup/availability/phone", json={"phone": "123"})
    assert email.status_code == 422 and email.json()["error"]["code"] == "invalid_request"
    assert phone.status_code == 422 and phone.json()["error"]["code"] == "invalid_request"


def test_availability_is_rate_limited_without_confirming_an_account(signup: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(availability, "RATE_LIMIT", 2)
    assert signup.post("/api/v1/signup/availability/email", json={"email": "one@alnoor.ae"}).status_code == 200
    assert signup.post("/api/v1/signup/availability/phone", json={"phone": "+971501110000"}).status_code == 200
    blocked = signup.post("/api/v1/signup/availability/email", json={"email": "two@alnoor.ae"})
    assert (blocked.status_code, blocked.json()["error"]["code"]) == (429, "rate_limited")


def test_a_bloom_miss_skips_the_existence_query(signup: TestClient, monkeypatch) -> None:
    assert bloom_filter.rebuild("email", [])
    availability.reset_stats()

    def boom(_db, _email: str) -> bool:
        raise AssertionError("the existence query ran")

    monkeypatch.setattr(availability, "email_is_taken", boom)
    result = signup.post("/api/v1/signup/availability/email", json={"email": "new@alnoor.ae"})
    assert result.json() == {"available": True, "code": "available"}
    assert availability.stats["db"] == 0
    assert availability.stats["absent"] == 1


def test_a_bloom_hit_is_confirmed_and_never_taken_on_its_own(signup: TestClient) -> None:
    assert bloom_filter.rebuild("email", ["ghost@alnoor.ae"])
    availability.reset_stats()
    ghost = signup.post("/api/v1/signup/availability/email", json={"email": "ghost@alnoor.ae"})
    assert ghost.json() == {"available": True, "code": "available"}
    assert availability.stats["db"] == 1

    _start(signup, email="real@alnoor.ae", phone="+971501234000")
    taken = signup.post("/api/v1/signup/availability/email", json={"email": "real@alnoor.ae"})
    assert taken.json()["available"] is False
    assert availability.stats["db"] >= 2


def test_a_stale_or_unreachable_filter_uses_the_database(signup: TestClient, monkeypatch) -> None:
    _start(signup, email="kept@alnoor.ae", phone="+971501234001")
    bloom_filter.mark_stale("email")
    availability.reset_stats()
    stale = signup.post("/api/v1/signup/availability/email", json={"email": "kept@alnoor.ae"})
    assert stale.json()["available"] is False
    assert availability.stats["db"] >= 1

    monkeypatch.setattr("app.services.bloom_filter.cache.reachable", lambda: False)
    monkeypatch.setattr("app.services.bloom_filter.cache.get_value", lambda _key: None)
    availability.reset_stats()
    down = signup.post("/api/v1/signup/availability/email", json={"email": "kept@alnoor.ae"})
    free = signup.post("/api/v1/signup/availability/email", json={"email": "free@alnoor.ae"})
    assert down.json()["available"] is False
    assert free.json()["available"] is True
    assert availability.stats["absent"] == 0
    assert availability.stats["db"] == 2


def test_an_oversized_filter_does_not_answer_by_itself(signup: TestClient) -> None:
    _start(signup, email="full@alnoor.ae", phone="+971501234002")
    bloom_filter.mark_over("email")
    availability.reset_stats()
    result = signup.post("/api/v1/signup/availability/email", json={"email": "full@alnoor.ae"})
    assert result.json()["available"] is False
    assert availability.stats["absent"] == 0
    assert availability.stats["db"] == 1


def test_registration_adds_the_identifier_to_a_healthy_filter(signup: TestClient) -> None:
    assert bloom_filter.rebuild("email", [])
    assert bloom_filter.rebuild("phone", [])
    _start(signup, email="added@alnoor.ae", phone="+971501234003")
    assert bloom_filter.probe("email", "added@alnoor.ae") == "possible"
    assert bloom_filter.probe("phone", "+971501234003") == "possible"


def test_unique_constraints_report_the_field_when_the_precheck_misses(signup: TestClient, monkeypatch) -> None:
    _start(signup)
    monkeypatch.setattr(signup_service, "_existing", lambda *_args, **_kwargs: None)
    duplicate = signup.post(
        "/api/v1/signup/start",
        json={"email": "sara@alnoor.ae", "phone": "+971509990000", "full_name": "Other", "password": PASSWORD},
    )
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["error"]["code"] == "signup_exists"
    assert duplicate.json()["error"]["details"]["fields"]["email"] == "This email is already registered."
    same_phone = signup.post(
        "/api/v1/signup/start",
        json={"email": "second@alnoor.ae", "phone": "+971501234567", "full_name": "Other", "password": PASSWORD},
    )
    assert same_phone.json()["error"]["details"]["fields"]["phone"] == "This mobile number is already registered."


def test_concurrent_signups_cannot_create_two_rows(signup: TestClient) -> None:
    gate = threading.Barrier(2)

    def attempt() -> str:
        gate.wait(timeout=5)
        try:
            signup_service.start(
                get_settings(),
                SignupStart(
                    email="race@alnoor.ae",
                    phone="+971501111111",
                    full_name="Race User",
                    password=PASSWORD,
                ),
            )
        except ApiError as exc:
            return exc.code
        return "ok"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: attempt(), (0, 1)))
    assert results.count("ok") == 1
    assert results.count("signup_exists") == 1
    with registry.control_session(get_settings()) as db:
        rows = list(db.scalars(select(SignupRequest).where(SignupRequest.email == "race@alnoor.ae")))
    assert len(rows) == 1


def test_store_names_can_be_shared_and_addresses_cannot(signup: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(provisioning, "provision", lambda *_args, **_kwargs: None)
    first = _verified(signup, "one@alnoor.ae", "+971501234010")
    second = _verified(signup, "two@alnoor.ae", "+971501234011")
    _business(signup, first)
    _business(signup, second)
    headers = {"X-Signup-Token": first["token"]}
    named = signup.post(
        f"/api/v1/signup/{first['id']}/store",
        headers=headers,
        json={"store_name": "  Al   Noor  ", "slug": "alnoor", "currency": "AED", "country": "AE", "trn": None},
    )
    assert named.status_code == 200, named.text
    assert named.json()["store_name"] == "Al Noor"
    short = signup.post(
        f"/api/v1/signup/{second['id']}/store",
        headers={"X-Signup-Token": second["token"]},
        json={"store_name": " A ", "slug": "other", "currency": "AED", "country": "AE", "trn": None},
    )
    assert short.status_code == 422
    shared = signup.post(
        f"/api/v1/signup/{second['id']}/store",
        headers={"X-Signup-Token": second["token"]},
        json={"store_name": "Al Noor", "slug": "alnoor", "currency": "AED", "country": "AE", "trn": None},
    )
    assert shared.status_code == 409, shared.text
    assert shared.json()["error"]["details"]["fields"]["slug"]
    different = signup.post(
        f"/api/v1/signup/{second['id']}/store",
        headers={"X-Signup-Token": second["token"]},
        json={"store_name": "Al Noor", "slug": "alnoor-2", "currency": "AED", "country": "AE", "trn": None},
    )
    assert different.status_code == 200, different.text
    assert different.json()["store_name"] == "Al Noor"
    with registry.control_session(get_settings()) as db:
        assert db.get(SignupSlugHold, "alnoor") is not None
        assert db.get(SignupSlugHold, "alnoor-2") is not None


def test_a_failed_setup_releases_the_address_and_the_filter_stays_safe(signup: TestClient, monkeypatch) -> None:
    def broken(_job) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setitem(provisioning.STEP_FUNCTIONS, "migrations", broken)
    started = _verified(signup, "fail@alnoor.ae", "+971501234012")
    _business(signup, started)
    queued = signup.post(
        f"/api/v1/signup/{started['id']}/store",
        headers={"X-Signup-Token": started["token"]},
        json={"store_name": "Al Noor", "slug": "released", "currency": "AED", "country": "AE", "trn": None},
    )
    assert queued.status_code == 200, queued.text
    state = signup.get(
        f"/api/v1/signup/{started['id']}/status", headers={"X-Signup-Token": started["token"]}
    )
    assert state.json()["status"] == "FAILED"
    with registry.control_session(get_settings()) as db:
        assert db.get(SignupSlugHold, "released") is None
    assert bloom_filter.probe("slug", "released") == "unknown"
    checked = signup.get("/api/v1/signup/slug-check", params={"slug": "released"})
    assert checked.json()["available"] is True
