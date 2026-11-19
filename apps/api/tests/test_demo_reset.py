"""Production demo reset, recovery, and CLI guards.

The control database and the store database are separate sqlite files here, matching
the separate engines used in production. Reset safety is checked against those commits.
"""

import os
import threading
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import build_engine
from app.core.deps import verify_user_token
from app.core.errors import ApiError
from app.core.security import create_access_token
from app.models import Base
from app.models.audit_log import AuditLog
from app.models.product import Product
from app.models.role import Role
from app.models.sale import Sale
from app.models.user import User
from app.services import demo_validate, payment_service
from app.services.demo_catalog import EXPLORER_USERNAME, demo_tenants, seed_production_demos
from app.services.demo_reset import (
    DemoResetError,
    deactivate_demo_account,
    reactivate_demo_account,
    recover_interrupted_reset,
    reset_all_demo_tenants,
    reset_demo_tenant,
    wipe_operational_data,
)
from app.services.settings_service import clear_settings_cache
from app.tenancy import provisioning, registry
from app.tenancy.cli import main
from app.tenancy.context import use_tenant
from app.tenancy.demo import provision_all
from app.tenancy.models import BillingInvoice, ControlBase, Subscription, Tenant


class _Gateway(Exception):
    pass


def _boom(*_args, **_kwargs):
    raise _Gateway("A payment gateway was called.")


@pytest.fixture(scope="module")
def demos(tmp_path_factory):
    root = tmp_path_factory.mktemp("reset-demos")
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
    yield {"reports": reports, "root": root}
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


def _open(slug: str):
    registry.invalidate(slug)
    found = registry.lookup(slug, get_settings())
    assert found.tenant is not None
    db = sessionmaker(bind=build_engine(found.tenant.database_url), expire_on_commit=False)()
    return db, found.tenant


def _sales(slug: str) -> list[tuple]:
    db, ref = _open(slug)
    try:
        with use_tenant(ref):
            rows = db.execute(
                select(Sale.id, Sale.client_sale_id, Sale.total_cents).order_by(Sale.client_sale_id)
            ).all()
        return [(row.id, row.client_sale_id, row.total_cents) for row in rows]
    finally:
        db.close()


def _products(slug: str) -> list[tuple]:
    db, ref = _open(slug)
    try:
        with use_tenant(ref):
            rows = db.execute(select(Product.id, Product.sku).order_by(Product.sku)).all()
        return [(row.id, row.sku) for row in rows]
    finally:
        db.close()


def _users(slug: str) -> list[tuple]:
    db, ref = _open(slug)
    try:
        with use_tenant(ref):
            rows = db.execute(
                select(User.id, User.username, User.token_version, Role.name)
                .join(Role, User.role_id == Role.id)
                .order_by(User.username)
            ).all()
        return [(row.id, row.username, row.token_version, row.name) for row in rows]
    finally:
        db.close()


def _control_row(slug: str) -> Tenant:
    with registry.control_session(get_settings()) as db:
        row = db.scalar(select(Tenant).where(Tenant.slug == slug))
        assert row is not None
        db.expunge(row)
        return row


def _subscription(tenant_id: uuid.UUID) -> tuple:
    with registry.control_session(get_settings()) as db:
        row = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
        invoices = db.scalar(
            select(func.count()).select_from(BillingInvoice).where(BillingInvoice.tenant_id == tenant_id)
        )
        assert row is not None
        return (row.id, row.plan_id, row.status, int(invoices or 0))


def _token(slug: str) -> str:
    db, ref = _open(slug)
    try:
        with use_tenant(ref):
            explorer = db.scalar(select(User).where(User.username == EXPLORER_USERNAME))
            assert explorer is not None
            token, _expires = create_access_token(
                subject=str(explorer.id),
                scope="portal",
                token_version=int(explorer.token_version or 0),
                settings=get_settings(),
                tenant_id=str(ref.id),
            )
            assert verify_user_token(token, db, get_settings()).id == explorer.id
        return token
    finally:
        db.close()


