"""Catalog math: the cycle discount hits recurring fils only, and a later edit does not rewrite a stored quote."""

import os
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.console.billing import cycle_amount, ensure_catalog, quote_for
from app.console.security import OperatorPrincipal
from app.console.site import normalize_whatsapp, set_contact
from app.core.config import get_settings
from app.core.database import build_engine
from app.core.errors import ApiError
from app.main import create_app
from app.schemas.billing import AddonQty
from app.tenancy import registry
from app.tenancy.models import BillingPlan, ControlBase, Operator


def test_annual_discount_is_a_quarter_off_the_year():
    assert cycle_amount(10_000, 12, 2_500) == 90_000
    assert cycle_amount(10_000, 1, 0) == 10_000
    assert cycle_amount(3_900, 3, 500) == 11_115


def test_deposit_and_onboarding_skip_the_cycle_discount():
    engine = create_engine("sqlite://")
    ControlBase.metadata.create_all(engine)
    with Session(engine) as db:
        ensure_catalog(db)
        db.commit()
        priced = quote_for(db, "STANDARD", "ANNUAL", [AddonQty(code="hardware_lease", quantity=1)])
        deposit = next(line for line in priced.lines if line.code == "hardware_lease_once")
        rent = next(line for line in priced.lines if line.code == "hardware_lease")
        onboarding = next(line for line in priced.lines if line.code == "onboarding")
        assert deposit.refundable is True
        assert deposit.amount_fils == 50_000
        assert rent.amount_fils == cycle_amount(15_000, 12, 2_500)
        assert onboarding.amount_fils == 25_000
        assert priced.one_time_fils == 75_000


def test_a_price_edit_changes_the_next_quote_only():
    engine = create_engine("sqlite://")
    ControlBase.metadata.create_all(engine)
    with Session(engine) as db:
        ensure_catalog(db)
        db.commit()
        first = quote_for(db, "PRO", "MONTHLY", [])
        plan = db.scalar(select(BillingPlan).where(BillingPlan.code == "PRO"))
        assert plan is not None
        plan.monthly_fils = 99_900
        db.commit()
        second = quote_for(db, "PRO", "MONTHLY", [])
        assert first.recurring_fils == 49_900
        assert second.recurring_fils == 99_900


def test_public_catalog_lists_the_seed_plans_without_a_tenant(tmp_path) -> None:
    previous = os.environ.get("CONTROL_DATABASE_URL")
    os.environ["CONTROL_DATABASE_URL"] = f"sqlite:///{(tmp_path / 'control.db').as_posix()}"
    get_settings.cache_clear()
    registry.invalidate()
    registry._control_factory.cache_clear()
    engine = build_engine(os.environ["CONTROL_DATABASE_URL"])
    ControlBase.metadata.create_all(engine)
    engine.dispose()
    try:
        client = TestClient(create_app())
        response = client.get("/api/v1/billing/public-catalog")
        assert response.status_code == 200, response.text
        body = response.json()
        assert [plan["code"] for plan in body["plans"]] == ["LITE", "STANDARD", "PRO"]
        assert body["plans"][0]["monthly_fils"] == 14_900
        assert body["plans"][1]["monthly_fils"] == 29_900
        assert body["plans"][2]["monthly_fils"] == 49_900
        assert {cycle["code"] for cycle in body["cycles"]} == {"MONTHLY", "QUARTERLY", "HALF_YEARLY", "ANNUAL"}
        assert {addon["code"] for addon in body["addons"]} == {
            "hardware_lease",
            "equipment_protection",
            "extra_register",
        }
        assert any(fee["code"] == "onboarding" and fee["amount_fils"] == 25_000 for fee in body["fees"])
    finally:
        if previous is None:
            os.environ.pop("CONTROL_DATABASE_URL", None)
        else:
            os.environ["CONTROL_DATABASE_URL"] = previous
        get_settings.cache_clear()
        registry.invalidate()
        registry._control_factory.cache_clear()


def test_public_contact_shows_the_number_saved_for_the_landing_page(tmp_path) -> None:
    previous = os.environ.get("CONTROL_DATABASE_URL")
    os.environ["CONTROL_DATABASE_URL"] = f"sqlite:///{(tmp_path / 'control.db').as_posix()}"
    get_settings.cache_clear()
    registry.invalidate()
    registry._control_factory.cache_clear()
    engine = build_engine(os.environ["CONTROL_DATABASE_URL"])
    ControlBase.metadata.create_all(engine)
    try:
        with TestClient(create_app()) as client:
            empty = client.get("/api/v1/site/contact")
            assert empty.status_code == 200, empty.text
            assert empty.json()["whatsapp"] == ""
            with pytest.raises(ApiError) as caught:
                normalize_whatsapp("call-me")
            assert caught.value.code == "invalid_whatsapp"
            operator_id = uuid.uuid4()
            now = datetime.now(UTC)
            with Session(engine) as db:
                db.add(
                    Operator(
                        id=operator_id,
                        email="it@axizpos.com",
                        full_name="IT",
                        password_hash="x",
                        totp_secret_enc="x",
                        role="ADMIN",
                        created_at=now,
                        updated_at=now,
                    )
                )
                db.commit()
            operator = OperatorPrincipal(
                id=operator_id, email="it@axizpos.com", full_name="IT", role="ADMIN", ip=None
            )
            with Session(engine) as db:
                set_contact(db, operator, "+971 50 123 4567", "Landing page chat")
            saved = client.get("/api/v1/site/contact")
            assert saved.status_code == 200, saved.text
            assert saved.json()["whatsapp"] == "971501234567"
    finally:
        engine.dispose()
        if previous is None:
            os.environ.pop("CONTROL_DATABASE_URL", None)
        else:
            os.environ["CONTROL_DATABASE_URL"] = previous
        get_settings.cache_clear()
        registry.invalidate()
        registry._control_factory.cache_clear()
