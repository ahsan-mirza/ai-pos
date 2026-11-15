"""Tenant data reset stays inside one tenant, refuses a bad password, and restores from the snapshot."""

import uuid

from sqlalchemy import select
from tests.governance_support import OPERATOR_PASSWORD, platform  # noqa: F401

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.inventory import InventoryLevel
from app.models.product import Product
from app.models.sale import Sale
from app.models.store import Store
from app.models.user import User
from app.services.rbac_service import super_admin_role_id
from app.tenancy.models import OperatorAuditLog


def _settings(tmp_path):
    settings = get_settings()
    settings.data_reset_dir = str(tmp_path / "resets")
    return settings


def _seed(platform):  # noqa: F811
    with platform.session("alpha") as db:
        first = Store(code="A1", name="Alpha Main", currency="AED")
        second = Store(code="A2", name="Alpha Annex", currency="AED")
        product = Product(
            sku="phone",
            barcode=uuid.uuid4().hex[:12],
            name="Phone",
            category="Retail",
            price_cents=100,
            currency="AED",
            item_type="PRE_PACKAGED",
        )
        db.add_all([first, second, product])
        db.flush()
        db.add(InventoryLevel(product_id=product.id, store_id=first.id, quantity_on_hand=4))
        db.add(InventoryLevel(product_id=product.id, store_id=second.id, quantity_on_hand=7))
        owner = db.scalar(select(User).where(User.store_id.is_(None)))
        branch = User(
            username="annex",
            email="annex@alpha.example",
            full_name="Annex Cashier",
            hashed_password=hash_password("Branch-password-1"),
            store_id=second.id,
            role_id=super_admin_role_id(db),
            has_portal_access=True,
        )
        db.add(branch)
        db.commit()
        ids = {"first": first.id, "second": second.id, "product": product.id, "owner": owner.id, "branch": branch.id}
    with platform.session("bravo") as db:
        store = Store(code="B1", name="Bravo Main", currency="AED")
        product = Product(
            sku="bravo-phone",
            barcode=uuid.uuid4().hex[:12],
            name="Bravo Phone",
            category="Retail",
            price_cents=100,
            currency="AED",
            item_type="PRE_PACKAGED",
        )
        db.add_all([store, product])
        db.flush()
        db.add(InventoryLevel(product_id=product.id, store_id=store.id, quantity_on_hand=3))
        db.commit()
        ids["bravo_store"] = store.id
        ids["bravo_product"] = product.id
    return ids


def _preview(platform, headers, tenant, **extra):  # noqa: F811
    body = {
        "scope": "store",
        "categories": ["products"],
        "idempotency_key": uuid.uuid4().hex,
        "acknowledge_dependencies": False,
    }
    body.update(extra)
    return platform.client.post(f"/api/v1/super-admin/tenants/{tenant}/data-reset/preview", headers=headers, json=body)


def _run(platform, headers, tenant, preview):  # noqa: F811
    operation = preview.json()["id"]
    authorized = platform.client.post(
        f"/api/v1/super-admin/tenants/{tenant}/data-reset/{operation}/authorize",
        headers=headers,
        json={"password": OPERATOR_PASSWORD},
    )
    assert authorized.status_code == 200, authorized.text
    executed = platform.client.post(
        f"/api/v1/super-admin/tenants/{tenant}/data-reset/{operation}/execute",
        headers=headers,
    )
    assert executed.status_code == 200, executed.text
    return executed.json()