def _rejected(slug: str, token: str) -> None:
    db, ref = _open(slug)
    try:
        with use_tenant(ref), pytest.raises(ApiError) as caught:
            verify_user_token(token, db, get_settings())
        assert caught.value.status_code == 401
    finally:
        db.close()


def test_dev_demo_command_still_refuses_production():
    settings = get_settings().model_copy(update={"app_env": "production"})
    with pytest.raises(SystemExit) as caught:
        provision_all(settings)
    assert "development" in str(caught.value)


def test_normal_and_unknown_tenants_are_refused(demos):
    assert demos["reports"]
    with pytest.raises(DemoResetError, match="Unknown demo business code"):
        reset_demo_tenant(get_settings(), "warehouse")
    restaurant = _control_row("demo-restaurant")
    with registry.control_session(get_settings()) as db:
        source = db.scalar(select(Tenant).where(Tenant.slug == "demo-restaurant"))
        assert source is not None
        db.add(
            Tenant(
                slug="live-market",
                name="Live Market",
                status="active",
                profile="grocery",
                database_url_encrypted=source.database_url_encrypted,
                data_plane=source.data_plane,
                plan=source.plan,
                practice_mode=True,
                is_demo=False,
            )
        )
        source.slug = "demo-restaurant-moved"
        db.commit()
    try:
        with pytest.raises(DemoResetError, match="Unknown demo tenant"):
            reset_demo_tenant(get_settings(), "restaurant")
    finally:
        with registry.control_session(get_settings()) as db:
            moved = db.scalar(select(Tenant).where(Tenant.slug == "demo-restaurant-moved"))
            assert moved is not None
            moved.slug = "demo-restaurant"
            db.commit()
    before = _sales("demo-restaurant")
    with registry.control_session(get_settings()) as db:
        row = db.scalar(select(Tenant).where(Tenant.slug == "demo-restaurant"))
        assert row is not None
        row.is_demo = False
        db.commit()
    try:
        with pytest.raises(DemoResetError, match="not a demo tenant"):
            reset_demo_tenant(get_settings(), "restaurant")
    finally:
        with registry.control_session(get_settings()) as db:
            row = db.scalar(select(Tenant).where(Tenant.slug == "demo-restaurant"))
            assert row is not None
            row.is_demo = True
            db.commit()
    with registry.control_session(get_settings()) as db:
        row = db.scalar(select(Tenant).where(Tenant.slug == "demo-restaurant"))
        assert row is not None
        row.demo_seed_version = 99
        db.commit()
    try:
        with pytest.raises(DemoResetError, match="catalog version"):
            reset_demo_tenant(get_settings(), "restaurant")
    finally:
        with registry.control_session(get_settings()) as db:
            row = db.scalar(select(Tenant).where(Tenant.slug == "demo-restaurant"))
            assert row is not None
            row.demo_seed_version = restaurant.demo_seed_version
            db.commit()
    assert _sales("demo-restaurant") == before
    with registry.control_session(get_settings()) as db:
        live = db.scalar(select(Tenant).where(Tenant.slug == "live-market"))
        assert live is not None and live.is_demo is False


def test_dry_run_changes_nothing(demos):
    assert demos["reports"]
    before = {spec["slug"]: _sales(spec["slug"]) for spec in demo_tenants()}
    users = _users("demo-restaurant")
    summary = reset_demo_tenant(get_settings(), "restaurant", dry_run=True)
    listed = reset_all_demo_tenants(get_settings(), dry_run=True)
    assert summary["dry_run"] is True and summary["sales"] == len(before["demo-restaurant"])
    assert [item["code"] for item in listed] == ["restaurant", "supermarket", "electronics", "fashion", "pharmacy"]
    assert _sales("demo-restaurant") == before["demo-restaurant"]
    assert _users("demo-restaurant") == users
    assert _control_row("demo-restaurant").demo_status == "active"
    for spec in demo_tenants():
        assert _sales(spec["slug"]) == before[spec["slug"]]


