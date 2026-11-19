"""Console-created packages can be added and removed. Seeded packages and live contracts stay."""

import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.console.billing import create_plan, delete_plan, ensure_catalog
from app.console.security import OperatorPrincipal
from app.core.errors import ApiError
from app.schemas.billing import PlanCreateIn
from app.tenancy.models import BillingCycle, BillingInvoice, BillingPlan, ControlBase, Subscription, Tenant


def _control() -> Session:
    engine = create_engine("sqlite://")
    ControlBase.metadata.create_all(engine)
    return Session(engine)


def _operator() -> OperatorPrincipal:
    return OperatorPrincipal(id=uuid.uuid4(), email="it@axizpos.com", full_name="IT", role="ADMIN", ip=None)


def _draft(code: str) -> PlanCreateIn:
    return PlanCreateIn(
        code=code,
        name="Retail Plus",
        included_registers=2,
        included_modules=[],
        monthly_fils=19_900,
        trial_days=7,
        active=True,
        sort_order=40,
        reason="Offer a retail package",
    )


def test_a_new_package_is_current_and_an_unused_one_can_be_deleted() -> None:
    with _control() as db:
        ensure_catalog(db)
        created = create_plan(db, _operator(), _draft("RETAIL_PLUS"))
        assert created.code == "RETAIL_PLUS"
        assert created.catalog_family == "current"
        assert created.monthly_fils == 19_900
        delete_plan(db, _operator(), created.id, "No stores selected it")
        assert db.get(BillingPlan, created.id) is None


def test_duplicate_retired_and_invalid_codes_are_rejected() -> None:
    with _control() as db:
        ensure_catalog(db)
        operator = _operator()
        create_plan(db, operator, _draft("RETAIL_PLUS"))
        with pytest.raises(ApiError) as duplicate:
            create_plan(db, operator, _draft("retail_plus"))
        assert duplicate.value.code == "duplicate_code"
        assert duplicate.value.details is not None
        assert duplicate.value.details["fields"]["code"] == "This package code already exists."
        with pytest.raises(ApiError) as retired:
            create_plan(db, operator, _draft("LITE"))
        assert retired.value.code == "plan_not_selectable"
        with pytest.raises(ApiError) as invalid:
            create_plan(db, operator, _draft("1BAD"))
        assert invalid.value.code == "invalid_code"


def test_seeded_packages_and_referenced_packages_are_not_deleted() -> None:
    with _control() as db:
        ensure_catalog(db)
        operator = _operator()
        free = db.scalar(select(BillingPlan).where(BillingPlan.code == "FREE"))
        assert free is not None
        with pytest.raises(ApiError) as protected:
            delete_plan(db, operator, free.id, "Remove the free package")
        assert protected.value.code == "package_protected"
        created = create_plan(db, operator, _draft("RETAIL_PLUS"))
        tenant = Tenant(slug="plus", name="Plus", status="active", database_url_encrypted="x", plan="RETAIL_PLUS")
        db.add(tenant)
        db.flush()
        cycle = db.scalar(select(BillingCycle).where(BillingCycle.code == "MONTHLY"))
        assert cycle is not None
        db.add(Subscription(tenant_id=tenant.id, plan_id=created.id, cycle_id=cycle.id, status="active"))
        db.add(
            BillingInvoice(
                tenant_id=tenant.id,
                status="paid",
                plan_code="RETAIL_PLUS",
                cycle_code="MONTHLY",
                confirm_name="Plus",
            )
        )
        db.commit()
        with pytest.raises(ApiError) as used:
            delete_plan(db, operator, created.id, "Remove the retail package")
        assert used.value.code == "package_in_use"
        assert db.get(BillingPlan, created.id) is not None