def test_single_branch_reset_leaves_the_other_branch_and_tenant(platform, tmp_path) -> None:  # noqa: F811
    _settings(tmp_path)
    ids = _seed(platform)
    headers = platform.operator()
    tenant = platform.tenant_id("alpha")
    preview = _preview(platform, headers, tenant, store_id=str(ids["first"]))
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["ready"] is True
    assert body["preview"]["total_records"] == 1
    assert any(row["label"] == "Products and variants" for row in body["preview"]["skipped_shared"])
    done = _run(platform, headers, tenant, preview)
    assert done["status"] == "COMPLETED"
    assert done["records_reset"] == 1
    with platform.session("alpha") as db:
        assert db.scalar(select(InventoryLevel.id).where(InventoryLevel.store_id == ids["first"])) is None
        kept = db.scalar(select(InventoryLevel).where(InventoryLevel.store_id == ids["second"]))
        assert kept is not None and kept.quantity_on_hand == 7
        assert db.get(Product, ids["product"]) is not None
        assert db.get(Store, ids["first"]) is not None
        assert db.get(User, ids["owner"]) is not None
    with platform.session("bravo") as db:
        assert db.get(Product, ids["bravo_product"]) is not None
        kept = db.scalar(select(InventoryLevel).where(InventoryLevel.store_id == ids["bravo_store"]))
        assert kept is not None and kept.quantity_on_hand == 3


def test_all_branch_reset_removes_only_that_tenants_catalog(platform, tmp_path) -> None:  # noqa: F811
    _settings(tmp_path)
    ids = _seed(platform)
    headers = platform.operator(email="reset-all@axizpos.com")
    tenant = platform.tenant_id("alpha")
    preview = _preview(platform, headers, tenant, scope="tenant", categories=["products"])
    assert preview.status_code == 200, preview.text
    done = _run(platform, headers, tenant, preview)
    assert done["records_reset"] >= 3
    with platform.session("alpha") as db:
        assert db.get(Product, ids["product"]) is None
        assert db.scalar(select(InventoryLevel.id).where(InventoryLevel.store_id == ids["first"])) is None
        assert db.get(Store, ids["first"]) is not None
    with platform.session("bravo") as db:
        assert db.get(Product, ids["bravo_product"]) is not None


def test_cross_tenant_branch_is_rejected(platform, tmp_path) -> None:  # noqa: F811
    _settings(tmp_path)
    ids = _seed(platform)
    headers = platform.operator(email="reset-cross@axizpos.com")
    tenant = platform.tenant_id("alpha")
    preview = _preview(platform, headers, tenant, store_id=str(ids["bravo_store"]))
    assert preview.status_code == 422
    assert preview.json()["error"]["code"] == "store_outside_tenant"


def test_support_cannot_reset_and_a_bad_password_is_not_stored(platform, tmp_path) -> None:  # noqa: F811
    _settings(tmp_path)
    ids = _seed(platform)
    support = platform.operator(email="reset-support@axizpos.com", role="SUPPORT")
    tenant = platform.tenant_id("alpha")
    denied = platform.client.get(f"/api/v1/super-admin/tenants/{tenant}/data-reset/catalog", headers=support)
    assert denied.status_code == 403
    assert "tenant.data.reset" in denied.json()["error"]["message"]
    admin = platform.operator(email="reset-admin@axizpos.com")
    preview = _preview(platform, admin, tenant, store_id=str(ids["first"]))
    operation = preview.json()["id"]
    missing = platform.client.post(
        f"/api/v1/super-admin/tenants/{tenant}/data-reset/{operation}/authorize",
        headers=admin,
        json={"password": ""},
    )
    assert missing.status_code == 422
    secret = "not-the-console-password"
    wrong = platform.client.post(
        f"/api/v1/super-admin/tenants/{tenant}/data-reset/{operation}/authorize",
        headers=admin,
        json={"password": secret},
    )
    assert wrong.status_code == 401
    with platform.control() as db:
        rows = list(
            db.scalars(select(OperatorAuditLog).where(OperatorAuditLog.action == "console.data_reset_password_failed"))
        )
        assert rows
        dumped = str([row.after for row in rows])
        assert secret not in dumped