def test_reset_one_tenant_leaves_the_others_and_revokes_the_old_token(demos):
    assert demos["reports"]
    others = {
        spec["slug"]: (_sales(spec["slug"]), _products(spec["slug"]))
        for spec in demo_tenants()
        if spec["code"] != "restaurant"
    }
    restaurant_sales = [(sale_id, total) for _sale, sale_id, total in _sales("demo-restaurant")]
    restaurant_skus = [sku for _product, sku in _products("demo-restaurant")]
    users = _users("demo-restaurant")
    token = _token("demo-restaurant")
    tenant = _control_row("demo-restaurant")
    subscription = _subscription(tenant.id)
    result = reset_demo_tenant(get_settings(), "restaurant")
    assert result["ok"] is True
    restored = _sales("demo-restaurant")
    assert [(sale_id, total) for _sale, sale_id, total in restored] == restaurant_sales
    assert len(restored) >= 30
    assert {row[0] for row in restored}.isdisjoint({row[0] for row in _sales("demo-supermarket")})
    assert [sku for _product, sku in _products("demo-restaurant")] == restaurant_skus
    assert {sku for _product, sku in _products("demo-restaurant")}.isdisjoint(
        {sku for _product, sku in _products("demo-supermarket")}
    )
    for slug, (sales, products) in others.items():
        assert _sales(slug) == sales
        assert _products(slug) == products
    after_users = _users("demo-restaurant")
    assert [(row[0], row[1], row[3]) for row in after_users] == [(row[0], row[1], row[3]) for row in users]
    explorer = next(row for row in after_users if row[1] == EXPLORER_USERNAME)
    owner = next(row for row in after_users if row[3] == "Super Admin")
    assert explorer[2] == next(row[2] for row in users if row[1] == EXPLORER_USERNAME) + 1
    assert owner[2] == next(row[2] for row in users if row[3] == "Super Admin")
    assert len(after_users) == 2
    _rejected("demo-restaurant", token)
    finished = _control_row("demo-restaurant")
    assert finished.demo_status == "active"
    assert finished.demo_access_enabled is False
    assert finished.demo_reset_phase is None
    assert finished.demo_last_reset_at is not None
    assert _subscription(tenant.id) == subscription
    with registry.control_session(get_settings()) as db:
        assert db.scalar(select(func.count()).select_from(Subscription).where(Subscription.tenant_id == tenant.id)) == 1


def test_concurrent_reset_is_refused_and_the_lock_is_released(demos):
    assert demos["reports"]
    started = threading.Event()
    release = threading.Event()
    holder: dict = {}
    original = wipe_operational_data

    def blocking(db, tenant_id):
        started.set()
        assert release.wait(60)
        return original(db, tenant_id)

    import app.services.demo_reset as reset_module

    reset_module.wipe_operational_data = blocking
    def run() -> None:
        try:
            holder["result"] = reset_demo_tenant(get_settings(), "supermarket")
        except Exception as exc:  # noqa: BLE001 - the assertion below reports the worker failure
            holder["error"] = exc

    worker = threading.Thread(target=run)
    try:
        worker.start()
        assert started.wait(60)
        with pytest.raises(DemoResetError, match="resetting"):
            reset_demo_tenant(get_settings(), "supermarket")
        assert _control_row("demo-supermarket").demo_status == "resetting"
    finally:
        release.set()
        worker.join(180)
        reset_module.wipe_operational_data = original
    assert "error" not in holder, holder.get("error")
    assert holder["result"]["ok"] is True
    assert _control_row("demo-supermarket").demo_status == "active"


