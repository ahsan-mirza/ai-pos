"""Production demo catalog, history, and reconciliation."""

import os
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import build_engine
from app.core.permissions import Permission
from app.models import Base
from app.models.business_settings import BusinessSettings
from app.models.product import Product
from app.models.role import Role
from app.models.sale import Sale
from app.models.user import User
from app.services import payment_service
from app.services.demo_catalog import EXPLORER_USERNAME, demo_tenants, explorer_denied, seed_production_demos
from app.services.settings_service import clear_settings_cache
from app.tenancy import provisioning, registry
from app.tenancy.context import use_tenant
from app.tenancy.models import ControlBase, Tenant


class _Gateway(Exception):
    pass


def _boom(*_args, **_kwargs):
    raise _Gateway("A payment gateway was called.")


@pytest.fixture(scope="module")
def demos(tmp_path_factory):
    root = tmp_path_factory.mktemp("demos")
    previous = {
        "DATABASE_URL": os.environ.get("DATABASE_URL"),
        "CONTROL_DATABASE_URL": os.environ.get("CONTROL_DATABASE_URL"),
    }
    shared = f"sqlite:///{(root / 'shared.db').as_posix()}"
    control = f"sqlite:///{(root / 'control.db').as_posix()}"
    os.environ["DATABASE_URL"] = shared
    os.environ["CONTROL_DATABASE_URL"] = control
    get_settings.cache_clear()
    registry.invalidate()
    registry._control_factory.cache_clear()
    clear_settings_cache()
    ControlBase.metadata.create_all(build_engine(control))
    original_migrate = provisioning.migrate
    original_consume = payment_service.consume_for_sale
    provisioning.migrate = lambda url: Base.metadata.create_all(build_engine(url))
    payment_service.consume_for_sale = _boom
    try:
        reports = seed_production_demos(get_settings())
    finally:
        payment_service.consume_for_sale = original_consume
        provisioning.migrate = original_migrate
    yield {"reports": reports, "root": root, "shared": shared, "control": control}
    if previous["DATABASE_URL"] is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous["DATABASE_URL"]
    if previous["CONTROL_DATABASE_URL"] is None:
        os.environ.pop("CONTROL_DATABASE_URL", None)
    else:
        os.environ["CONTROL_DATABASE_URL"] = previous["CONTROL_DATABASE_URL"]
    get_settings.cache_clear()
    registry.invalidate()
    registry._control_factory.cache_clear()
    clear_settings_cache()


def _session(slug: str):
    registry.invalidate(slug)
    found = registry.lookup(slug, get_settings())
    assert found.tenant is not None
    db = sessionmaker(bind=build_engine(found.tenant.database_url), expire_on_commit=False)()
    return db, found.tenant


def test_four_demo_configs():
    codes = [spec["code"] for spec in demo_tenants()]
    assert codes == ["restaurant", "supermarket", "electronics", "fashion"]
    assert {spec["profile"] for spec in demo_tenants()} == {
        "restaurant",
        "grocery",
        "electronics_wholesale",
        "retail_fashion",
    }
    raw = Path(__file__).resolve().parents[3] / "packages" / "catalog" / "production-demos.json"
    body = raw.read_text(encoding="utf-8")
    assert "password" not in body.lower()
    assert "RESTAURANT_CAFE" not in body


def test_profiles_capabilities_and_users(demos):
    assert [report["code"] for report in demos["reports"]] == ["restaurant", "supermarket", "electronics", "fashion"]
    denied = explorer_denied()
    required = {
        "restaurant": {"tables", "menu_modifiers", "kds", "recipes", "split_bills"},
        "supermarket": {"weighed_items", "fefo", "loyalty", "gift_cards"},
        "electronics": {"serial_tracking", "b2b_credit", "warranty", "variants_matrix"},
        "fashion": {"variants_matrix", "loyalty", "promotions"},
    }
    with registry.control_session(get_settings()) as control:
        rows = list(control.scalars(select(Tenant).where(Tenant.is_demo.is_(True))))
    assert {row.demo_business_type for row in rows} == {"restaurant", "supermarket", "electronics", "fashion"}
    assert all(row.demo_access_enabled is False for row in rows)
    for spec in demo_tenants():
        db, ref = _session(spec["slug"])
        try:
            with use_tenant(ref):
                owner = db.scalar(select(User).join(Role).where(Role.name == "Super Admin"))
                explorer = db.scalar(select(User).where(User.username == EXPLORER_USERNAME))
                assert owner is not None and explorer is not None
                assert owner.id != explorer.id
                assert denied.isdisjoint(explorer.permissions)
                assert Permission.PORTAL_ACCESS.value in explorer.permissions
                assert Permission.POS_ACCESS.value in explorer.permissions
                assert Permission.USERS_CREATE.value not in explorer.permissions
                settings = db.scalar(select(BusinessSettings))
                assert settings is not None
                assert settings.business_profile == spec["profile"]
                assert required[spec["code"]] <= set(settings.capabilities or [])
                if spec["code"] != "electronics":
                    assert "b2b_credit" not in (settings.capabilities or [])
        finally:
            db.close()