def test_repeated_password_failures_are_limited(platform, tmp_path) -> None:  # noqa: F811
    _settings(tmp_path)
    ids = _seed(platform)
    headers = platform.operator(email="reset-lock@axizpos.com")
    tenant = platform.tenant_id("alpha")
    preview = _preview(platform, headers, tenant, store_id=str(ids["first"]))
    operation = preview.json()["id"]
    for _ in range(get_settings().login_max_attempts):
        failed = platform.client.post(
            f"/api/v1/super-admin/tenants/{tenant}/data-reset/{operation}/authorize",
            headers=headers,
            json={"password": "Wrong-password-1"},
        )
        assert failed.status_code == 401
    locked = platform.client.post(
        f"/api/v1/super-admin/tenants/{tenant}/data-reset/{operation}/authorize",
        headers=headers,
        json={"password": OPERATOR_PASSWORD},
    )
    assert locked.status_code == 429


def test_snapshot_failure_does_not_delete(platform, tmp_path, monkeypatch) -> None:  # noqa: F811
    _settings(tmp_path)
    ids = _seed(platform)
    headers = platform.operator(email="reset-snap@axizpos.com")
    tenant = platform.tenant_id("alpha")
    preview = _preview(platform, headers, tenant, store_id=str(ids["first"]))
    operation = preview.json()["id"]
    platform.client.post(
        f"/api/v1/super-admin/tenants/{tenant}/data-reset/{operation}/authorize",
        headers=headers,
        json={"password": OPERATOR_PASSWORD},
    )
    def _broken(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("disk")

    monkeypatch.setattr("app.console.data_reset._write_snapshot", _broken)
    executed = platform.client.post(
        f"/api/v1/super-admin/tenants/{tenant}/data-reset/{operation}/execute", headers=headers
    )
    assert executed.status_code == 409
    with platform.session("alpha") as db:
        kept = db.scalar(select(InventoryLevel).where(InventoryLevel.store_id == ids["first"]))
        assert kept is not None and kept.quantity_on_hand == 4


def test_restore_puts_the_branch_back_and_skips_conflicts(platform, tmp_path) -> None:  # noqa: F811
    _settings(tmp_path)
    ids = _seed(platform)
    headers = platform.operator(email="reset-restore@axizpos.com")
    tenant = platform.tenant_id("alpha")
    preview = _preview(platform, headers, tenant, store_id=str(ids["first"]))
    done = _run(platform, headers, tenant, preview)
    with platform.session("alpha") as db:
        level = db.scalar(select(InventoryLevel).where(InventoryLevel.store_id == ids["second"]))
        assert level is not None
        original = db.scalar(select(InventoryLevel.id).where(InventoryLevel.store_id == ids["first"]))
        assert original is None
    again = platform.client.post(
        f"/api/v1/super-admin/tenants/{tenant}/data-reset/{done['id']}/execute", headers=headers
    )
    assert again.status_code == 200
    assert again.json()["status"] == "COMPLETED"
    looked = platform.client.post(
        f"/api/v1/super-admin/tenants/{tenant}/data-reset/{done['id']}/restore/preview",
        headers=headers,
    )
    assert looked.status_code == 200, looked.text
    assert looked.json()["records_to_restore"] >= 1
    platform.client.post(
        f"/api/v1/super-admin/tenants/{tenant}/data-reset/{done['id']}/restore/authorize",
        headers=headers,
        json={"password": OPERATOR_PASSWORD},
    )
    restored = platform.client.post(
        f"/api/v1/super-admin/tenants/{tenant}/data-reset/{done['id']}/restore", headers=headers
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["records_restored"] >= 1
    with platform.session("alpha") as db:
        level = db.scalar(select(InventoryLevel).where(InventoryLevel.store_id == ids["first"]))
        assert level is not None and level.quantity_on_hand == 4
        level.quantity_on_hand = 9
        db.commit()
        kept_id = level.id
    platform.client.post(
        f"/api/v1/super-admin/tenants/{tenant}/data-reset/{done['id']}/restore/authorize",
        headers=headers,
        json={"password": OPERATOR_PASSWORD},
    )
    second = platform.client.post(
        f"/api/v1/super-admin/tenants/{tenant}/data-reset/{done['id']}/restore", headers=headers
    )
    assert second.status_code == 200, second.text
    assert second.json()["conflicts"]
    with platform.session("alpha") as db:
        level = db.get(InventoryLevel, kept_id)
        assert level is not None and level.quantity_on_hand == 9


def test_expired_and_corrupt_snapshots_are_rejected(platform, tmp_path) -> None:  # noqa: F811
    from datetime import UTC, datetime, timedelta

    from app.tenancy.models import TenantDataOperation

    _settings(tmp_path)
    ids = _seed(platform)
    headers = platform.operator(email="reset-expire@axizpos.com")
    tenant = platform.tenant_id("alpha")
    preview = _preview(platform, headers, tenant, store_id=str(ids["first"]))
    done = _run(platform, headers, tenant, preview)
    with platform.control() as db:
        row = db.get(TenantDataOperation, uuid.UUID(done["id"]))
        row.expires_at = datetime.now(UTC) - timedelta(days=1)
        db.commit()
    expired = platform.client.post(
        f"/api/v1/super-admin/tenants/{tenant}/data-reset/{done['id']}/restore/preview",
        headers=headers,
    )
    assert expired.status_code == 409
    assert expired.json()["error"]["code"] == "snapshot_expired"
    with platform.control() as db:
        row = db.get(TenantDataOperation, uuid.UUID(done["id"]))
        row.expires_at = datetime.now(UTC) + timedelta(days=1)
        path = get_settings().data_reset_dir
        db.commit()
        rel = row.snapshot_relpath
    from pathlib import Path

    target = Path(path) / rel
    target.write_text("not-a-snapshot", encoding="utf-8")
    corrupt = platform.client.post(
        f"/api/v1/super-admin/tenants/{tenant}/data-reset/{done['id']}/restore/preview",
        headers=headers,
    )
    assert corrupt.status_code == 409
    assert corrupt.json()["error"]["code"] == "snapshot_corrupt"


def test_staff_reset_requires_sales_when_sales_exist_and_keeps_the_owner(platform, tmp_path) -> None:  # noqa: F811
    _settings(tmp_path)
    ids = _seed(platform)
    with platform.session("alpha") as db:
        db.add(
            Sale(
                store_id=ids["second"],
                cashier_id=ids["branch"],
                status="completed",
                currency="AED",
                payment_method="cash",
                subtotal_cents=100,
                tax_cents=0,
                total_cents=100,
                amount_paid_cents=100,
                due_balance_cents=0,
                client_sale_id="sale-1",
            )
        )
        db.commit()
    headers = platform.operator(email="reset-staff@axizpos.com")
    tenant = platform.tenant_id("alpha")
    blocked = _preview(
        platform,
        headers,
        tenant,
        store_id=str(ids["second"]),
        categories=["staff"],
        idempotency_key="staff-block-01",
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["ready"] is False
    assert "sales" in blocked.json()["preview"]["required_categories"]
    confirmed = _preview(
        platform,
        headers,
        tenant,
        store_id=str(ids["second"]),
        categories=["staff"],
        idempotency_key="staff-block-01",
        acknowledge_dependencies=True,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["ready"] is True
    assert "sales" in confirmed.json()["categories"]
    with platform.session("alpha") as db:
        cashier = User(
            username="main",
            email="main@alpha.example",
            full_name="Main Cashier",
            hashed_password=hash_password("Branch-password-1"),
            store_id=ids["first"],
            role_id=super_admin_role_id(db),
            has_portal_access=True,
        )
        db.add(cashier)
        db.commit()
        cashier_id = cashier.id
    staff = _preview(
        platform,
        headers,
        tenant,
        store_id=str(ids["first"]),
        categories=["staff"],
        idempotency_key="staff-owner-01",
    )
    assert staff.status_code == 200, staff.text
    assert staff.json()["ready"] is True
    _run(platform, headers, tenant, staff)
    with platform.session("alpha") as db:
        assert db.get(User, cashier_id) is None
        assert db.get(User, ids["owner"]) is not None
        assert db.get(User, ids["branch"]) is not None
        assert db.get(Product, ids["product"]) is not None