def test_failed_wipe_releases_the_lock_for_recovery(demos):
    assert demos["reports"]
    before = _sales("demo-fashion")
    import app.services.demo_reset as reset_module

    def boom(_db, _tenant_id):
        raise RuntimeError("wipe failed")

    original = reset_module.wipe_operational_data
    reset_module.wipe_operational_data = boom
    try:
        with pytest.raises(RuntimeError, match="wipe failed"):
            reset_demo_tenant(get_settings(), "fashion")
    finally:
        reset_module.wipe_operational_data = original
    assert _control_row("demo-fashion").demo_status == "reset_failed"
    assert _sales("demo-fashion") == before
    recovered = recover_interrupted_reset(get_settings(), "fashion")
    assert recovered[0]["ok"] is True
    assert _control_row("demo-fashion").demo_status == "active"
    assert [(sale_id, total) for _sale, sale_id, total in _sales("demo-fashion")] == [
        (sale_id, total) for _sale, sale_id, total in before
    ]


def test_interrupted_reset_recovers_without_touching_other_tenants(demos):
    assert demos["reports"]
    restaurant = _sales("demo-restaurant")
    electronics = _sales("demo-electronics")
    fashion = _sales("demo-fashion")
    with registry.control_session(get_settings()) as db:
        row = db.scalar(select(Tenant).where(Tenant.slug == "demo-supermarket"))
        assert row is not None
        row.demo_status = "resetting"
        row.demo_reset_phase = "wipe"
        row.demo_reset_operation_id = uuid.uuid4()
        tenant_id = row.id
        db.commit()
    with pytest.raises(DemoResetError, match="resetting"):
        reset_demo_tenant(get_settings(), "supermarket")
    db, ref = _open("demo-supermarket")
    try:
        with use_tenant(ref):
            wipe_operational_data(db, tenant_id)
            db.commit()
            assert db.scalar(select(func.count()).select_from(Sale)) == 0
    finally:
        db.close()
    recovered = recover_interrupted_reset(get_settings(), "supermarket")
    assert recovered[0]["ok"] is True
    assert _control_row("demo-supermarket").demo_status == "active"
    assert len(_sales("demo-supermarket")) >= 30
    assert _sales("demo-restaurant") == restaurant
    assert _sales("demo-electronics") == electronics
    assert _sales("demo-fashion") == fashion


def test_failed_validation_does_not_mark_the_reset_complete(demos, monkeypatch):
    assert demos["reports"]

    def bad(_db, spec):
        return {"code": spec["code"], "ok": False, "checks": [{"name": "stock", "ok": False}]}

    monkeypatch.setattr(demo_validate, "validate_demo", bad)
    try:
        with pytest.raises(DemoResetError, match="failed validation"):
            reset_demo_tenant(get_settings(), "electronics")
        assert _control_row("demo-electronics").demo_status == "reset_failed"
    finally:
        monkeypatch.undo()
    recovered = recover_interrupted_reset(get_settings(), "electronics")
    assert recovered[0]["ok"] is True
    assert _control_row("demo-electronics").demo_status == "active"
    db, ref = _open("demo-electronics")
    try:
        with use_tenant(ref):
            spec = next(item for item in demo_tenants() if item["slug"] == "demo-electronics")
            report = demo_validate.validate_demo(db, spec)
        assert report["ok"] is True
    finally:
        db.close()