def test_validation_report_covers_reconciliation(demos):
    by_code = {report["code"]: report for report in demos["reports"]}
    for code, names in {
        "restaurant": [
            "stock",
            "sale_totals",
            "tax",
            "payments",
            "returns",
            "modifiers",
            "tables",
            "kitchen",
            "no_gateway_tender",
        ],
        "supermarket": ["stock", "tax", "payments", "plu", "fefo", "returns"],
        "electronics": ["stock", "serials", "warranties", "electronics_balance", "ledger", "payments"],
        "fashion": ["stock", "variants", "sku_unique", "barcode_unique", "tax", "no_b2b_credit"],
    }.items():
        report = by_code[code]
        assert report["ok"], report["checks"]
        present = {check["name"]: check for check in report["checks"]}
        for name in names:
            assert present[name]["ok"], present[name]


def test_tenant_isolation(demos):
    del demos
    left, left_ref = _session("demo-restaurant")
    right, right_ref = _session("demo-supermarket")
    try:
        with use_tenant(left_ref):
            restaurant = set(left.scalars(select(Product.sku)).all())
        with use_tenant(right_ref):
            grocery = set(right.scalars(select(Product.sku)).all())
    finally:
        left.close()
        right.close()
    assert restaurant
    assert grocery
    assert restaurant.isdisjoint(grocery)


def test_reseed_is_idempotent(demos):
    db, ref = _session("demo-fashion")
    try:
        with use_tenant(ref):
            before = (
                db.scalar(select(func.count()).select_from(Product)),
                db.scalar(select(func.count()).select_from(Sale)),
            )
    finally:
        db.close()
    original = provisioning.migrate
    provisioning.migrate = lambda url: Base.metadata.create_all(build_engine(url))
    try:
        reports = seed_production_demos(get_settings())
    finally:
        provisioning.migrate = original
    assert all(report["ok"] for report in reports)
    db, ref = _session("demo-fashion")
    try:
        with use_tenant(ref):
            after = (
                db.scalar(select(func.count()).select_from(Product)),
                db.scalar(select(func.count()).select_from(Sale)),
            )
    finally:
        db.close()
    assert before == after


def test_history_is_deterministic(demos):
    root: Path = demos["root"]
    second_shared = f"sqlite:///{(root / 'second.db').as_posix()}"
    second_control = f"sqlite:///{(root / 'second-control.db').as_posix()}"
    ControlBase.metadata.create_all(build_engine(second_control))
    settings = get_settings().model_copy(update={"database_url": second_shared, "control_database_url": second_control})
    original = provisioning.migrate
    provisioning.migrate = lambda url: Base.metadata.create_all(build_engine(url))
    try:
        reports = seed_production_demos(settings, codes=["restaurant"])
    finally:
        provisioning.migrate = original
    assert reports[0]["ok"]
    first, first_ref = _session("demo-restaurant")
    registry.invalidate("demo-restaurant")
    second_tenant = registry.lookup("demo-restaurant", settings)
    assert second_tenant.tenant is not None
    other = sessionmaker(bind=build_engine(second_shared), expire_on_commit=False)()
    try:
        with use_tenant(first_ref):
            left = first.execute(select(Sale.client_sale_id, Sale.total_cents).order_by(Sale.client_sale_id)).all()
        with use_tenant(second_tenant.tenant):
            right = other.execute(select(Sale.client_sale_id, Sale.total_cents).order_by(Sale.client_sale_id)).all()
    finally:
        first.close()
        other.close()
        registry.invalidate("demo-restaurant")
    assert left == right
    assert len(left) >= 30