def test_deactivation_revokes_the_session_and_keeps_the_records(demos):
    assert demos["reports"]
    before = _sales("demo-fashion")
    subscription = _subscription(_control_row("demo-fashion").id)
    token = _token("demo-fashion")
    operator = uuid.uuid4()
    result = deactivate_demo_account(get_settings(), "fashion", operator_id=operator)
    assert result["demo_status"] == "disabled"
    assert result["token_version"] == next(row[2] for row in _users("demo-fashion") if row[1] == EXPLORER_USERNAME)
    assert _sales("demo-fashion") == before
    assert _subscription(_control_row("demo-fashion").id) == subscription
    _rejected("demo-fashion", token)
    row = _control_row("demo-fashion")
    assert row.demo_status == "disabled" and row.demo_access_enabled is False
    db, ref = _open("demo-fashion")
    try:
        with use_tenant(ref):
            entry = db.scalar(select(AuditLog).where(AuditLog.action == "demo.deactivate"))
            assert entry is not None
            assert entry.details["operator_id"] == str(operator)
            assert entry.details["at"]
    finally:
        db.close()
    with pytest.raises(DemoResetError, match="deactivated"):
        reset_demo_tenant(get_settings(), "fashion")
    assert _sales("demo-fashion") == before
    again = deactivate_demo_account(get_settings(), "fashion", operator_id=operator)
    assert again["token_version"] is None
    restored = reactivate_demo_account(get_settings(), "fashion")
    assert restored == {
        "code": "fashion",
        "slug": "demo-fashion",
        "demo_status": "active",
        "demo_access_enabled": False,
    }
    assert _sales("demo-fashion") == before
    _rejected("demo-fashion", token)


def test_reset_all_demo_tenants(demos):
    assert demos["reports"]
    before = {
        spec["code"]: [(sale_id, total) for _sale, sale_id, total in _sales(spec["slug"])] for spec in demo_tenants()
    }
    subscriptions = {spec["slug"]: _subscription(_control_row(spec["slug"]).id) for spec in demo_tenants()}
    results = reset_all_demo_tenants(get_settings())
    assert [item["code"] for item in results] == ["restaurant", "supermarket", "electronics", "fashion", "pharmacy"]
    assert all(item["ok"] for item in results)
    for spec in demo_tenants():
        restored = [(sale_id, total) for _sale, sale_id, total in _sales(spec["slug"])]
        assert restored == before[spec["code"]]
        assert len(restored) >= 30
        assert _control_row(spec["slug"]).demo_status == "active"
        assert _subscription(_control_row(spec["slug"]).id) == subscriptions[spec["slug"]]


def test_cli_exit_codes_dry_run_and_production_confirmation(demos, capsys):
    assert demos["reports"]
    main(["validate-demo-data", "--business-code", "supermarket"])
    validation = capsys.readouterr().out
    assert '"ok": true' in validation
    assert "password" not in validation.lower()
    with pytest.raises(SystemExit) as missing:
        main(["validate-demo-data"])
    assert missing.value.code not in (None, 0)
    before = _sales("demo-restaurant")
    main(["reset-demo-data", "--business-code", "restaurant", "--dry-run"])
    dry = capsys.readouterr().out
    assert "Dry run" in dry and "restaurant" in dry and "password" not in dry.lower()
    assert _sales("demo-restaurant") == before
    production = get_settings().model_copy(update={"app_env": "production"})
    import app.tenancy.cli as cli

    original = cli.get_settings
    cli.get_settings = lambda: production
    try:
        with pytest.raises(SystemExit) as refused:
            main(["reset-demo-data", "--business-code", "restaurant"])
        assert refused.value.code == 2
        assert _sales("demo-restaurant") == before
        main(["reset-demo-data", "--all", "--dry-run"])
        listed = capsys.readouterr().out
        for spec in demo_tenants():
            assert spec["code"] in listed
    finally:
        cli.get_settings = original
    subscription = _subscription(_control_row("demo-restaurant").id)
    original_migrate = provisioning.migrate
    original_consume = payment_service.consume_for_sale
    provisioning.migrate = lambda _url: None
    payment_service.consume_for_sale = _boom
    try:
        main(["seed-demo-data", "--business-code", "restaurant"])
    finally:
        provisioning.migrate = original_migrate
        payment_service.consume_for_sale = original_consume
    seeded = capsys.readouterr().out
    assert "password" not in seeded.lower()
    assert _sales("demo-restaurant") == before
    assert _subscription(_control_row("demo-restaurant").id) == subscription
