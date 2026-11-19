"""Stage 3F.2 disposable PostgreSQL checks as a real ai_pos_app login.

The process that runs Alembic is the container bootstrap role. Every stock,
return, recall, and RLS statement under test uses a second engine whose login
is ai_pos_app. SET ROLE is not used.
"""

from __future__ import annotations

import os
import statistics
import threading
import time
import traceback
import uuid
from datetime import date, timedelta

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

import app.core.database  # noqa: F401  installs tenant session hooks
from app.core.capabilities import Capability, has_capability
from app.core.errors import ApiError, SyncRejected
from app.models.batch import BatchItem, PurchaseBatch
from app.models.business_settings import BusinessSettings
from app.models.inventory import InventoryLevel, StockMovement
from app.models.pharmacy import PharmacyProductDetails
from app.models.pharmacy_lots import (
    BatchItemEvent,
    PharmacistAuthorization,
    PharmacyGovernanceOfficer,
    PharmacyRecall,
    PharmacyRecallLot,
    PharmacySupplierReturn,
    PharmacySupplierReturnLine,
)
from app.models.product import Product
from app.models.return_item import ReturnItem
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sale_return import SaleReturn
from app.models.sale_tender import SaleTender
from app.models.store import Store
from app.models.sync_event import SyncEvent
from app.models.user import Role, User
from app.services.batch_ledger import link_sale, restore_sale_item
from app.services.inventory import move_stock
from app.services.pharmacy_lots import hold_customer_return, open_recall, return_to_supplier, strict_sale_candidates
from app.services.settings_service import cached_settings
from app.tenancy.context import TenantRef, use_tenant
from app.tenancy.scoping import INCLUDE_ALL

OPS_DB = "stage3f2_ops"
MIGRATE_DB = "stage3f2_from_0119"
PREVIOUS = "20261119_0119"
HEAD = "20261119_0120"
TENANT_A = uuid.UUID("11111111-1111-4111-8111-111111111111")
TENANT_B = uuid.UUID("22222222-2222-4222-8222-222222222222")
EXPIRY = date.today() + timedelta(days=120)
RESULTS: list[dict[str, object]] = []


def _url():
    raw = os.environ.get("DATABASE_URL", "")
    url = make_url(raw)
    if url.host != "127.0.0.1" or url.port != 55444 or url.username != "axizpos_3f2":
        raise SystemExit("Refusing: this script only opens the disposable 3F.2 container.")
    if url.database in {"ai_pos", "axizpos_pharmacy_acceptance"}:
        raise SystemExit("Refusing: database name is not disposable.")
    return url


def _upgrade(url: str, revision: str) -> None:
    config = Config("alembic.ini")
    config.attributes["database_url"] = url
    command.upgrade(config, revision)


def _sqlstate(exc: BaseException) -> str | None:
    orig = getattr(exc, "orig", None)
    if orig is None:
        return None
    return getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)


def record(test_id: str, ok: bool, expected: str, actual: str, evidence: str) -> None:
    RESULTS.append(
        {
            "id": test_id,
            "result": "PASSED" if ok else "FAILED",
            "expected": expected,
            "actual": actual,
            "evidence": evidence,
        }
    )
    print(f"{'PASS' if ok else 'FAIL'} {test_id}: {actual}")


def identity(db) -> dict[str, object]:
    row = db.execute(
        text(
            "SELECT current_user, session_user, "
            "(SELECT rolsuper FROM pg_roles WHERE rolname = current_user), "
            "(SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user), "
            "current_setting('app.tenant_id', true)"
        )
    ).one()
    info = {
        "current_user": row[0],
        "session_user": row[1],
        "rolsuper": bool(row[2]),
        "rolbypassrls": bool(row[3]),
        "tenant_setting": row[4] or "",
    }
    if info["current_user"] != "ai_pos_app" or info["session_user"] != "ai_pos_app":
        raise RuntimeError(f"not an application login: {info}")
    if info["rolsuper"] or info["rolbypassrls"]:
        raise RuntimeError(f"application role is privileged: {info}")
    return info


def tenant_ref(tenant_id: uuid.UUID, url: str) -> TenantRef:
    slug = "pharmacy-a" if tenant_id == TENANT_A else "grocery-b"
    return TenantRef(id=str(tenant_id), slug=slug, name=slug, database_url=url, data_plane="shared")


def main() -> None:
    admin_url = _url()
    app_password = os.environ["AXIZPOS_3F2_APP_PW"]
    if not app_password.isalnum():
        raise SystemExit("Application password must be alphanumeric.")
    maintenance = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with maintenance.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {OPS_DB}"))
        conn.execute(text("DROP ROLE IF EXISTS ai_pos_app"))
        conn.execute(text(f"CREATE DATABASE {OPS_DB}"))
        # CREATE ROLE does not accept a bound parameter. The password is alphanumeric.
        conn.exec_driver_sql(
            f"CREATE ROLE ai_pos_app LOGIN PASSWORD '{app_password}' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
        )
    maintenance.dispose()

    ops_admin = admin_url.set(database=OPS_DB)
    _upgrade(ops_admin.render_as_string(hide_password=False), "head")
    admin_engine = create_engine(ops_admin)
    with admin_engine.begin() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        conn.execute(text(f"GRANT CONNECT ON DATABASE {OPS_DB} TO ai_pos_app"))
        conn.execute(text("GRANT USAGE ON SCHEMA public TO ai_pos_app"))
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ai_pos_app"))
        conn.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ai_pos_app"))
        role = conn.execute(
            text("SELECT rolsuper, rolbypassrls, rolcanlogin, rolcreatedb FROM pg_roles WHERE rolname = 'ai_pos_app'")
        ).one()
    print(f"database={OPS_DB} port=55444 alembic={version} role_flags={tuple(role)}")
    if version != HEAD or any(role[:2]) or not role[2]:
        raise SystemExit("Role or migration head is not the expected application setup.")

    app_engine = create_engine(ops_admin.set(username="ai_pos_app", password=app_password), pool_size=12)
    Admin = sessionmaker(bind=admin_engine, expire_on_commit=False)
    App = sessionmaker(bind=app_engine, expire_on_commit=False)
    scope_a = tenant_ref(TENANT_A, ops_admin.render_as_string(hide_password=True))
    scope_b = tenant_ref(TENANT_B, ops_admin.render_as_string(hide_password=True))

    store_a, users_a = _seed_tenant(Admin, TENANT_A, "pharmacy", "WH-A")
    store_b, users_b = _seed_tenant(Admin, TENANT_B, "grocery", "WH-B")
    _prove_login(App, scope_a, scope_b)
    _supplier_races(Admin, App, scope_a, store_a, users_a[0])
    _customer_races(Admin, App, scope_a, scope_b, store_a, store_b, users_a[0], users_b[0])
    _multiline(Admin, App, scope_a, store_a, users_a[0])
    _recall_versus_sale(admin_engine, Admin, App, scope_a, store_a, users_a[0])
    _rls(admin_engine, App, scope_a, scope_b)
    _performance(admin_engine, Admin, App, scope_a, store_a, users_a[0])
    _migration(admin_url, app_password)
    admin_engine.dispose()
    app_engine.dispose()
    failed = [row["id"] for row in RESULTS if row["result"] != "PASSED"]
    print(f"SUMMARY passed={len(RESULTS) - len(failed)} failed={len(failed)}")
    if failed:
        raise SystemExit(f"failed: {failed}")


def _seed_tenant(Admin, tenant_id: uuid.UUID, profile: str, code: str) -> tuple[uuid.UUID, list[uuid.UUID]]:
    db = Admin()
    db.info[INCLUDE_ALL] = True
    store_id = uuid.uuid4()
    user_ids = [uuid.uuid4() for _ in range(3)]
    slug = str(tenant_id)[:8]
    with use_tenant(tenant_ref(tenant_id, "seed")):
        role = Role(tenant_id=tenant_id, name=f"Cashier {slug}")
        db.add(role)
        db.flush()
        db.add(
            BusinessSettings(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                currency="USD",
                business_profile=profile,
                capabilities=None,
            )
        )
        db.add(Store(id=store_id, tenant_id=tenant_id, code=code, name=code, currency="USD"))
        for index, user_id in enumerate(user_ids):
            db.add(
                User(
                    id=user_id,
                    tenant_id=tenant_id,
                    username=f"user-{slug}-{index}",
                    email=f"user-{slug}-{index}@example.test",
                    full_name=f"User {index}",
                    role_id=role.id,
                )
            )
        db.flush()
        db.add(
            PharmacyGovernanceOfficer(
                tenant_id=tenant_id,
                user_id=user_ids[1],
                requested_by_id=user_ids[0],
                reason="Stage 3F.2 isolation row",
                status="PENDING",
            )
        )
        db.add(
            PharmacistAuthorization(
                tenant_id=tenant_id,
                user_id=user_ids[2],
                requested_by_id=user_ids[0],
                granted_by_id=user_ids[1],
                reason="Stage 3F.2 isolation row",
                status="PENDING",
                approval_basis="TWO_PERSON",
            )
        )
        db.commit()
    db.close()
    return store_id, user_ids


def _layer(
    db,
    *,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    store_id: uuid.UUID,
    user_id: uuid.UUID,
    quantity: int,
    status: str | None,
    lot: str,
    medicine: bool,
    expiry: date | None = None,
    recall_id: uuid.UUID | None = None,
) -> uuid.UUID:
    batch = PurchaseBatch(
        tenant_id=tenant_id,
        batch_number=f"B-{uuid.uuid4().hex[:10]}",
        store_id=store_id,
        import_source="MANUAL",
        currency="USD",
        status="ACTIVE",
        total_cost_amount=quantity * 100,
        total_items_count=quantity,
        created_by_id=user_id,
    )
    db.add(batch)
    db.flush()
    item = BatchItem(
        tenant_id=tenant_id,
        batch_id=batch.id,
        product_id=product_id,
        store_id=store_id,
        quantity_imported=quantity,
        quantity_remaining=quantity,
        purchase_cost_per_unit=100,
        selling_price_per_unit=1500,
        expiry_date=expiry or EXPIRY,
        manufacturer_lot=lot,
        lot_status=status,
        recall_id=recall_id,
        recall_reason="Controlled recall" if recall_id is not None else None,
        imported_serials=[],
    )
    db.add(item)
    db.flush()
    if medicine and status is not None:
        db.add(
            BatchItemEvent(
                tenant_id=tenant_id,
                batch_item_id=item.id,
                action="RECEIVED" if status == "UNRELEASED" else "RELEASED",
                to_status=status,
                user_id=user_id,
            )
        )
    return item.id


def _product(
    db,
    *,
    tenant_id: uuid.UUID,
    store_id: uuid.UUID,
    user_id: uuid.UUID,
    name: str,
    quantity: int,
    status: str | None,
    medicine: bool,
    lot: str = "LOT-1",
) -> tuple[uuid.UUID, uuid.UUID]:
    product_id = uuid.uuid4()
    db.add(
        Product(
            id=product_id,
            tenant_id=tenant_id,
            sku=f"SKU-{product_id.hex[:8]}",
            barcode=f"629{product_id.int % 10**10:010d}"[:13],
            name=name,
            category="Medicine" if medicine else "Grocery",
            price_cents=1500,
            currency="USD",
        )
    )
    db.flush()
    if medicine:
        db.add(
            PharmacyProductDetails(
                product_id=product_id,
                tenant_id=tenant_id,
                product_kind="MEDICINE",
                dispensing_class="PRESCRIPTION",
            )
        )
    db.add(
        InventoryLevel(
            tenant_id=tenant_id,
            product_id=product_id,
            store_id=store_id,
            quantity_on_hand=quantity,
        )
    )
    db.flush()
    layer_id = _layer(
        db,
        tenant_id=tenant_id,
        product_id=product_id,
        store_id=store_id,
        user_id=user_id,
        quantity=quantity,
        status=status,
        lot=lot,
        medicine=medicine,
    )
    return product_id, layer_id


def _app(App):
    db = App()
    db.info.pop(INCLUDE_ALL, None)
    return db


def _prove_login(App, scope_a: TenantRef, scope_b: TenantRef) -> None:
    db = _app(App)
    try:
        with use_tenant(scope_a):
            info = identity(db)
            profile = cached_settings(db).business_profile
            pharmacy = has_capability(db, Capability.PHARMACY_CATALOG)
        record(
            "3F2-LOGIN",
            profile == "pharmacy" and pharmacy,
            "ai_pos_app login, session_user matches, pharmacy tenant context",
            f"{info} profile={profile} pharmacy_catalog={pharmacy}",
            "current_user and session_user are both ai_pos_app",
        )
    finally:
        db.close()
    db = _app(App)
    try:
        with use_tenant(scope_b):
            identity(db)
            profile = cached_settings(db).business_profile
            pharmacy = has_capability(db, Capability.PHARMACY_CATALOG)
        record(
            "3F2-LOGIN-B",
            profile == "grocery" and not pharmacy,
            "Grocery tenant context does not enable the pharmacy catalogue",
            f"profile={profile} pharmacy_catalog={pharmacy}",
            "settings row for tenant B",
        )
    finally:
        db.close()


def _run_pair(calls: list) -> list[tuple[str, str]]:
    barrier = threading.Barrier(len(calls))
    out: list[tuple[str, str]] = []
    lock = threading.Lock()

    def wrap(fn) -> None:
        try:
            barrier.wait(10)
            result = fn()
        except Exception as exc:  # noqa: BLE001
            result = (type(exc).__name__, f"{exc} sqlstate={_sqlstate(exc)}")
        with lock:
            out.append(result)

    threads = [threading.Thread(target=wrap, args=(fn,)) for fn in calls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return out


def _supplier_races(Admin, App, scope, store_id, user_id) -> None:
    db = Admin()
    db.info[INCLUDE_ALL] = True
    with use_tenant(scope):
        full_product, full_layer = _product(
            db,
            tenant_id=TENANT_A,
            store_id=store_id,
            user_id=user_id,
            name="Full return",
            quantity=5,
            status="UNRELEASED",
            medicine=True,
            lot="FULL",
        )
        part_product, part_layer = _product(
            db,
            tenant_id=TENANT_A,
            store_id=store_id,
            user_id=user_id,
            name="Partial return",
            quantity=6,
            status="UNRELEASED",
            medicine=True,
            lot="PART",
        )
        recall = PharmacyRecall(
            tenant_id=TENANT_A,
            reference="SEED-RECALL",
            source_text="Stage 3F.2",
            severity="high",
            reason="Seed a recalled layer",
            status="OPEN",
            opened_by_id=user_id,
        )
        db.add(recall)
        db.flush()
        recalled_product = uuid.uuid4()
        db.add(
            Product(
                id=recalled_product,
                tenant_id=TENANT_A,
                sku=f"SKU-{recalled_product.hex[:8]}",
                barcode=f"629{recalled_product.int % 10**10:010d}"[:13],
                name="Recalled partial",
                category="Medicine",
                price_cents=1500,
                currency="USD",
            )
        )
        db.flush()
        db.add(
            PharmacyProductDetails(
                product_id=recalled_product,
                tenant_id=TENANT_A,
                product_kind="MEDICINE",
                dispensing_class="PRESCRIPTION",
            )
        )
        db.add(
            InventoryLevel(
                tenant_id=TENANT_A,
                product_id=recalled_product,
                store_id=store_id,
                quantity_on_hand=4,
            )
        )
        db.flush()
        recalled_layer = _layer(
            db,
            tenant_id=TENANT_A,
            product_id=recalled_product,
            store_id=store_id,
            user_id=user_id,
            quantity=4,
            status="RECALLED",
            lot="RECALL-SR",
            medicine=True,
            recall_id=recall.id,
        )
        db.commit()
    db.close()

    def one_return(layer_id: uuid.UUID, quantity: int, reference: str) -> tuple[str, str]:
        session = _app(App)
        try:
            with use_tenant(scope):
                info = identity(session)
                return_to_supplier(
                    session,
                    reference=reference,
                    reason="Short dated delivery",
                    lines=[(layer_id, quantity)],
                    user_id=user_id,
                )
            return ("ok", str(info["session_user"]))
        except (ApiError, SyncRejected) as exc:
            session.rollback()
            code = getattr(exc, "code", None) or getattr(exc, "message", str(exc))
            return (type(exc).__name__, str(code))
        finally:
            session.close()

    full = _run_pair(
        [
            lambda: one_return(full_layer, 5, "SR-FULL-1"),
            lambda: one_return(full_layer, 5, "SR-FULL-2"),
        ]
    )
    part = _run_pair(
        [
            lambda: one_return(part_layer, 2, "SR-PART-1"),
            lambda: one_return(part_layer, 2, "SR-PART-2"),
        ]
    )
    recalled = one_return(recalled_layer, 1, "SR-RECALL-PART")
    opened = _layer_evidence(App, scope, [part_layer])[str(part_layer)]
    closing = one_return(part_layer, 2, "SR-PART-CLOSE")
    evidence = _layer_evidence(App, scope, [full_layer, part_layer, recalled_layer])
    documents = _admin_counts(Admin, full_product, part_product, recalled_product)
    full_ok = [item for item in full if item[0] == "ok"]
    record(
        "3F2-SR-FULL",
        len(full_ok) == 1 and len(full) == 2 and evidence[str(full_layer)]["remaining"] == 0 and evidence[str(full_layer)]["status"] == "SUPPLIER_RETURN" and documents["full_docs"] == 1 and documents["full_moves"] == 1,
        "One full return, loser rejected, remaining 0, status SUPPLIER_RETURN, one movement",
        f"attempts={full} layer={evidence[str(full_layer)]} docs={documents['full_docs']} moves={documents['full_moves']}",
        "ai_pos_app sessions",
    )
    record(
        "3F2-SR-PARTIAL",
        all(item[0] == "ok" for item in part)
        and opened["remaining"] == 2
        and opened["status"] == "UNRELEASED"
        and closing[0] == "ok"
        and evidence[str(part_layer)]["remaining"] == 0
        and evidence[str(part_layer)]["status"] == "SUPPLIER_RETURN"
        and documents["part_moves"] == 3,
        "Two partial returns leave the original UNRELEASED status, then the last units set SUPPLIER_RETURN",
        f"partial={part} opened={opened} close={closing} layer={evidence[str(part_layer)]} moves={documents['part_moves']}",
        "lot_status after the partial returns and after the closing return",
    )
    record(
        "3F2-SR-STATUS",
        recalled[0] == "ok" and evidence[str(recalled_layer)]["status"] == "RECALLED" and evidence[str(recalled_layer)]["remaining"] == 3,
        "A partial supplier return leaves a recalled layer recalled",
        f"attempt={recalled} layer={evidence[str(recalled_layer)]}",
        "lot_status after the return",
    )


def _layer_evidence(App, scope, layer_ids: list[uuid.UUID]) -> dict[str, dict[str, object]]:
    db = _app(App)
    found: dict[str, dict[str, object]] = {}
    with use_tenant(scope):
        identity(db)
        rows = db.scalars(select(BatchItem).where(BatchItem.id.in_(layer_ids))).all()
        for row in rows:
            found[str(row.id)] = {"remaining": row.quantity_remaining, "status": row.lot_status}
    db.close()
    return found


def _admin_counts(Admin, full_product, part_product, recalled_product) -> dict[str, int]:
    db = Admin()
    db.info[INCLUDE_ALL] = True

    def docs(product_id: uuid.UUID) -> int:
        return int(
            db.scalar(
                select(func.count(PharmacySupplierReturnLine.id)).where(PharmacySupplierReturnLine.product_id == product_id)
            )
            or 0
        )

    def moves(product_id: uuid.UUID) -> int:
        return int(
            db.scalar(
                select(func.count(StockMovement.id)).where(
                    StockMovement.product_id == product_id,
                    StockMovement.movement_type == "PURCHASE_REVERSAL",
                )
            )
            or 0
        )

    out = {
        "full_docs": docs(full_product),
        "full_moves": moves(full_product),
        "part_moves": moves(part_product),
        "recalled_moves": moves(recalled_product),
    }
    db.close()
    return out


def _sell(App, scope, product_id, store_id, user_id, quantity: int) -> tuple[uuid.UUID, uuid.UUID]:
    db = _app(App)
    sale_id = uuid.uuid4()
    item_id = uuid.uuid4()
    try:
        with use_tenant(scope):
            identity(db)
            move_stock(
                db,
                product_id=product_id,
                store_id=store_id,
                quantity=-quantity,
                movement_type="SALE_OUT",
                reference_type="sale",
                reference_id=sale_id,
                user_id=user_id,
            )
            db.add(
                Sale(
                    id=sale_id,
                    tenant_id=uuid.UUID(scope.id),
                    store_id=store_id,
                    cashier_id=user_id,
                    status="completed",
                    currency="USD",
                    payment_method="cash",
                    subtotal_cents=1500 * quantity,
                    tax_cents=0,
                    total_cents=1500 * quantity,
                    client_sale_id=str(sale_id),
                    sale_type="RETAIL",
                    payment_status="PAID",
                    amount_paid_cents=1500 * quantity,
                    due_balance_cents=0,
                )
            )
            db.add(
                SaleItem(
                    id=item_id,
                    tenant_id=uuid.UUID(scope.id),
                    sale_id=sale_id,
                    product_id=product_id,
                    quantity=quantity,
                    unit_price_cents=1500,
                    tax_cents=0,
                    line_total_cents=1500 * quantity,
                )
            )
            db.flush()
            link_sale(db, sale_id)
            db.commit()
        return sale_id, item_id
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _accept_return(App, scope, sale_id, sale_item_id, store_id, user_id, quantity: int) -> tuple[str, str]:
    db = _app(App)
    try:
        with use_tenant(scope):
            identity(db)
            sale = db.scalar(select(Sale).where(Sale.id == sale_id).with_for_update())
            item = db.get(SaleItem, sale_item_id)
            if sale is None or item is None:
                raise SyncRejected("Original sale is not visible.")
            already = int(
                db.scalar(select(func.coalesce(func.sum(ReturnItem.quantity), 0)).where(ReturnItem.sale_item_id == item.id))
                or 0
            )
            if quantity > item.quantity - already:
                raise SyncRejected("Return quantity exceeds what is left to return on this line.")
            document = SaleReturn(
                tenant_id=uuid.UUID(scope.id),
                original_sale_id=sale.id,
                store_id=store_id,
                cashier_id=user_id,
                currency="USD",
                subtotal_cents=1500 * quantity,
                tax_refund_cents=0,
                restocking_fee_cents=0,
                total_refund_cents=1500 * quantity,
                refund_method="cash",
                reason_notes="Customer return verification",
            )
            db.add(document)
            db.flush()
            db.add(
                ReturnItem(
                    tenant_id=uuid.UUID(scope.id),
                    return_id=document.id,
                    sale_item_id=item.id,
                    product_id=item.product_id,
                    quantity=quantity,
                    unit_price_cents=1500,
                    tax_refund_cents=0,
                    restocking_fee_cents=0,
                    refund_cents=1500 * quantity,
                    condition_status="unopened_resealable",
                    reason_code="changed_mind",
                )
            )
            move_stock(
                db,
                product_id=item.product_id,
                store_id=store_id,
                quantity=quantity,
                movement_type="RETURN_IN",
                reference_type="sale_return",
                reference_id=document.id,
                user_id=user_id,
            )
            restore_sale_item(db, sale_item_id=item.id, store_id=store_id, quantity=quantity)
            hold_customer_return(db, sale_item_id=item.id, store_id=store_id, user_id=user_id)
            db.commit()
        return ("ok", str(document.id))
    except (ApiError, SyncRejected) as exc:
        db.rollback()
        return (type(exc).__name__, str(exc))
    finally:
        db.close()


def _customer_races(Admin, App, scope_a, scope_b, store_a, store_b, user_a, user_b) -> None:
    db = Admin()
    db.info[INCLUDE_ALL] = True
    with use_tenant(scope_a):
        product, layer = _product(
            db,
            tenant_id=TENANT_A,
            store_id=store_a,
            user_id=user_a,
            name="Return medicine",
            quantity=4,
            status="RELEASED",
            medicine=True,
            lot="RET-1",
        )
        preserved = {}
        for status in ("RECALLED", "UNRELEASED", "DAMAGED", "SUPPLIER_RETURN"):
            preserved[status] = _product(
                db,
                tenant_id=TENANT_A,
                store_id=store_a,
                user_id=user_a,
                name=f"Keep {status}",
                quantity=2,
                status="RELEASED",
                medicine=True,
                lot=f"KEEP-{status}",
            )
        db.commit()
    with use_tenant(scope_b):
        grocery, grocery_layer = _product(
            db,
            tenant_id=TENANT_B,
            store_id=store_b,
            user_id=user_b,
            name="Grocery rice",
            quantity=3,
            status=None,
            medicine=False,
            lot="RICE",
        )
        db.commit()
    db.close()

    sale_id, item_id = _sell(App, scope_a, product, store_a, user_a, 2)
    attempts = _run_pair(
        [
            lambda: _accept_return(App, scope_a, sale_id, item_id, store_a, user_a, 1),
            lambda: _accept_return(App, scope_a, sale_id, item_id, store_a, user_a, 1),
        ]
    )
    extra = _accept_return(App, scope_a, sale_id, item_id, store_a, user_a, 1)
    blocked = _sell_result(App, scope_a, product, store_a, user_a, 1)
    evidence = _layer_evidence(App, scope_a, [layer])
    movements = _movement_count(Admin, product, "RETURN_IN")
    audits = _audit_count(Admin, "pharmacy.lot_quarantined")
    record(
        "3F2-CR-RACE",
        sorted(item[0] for item in attempts) == ["ok", "ok"]
        and extra[0] != "ok"
        and evidence[str(layer)]["status"] == "QUARANTINED"
        and evidence[str(layer)]["remaining"] == 4
        and movements == 2
        and blocked[0] != "ok",
        "Two one-unit returns succeed, a third is rejected, the whole layer is quarantined, and it cannot be sold",
        f"attempts={attempts} extra={extra} layer={evidence[str(layer)]} return_movements={movements} resale={blocked} audits={audits}",
        "sale row lock, return items, RETURN_IN movements, QUARANTINED",
    )

    kept = {}
    for status, (kept_product, kept_layer) in preserved.items():
        kept_sale, kept_item = _sell(App, scope_a, kept_product, store_a, user_a, 1)
        session = _app(App)
        with use_tenant(scope_a):
            identity(session)
            row = session.get(BatchItem, kept_layer)
            if status == "RECALLED":
                recall = PharmacyRecall(
                    tenant_id=TENANT_A,
                    reference=f"KEEP-{kept_layer.hex[:8]}",
                    source_text="Stage 3F.2",
                    severity="high",
                    reason="Status must stay recalled",
                    status="OPEN",
                    opened_by_id=user_a,
                )
                session.add(recall)
                session.flush()
                row.recall_id = recall.id
                row.recall_reason = "Status must stay recalled"
            row.lot_status = status
            session.flush()
            hold_customer_return(session, sale_item_id=kept_item, store_id=store_a, user_id=user_a)
            session.commit()
        session.close()
        kept[status] = _layer_evidence(App, scope_a, [kept_layer])[str(kept_layer)]
        _ = kept_sale
    record(
        "3F2-CR-STATUS",
        all(kept[status]["status"] == status for status in kept),
        "Customer-return hold does not overwrite recalled, unreleased, damaged, or supplier-return layers",
        str(kept),
        "lot_status after hold_customer_return",
    )

    g_sale, g_item = _sell(App, scope_b, grocery, store_b, user_b, 1)
    g_return = _accept_return(App, scope_b, g_sale, g_item, store_b, user_b, 1)
    g_layer = _layer_evidence(App, scope_b, [grocery_layer])[str(grocery_layer)]
    g_resale = _sell_result(App, scope_b, grocery, store_b, user_b, 1)
    record(
        "3F2-CR-GROCERY",
        g_return[0] == "ok" and g_layer["status"] is None and g_layer["remaining"] == 3 and g_resale[0] == "ok",
        "A grocery return restores quantity and does not quarantine the layer",
        f"return={g_return} layer={g_layer} resale={g_resale}",
        "tenant B, no pharmacy details",
    )


def _sell_result(App, scope, product_id, store_id, user_id, quantity: int) -> tuple[str, str]:
    try:
        sale_id, _item = _sell(App, scope, product_id, store_id, user_id, quantity)
        return ("ok", str(sale_id))
    except (SyncRejected, ApiError) as exc:
        return (type(exc).__name__, f"{getattr(exc, 'code', '')} {exc}")


def _movement_count(Admin, product_id: uuid.UUID, movement_type: str) -> int:
    db = Admin()
    db.info[INCLUDE_ALL] = True
    count = int(
        db.scalar(
            select(func.count(StockMovement.id)).where(
                StockMovement.product_id == product_id,
                StockMovement.movement_type == movement_type,
            )
        )
        or 0
    )
    db.close()
    return count


def _audit_count(Admin, action: str) -> int:
    db = Admin()
    db.info[INCLUDE_ALL] = True
    count = int(db.execute(text("SELECT count(*) FROM audit_logs WHERE action = :action"), {"action": action}).scalar() or 0)
    db.close()
    return count


def _multiline(Admin, App, scope, store_id, user_id) -> None:
    db = Admin()
    db.info[INCLUDE_ALL] = True
    with use_tenant(scope):
        good, _good_layer = _product(
            db,
            tenant_id=TENANT_A,
            store_id=store_id,
            user_id=user_id,
            name="First medicine",
            quantity=3,
            status="RELEASED",
            medicine=True,
            lot="LINE-1",
        )
        bad, _bad_layer = _product(
            db,
            tenant_id=TENANT_A,
            store_id=store_id,
            user_id=user_id,
            name="Second medicine",
            quantity=3,
            status="UNRELEASED",
            medicine=True,
            lot="LINE-2",
        )
        db.commit()
    before_sync = int(db.scalar(select(func.count(SyncEvent.id))) or 0)
    db.close()
    session = _app(App)
    sale_id = uuid.uuid4()
    outcome = "committed"
    try:
        with use_tenant(scope):
            identity(session)
            session.add(
                Sale(
                    id=sale_id,
                    tenant_id=TENANT_A,
                    store_id=store_id,
                    cashier_id=user_id,
                    status="completed",
                    currency="USD",
                    payment_method="cash",
                    subtotal_cents=4500,
                    tax_cents=0,
                    total_cents=4500,
                    client_sale_id=str(sale_id),
                    sale_type="RETAIL",
                    payment_status="PAID",
                    amount_paid_cents=4500,
                    due_balance_cents=0,
                )
            )
            session.add(
                SaleTender(
                    tenant_id=TENANT_A,
                    sale_id=sale_id,
                    method="cash",
                    amount_cents=4500,
                )
            )
            move_stock(
                session,
                product_id=good,
                store_id=store_id,
                quantity=-2,
                movement_type="SALE_OUT",
                reference_type="sale",
                reference_id=sale_id,
                user_id=user_id,
            )
            move_stock(
                session,
                product_id=bad,
                store_id=store_id,
                quantity=-1,
                movement_type="SALE_OUT",
                reference_type="sale",
                reference_id=sale_id,
                user_id=user_id,
            )
            session.commit()
    except SyncRejected as exc:
        session.rollback()
        outcome = f"{exc.code}:{exc}"
    finally:
        session.close()
    check = Admin()
    check.info[INCLUDE_ALL] = True
    good_on = check.scalar(select(InventoryLevel.quantity_on_hand).where(InventoryLevel.product_id == good))
    bad_on = check.scalar(select(InventoryLevel.quantity_on_hand).where(InventoryLevel.product_id == bad))
    sale_left = check.get(Sale, sale_id)
    tender_left = check.scalar(select(func.count(SaleTender.id)).where(SaleTender.sale_id == sale_id))
    moves = check.scalar(select(func.count(StockMovement.id)).where(StockMovement.reference_id == sale_id))
    sync_after = int(check.scalar(select(func.count(SyncEvent.id))) or 0)
    check.close()
    record(
        "3F2-ROLLBACK",
        outcome.startswith("lot_unreleased") and good_on == 3 and bad_on == 3 and sale_left is None and tender_left == 0 and moves == 0 and sync_after == before_sync,
        "An ineligible later line rolls back the earlier allocation, sale, tender, and movements",
        f"outcome={outcome} good={good_on} bad={bad_on} sale_left={sale_left is not None} tenders={tender_left} movements={moves} sync={sync_after}",
        "one ai_pos_app transaction",
    )


def _recall_versus_sale(admin_engine, Admin, App, scope, store_id, user_id) -> None:
    db = Admin()
    db.info[INCLUDE_ALL] = True
    with use_tenant(scope):
        first, first_layer = _product(
            db,
            tenant_id=TENANT_A,
            store_id=store_id,
            user_id=user_id,
            name="Recall first",
            quantity=4,
            status="RELEASED",
            medicine=True,
            lot="RECALL-FIRST",
        )
        second, second_layer = _product(
            db,
            tenant_id=TENANT_A,
            store_id=store_id,
            user_id=user_id,
            name="Sale holds lock",
            quantity=4,
            status="RELEASED",
            medicine=True,
            lot="SALE-HOLDS",
        )
        db.commit()
    db.close()
    recall_first = _recall(App, scope, first, "RECALL-FIRST", user_id, "RF-1")
    sale_after = _sell_result(App, scope, first, store_id, user_id, 1)
    after = _layer_evidence(App, scope, [first_layer])[str(first_layer)]
    record(
        "3F2-RECALL-FIRST",
        recall_first[0] == "ok" and sale_after[0] != "ok" and after["remaining"] == 4 and after["status"] == "RECALLED",
        "A lot recalled before the sale's validation cannot be sold, and its quantity stays unchanged",
        f"recall={recall_first} sale={sale_after} layer={after}",
        "open_recall committed before move_stock",
    )

    locked = threading.Event()
    samples: list[str] = []

    def sale_holds() -> tuple[str, str]:
        session = _app(App)
        try:
            with use_tenant(scope):
                identity(session)
                move_stock(
                    session,
                    product_id=second,
                    store_id=store_id,
                    quantity=-1,
                    movement_type="SALE_OUT",
                    reference_type="sale",
                    reference_id=uuid.uuid4(),
                    user_id=user_id,
                )
                locked.set()
                time.sleep(1.2)
                session.commit()
            return ("sale_committed", "held batch row lock before commit")
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            return (type(exc).__name__, str(exc))
        finally:
            session.close()

    def recall_waits() -> tuple[str, str]:
        if not locked.wait(10):
            return ("timeout", "sale never locked")
        return _recall(App, scope, second, "SALE-HOLDS", user_id, "RF-2")

    def sample() -> None:
        if not locked.wait(10):
            return
        started = time.perf_counter()
        while time.perf_counter() - started < 1.0:
            with admin_engine.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT wait_event_type, wait_event, state FROM pg_stat_activity "
                        "WHERE datname = :name AND pid <> pg_backend_pid() AND state <> 'idle'"
                    ),
                    {"name": OPS_DB},
                ).all()
            samples.append("; ".join(f"{row[0]}/{row[1]}/{row[2]}" for row in rows) or "none")
            if any(row[0] == "Lock" for row in rows):
                break
            time.sleep(0.05)

    outcomes: list[tuple[str, str]] = []
    lock = threading.Lock()

    def wrap(fn) -> None:
        result = fn()
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=wrap, args=(fn,)) for fn in (sale_holds, recall_waits)]
    threads.append(threading.Thread(target=sample))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(20)
    later = _layer_evidence(App, scope, [second_layer])[str(second_layer)]
    follow = _sell_result(App, scope, second, store_id, user_id, 1)
    moves = _movement_count(Admin, second, "SALE_OUT")
    record(
        "3F2-RECALL-INFLIGHT",
        any(item[0] == "sale_committed" for item in outcomes)
        and any(item[0] == "ok" for item in outcomes)
        and later["remaining"] == 3
        and later["status"] == "RECALLED"
        and follow[0] != "ok"
        and moves == 1,
        "The sale that already locked the layer commits; the recall waits, then marks the remaining units recalled",
        f"outcomes={outcomes} layer={later} follow={follow} movements={moves} waits={samples[:4]}",
        "FOR UPDATE on the layer, then recall update",
    )


def _recall(App, scope, product_id, lot: str, user_id, reference: str) -> tuple[str, str]:
    db = _app(App)
    try:
        with use_tenant(scope):
            identity(db)
            open_recall(
                db,
                reference=reference,
                source_text="Stage 3F.2",
                severity="high",
                reason="Controlled recall verification",
                lots=[(product_id, lot)],
                user_id=user_id,
            )
        return ("ok", reference)
    except (ApiError, SyncRejected) as exc:
        db.rollback()
        return (type(exc).__name__, str(exc))
    finally:
        db.close()


def _rls(admin_engine, App, scope_a, scope_b) -> None:
    db = _app(App)
    with use_tenant(scope_a):
        info = identity(db)
        own = _visible(db)
    db.close()
    db = _app(App)
    with use_tenant(scope_b):
        other = _visible(db)
        try:
            db.execute(
                text(
                    "INSERT INTO pharmacy_recalls (id, tenant_id, reference, source_text, severity, reason, status, created_at) "
                    "VALUES (:id, :tenant, 'CROSS', 'x', 'high', 'no', 'OPEN', now())"
                ),
                {"id": uuid.uuid4(), "tenant": str(TENANT_A)},
            )
            db.commit()
            cross = "inserted"
            state = None
        except DBAPIError as exc:
            db.rollback()
            cross = type(exc).__name__
            state = _sqlstate(exc)
    db.close()
    raw = app_connection_state(App, "")
    bypass = app_bypass_does_not_widen(App, scope_b)
    record(
        "3F2-RLS",
        own["products"] >= 1
        and other["products"] >= 1
        and own["recalls_cross_visible"] == 0
        and state == "42501"
        and raw["sqlstate"] == "42501"
        and raw["empty_products"] == 0
        and bypass == 0
        and info["session_user"] == "ai_pos_app",
        "Own rows are visible, cross-tenant insert and a missing tenant insert raise SQLSTATE 42501, and bypass does not widen the application role",
        f"tenant_a={own} tenant_b={other} cross={cross} sqlstate={state} empty={raw} bypass_other_products={bypass}",
        "login ai_pos_app, not SET ROLE",
    )


def _visible(db) -> dict[str, int]:
    tables = {
        "lots": BatchItem,
        "events": BatchItemEvent,
        "recalls": PharmacyRecall,
        "recall_lots": PharmacyRecallLot,
        "authorizations": PharmacistAuthorization,
        "officers": PharmacyGovernanceOfficer,
        "supplier_returns": PharmacySupplierReturn,
        "supplier_lines": PharmacySupplierReturnLine,
        "products": Product,
        "inventory": InventoryLevel,
    }
    out = {name: int(db.scalar(select(func.count()).select_from(model)) or 0) for name, model in tables.items()}
    out["recalls_cross_visible"] = int(
        db.scalar(select(func.count()).select_from(PharmacyRecall).where(PharmacyRecall.tenant_id == TENANT_B)) or 0
    )
    return out


def app_connection_state(App, tenant_value: str) -> dict[str, object]:
    engine = App.kw["bind"]
    sqlstate = None
    products = None
    with engine.connect() as conn:
        trans = conn.begin()
        conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenant_value})
        conn.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))
        products = conn.execute(text("SELECT count(*) FROM products")).scalar()
        try:
            conn.execute(
                text(
                    "INSERT INTO pharmacy_recalls (id, tenant_id, reference, source_text, severity, reason, status, created_at) "
                    "VALUES (:id, :tenant, 'EMPTY', 'x', 'high', 'no', 'OPEN', now())"
                ),
                {"id": uuid.uuid4(), "tenant": str(TENANT_A)},
            )
        except DBAPIError as exc:
            sqlstate = _sqlstate(exc)
        trans.rollback()
    return {"sqlstate": sqlstate, "empty_products": int(products or 0)}


def app_bypass_does_not_widen(App, scope_b) -> int:
    db = _app(App)
    with use_tenant(scope_b):
        identity(db)
        db.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        count = int(db.scalar(select(func.count()).select_from(Product).where(Product.tenant_id == TENANT_A)) or 0)
    db.close()
    return count


def _performance(admin_engine, Admin, App, scope, store_id, user_id) -> None:
    db = Admin()
    db.info[INCLUDE_ALL] = True
    with use_tenant(scope):
        product_id = uuid.uuid4()
        db.add(
            Product(
                id=product_id,
                tenant_id=TENANT_A,
                sku=f"PERF-{product_id.hex[:8]}",
                barcode=f"629{product_id.int % 10**10:010d}"[:13],
                name="Performance medicine",
                category="Medicine",
                price_cents=1500,
                currency="USD",
            )
        )
        db.flush()
        db.add(
            PharmacyProductDetails(
                product_id=product_id,
                tenant_id=TENANT_A,
                product_kind="MEDICINE",
                dispensing_class="PRESCRIPTION",
            )
        )
        db.add(InventoryLevel(tenant_id=TENANT_A, product_id=product_id, store_id=store_id, quantity_on_hand=200))
        for index in range(200):
            _layer(
                db,
                tenant_id=TENANT_A,
                product_id=product_id,
                store_id=store_id,
                user_id=user_id,
                quantity=1,
                status="RELEASED",
                lot=f"PERF-{index:03d}",
                medicine=True,
                expiry=date.today() + timedelta(days=30 + index),
            )
        other, _other = _product(
            db,
            tenant_id=TENANT_A,
            store_id=store_id,
            user_id=user_id,
            name="Performance second",
            quantity=5,
            status="RELEASED",
            medicine=True,
            lot="PERF-B",
        )
        db.commit()
    db.close()
    timings: list[float] = []
    query_counts: list[int] = []
    for _ in range(5):
        session = _app(App)
        count = {"n": 0}

        def bump(*_args, **_kwargs) -> None:
            count["n"] += 1

        from sqlalchemy import event

        event.listen(session.bind, "before_cursor_execute", bump)
        started = time.perf_counter()
        with use_tenant(scope):
            identity(session)
            rows = list(
                session.scalars(
                    select(BatchItem)
                    .where(BatchItem.product_id == product_id, BatchItem.store_id == store_id)
                    .order_by(BatchItem.expiry_date, BatchItem.id)
                ).all()
            )
            eligible = strict_sale_candidates(rows)
        timings.append((time.perf_counter() - started) * 1000)
        query_counts.append(count["n"])
        event.remove(session.bind, "before_cursor_execute", bump)
        session.close()
        _ = eligible
    sale_started = time.perf_counter()
    sale = _sell_result(App, scope, product_id, store_id, user_id, 1)
    sale_ms = (time.perf_counter() - sale_started) * 1000
    multi_started = time.perf_counter()
    session = _app(App)
    try:
        with use_tenant(scope):
            identity(session)
            move_stock(
                session,
                product_id=product_id,
                store_id=store_id,
                quantity=-1,
                movement_type="SALE_OUT",
                reference_type="sale",
                reference_id=uuid.uuid4(),
                user_id=user_id,
            )
            move_stock(
                session,
                product_id=other,
                store_id=store_id,
                quantity=-1,
                movement_type="SALE_OUT",
                reference_type="sale",
                reference_id=uuid.uuid4(),
                user_id=user_id,
            )
            session.commit()
        multi = "ok"
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        multi = str(exc)
    finally:
        session.close()
    multi_ms = (time.perf_counter() - multi_started) * 1000
    recall_started = time.perf_counter()
    recall = _recall(App, scope, product_id, "PERF-050", user_id, "PERF-RECALL")
    recall_ms = (time.perf_counter() - recall_started) * 1000
    with admin_engine.connect() as conn:
        size = conn.execute(text("SELECT pg_size_pretty(pg_database_size(current_database()))")).scalar()
        counts = dict(
            conn.execute(
                text(
                    "SELECT 'batch_items', count(*) FROM batch_items "
                    "UNION ALL SELECT 'batch_item_events', count(*) FROM batch_item_events "
                    "UNION ALL SELECT 'products', count(*) FROM products "
                    "UNION ALL SELECT 'pharmacy_recalls', count(*) FROM pharmacy_recalls"
                )
            ).all()
        )
    record(
        "3F2-PERF",
        sale[0] == "ok" and multi == "ok" and recall[0] == "ok",
        "Measured on this disposable dataset. No acceptance threshold is claimed.",
        (
            f"eligibility_ms min={min(timings):.1f} median={statistics.median(timings):.1f} "
            f"max={max(timings):.1f} queries={query_counts} sale_ms={sale_ms:.1f} "
            f"multiline_ms={multi_ms:.1f} recall_ms={recall_ms:.1f} size={size} counts={counts}"
        ),
        "200 one-unit released layers plus the earlier scenario rows",
    )


def _migration(admin_url, app_password: str) -> None:
    maintenance = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with maintenance.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {MIGRATE_DB}"))
        conn.execute(text(f"CREATE DATABASE {MIGRATE_DB}"))
        conn.execute(text(f"GRANT CONNECT ON DATABASE {MIGRATE_DB} TO ai_pos_app"))
    maintenance.dispose()
    migrate_admin = admin_url.set(database=MIGRATE_DB)
    _upgrade(migrate_admin.render_as_string(hide_password=False), PREVIOUS)
    engine = create_engine(migrate_admin)
    before = _insert_prior(engine)
    with engine.connect() as conn:
        at_previous = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    engine.dispose()
    _upgrade(migrate_admin.render_as_string(hide_password=False), "head")
    _upgrade(migrate_admin.render_as_string(hide_password=False), "head")
    engine = create_engine(migrate_admin)
    with engine.begin() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        conn.execute(text("GRANT USAGE ON SCHEMA public TO ai_pos_app"))
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ai_pos_app"))
        conn.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ai_pos_app"))
        after = _read_prior(conn)
    engine.dispose()
    app_engine = create_engine(migrate_admin.set(username="ai_pos_app", password=app_password))
    App = sessionmaker(bind=app_engine, expire_on_commit=False)
    db = _app(App)
    with use_tenant(tenant_ref(TENANT_A, "migrate")):
        identity(db)
        visible = int(db.scalar(select(func.count()).select_from(Product).where(Product.sku == "PRIOR-A")) or 0)
        hidden = int(db.scalar(select(func.count()).select_from(Product).where(Product.sku == "PRIOR-B")) or 0)
        try:
            db.execute(
                text(
                    "INSERT INTO products (id, tenant_id, sku, barcode, name, category, price_cents, currency, is_serialized, created_at, updated_at) "
                    "VALUES (:id, :tenant, 'CROSS-PRIOR', '6290000000004', 'Cross', 'Grocery', 100, 'USD', false, now(), now())"
                ),
                {"id": uuid.uuid4(), "tenant": str(TENANT_B)},
            )
            db.commit()
            state = "inserted"
        except DBAPIError as exc:
            db.rollback()
            state = _sqlstate(exc)
    db.close()
    app_engine.dispose()
    record(
        "3F2-MIGRATE",
        at_previous == PREVIOUS
        and version == HEAD
        and after == before
        and visible == 1
        and hidden == 0
        and state == "42501",
        "Upgrade from 20261119_0119 keeps quantities and tenant ownership, and a second upgrade stays at head",
        f"from={at_previous} to={version} before={before} after={after} visible={visible} hidden={hidden} cross={state}",
        "disposable database stage3f2_from_0119",
    )


def _insert_prior(engine) -> dict[str, object]:
    Admin = sessionmaker(bind=engine, expire_on_commit=False)
    db = Admin()
    db.info[INCLUDE_ALL] = True
    snapshot: dict[str, object] = {}
    for tenant_id, sku, quantity in ((TENANT_A, "PRIOR-A", 7), (TENANT_B, "PRIOR-B", 4)):
        with use_tenant(tenant_ref(tenant_id, "prior")):
            role = Role(tenant_id=tenant_id, name=f"Prior {sku}")
            db.add(role)
            db.flush()
            user = User(
                tenant_id=tenant_id,
                username=sku.lower(),
                email=f"{sku.lower()}@example.test",
                full_name=sku,
                role_id=role.id,
            )
            store = Store(tenant_id=tenant_id, code=sku, name=sku, currency="USD")
            db.add_all([user, store])
            db.flush()
            product = Product(
                tenant_id=tenant_id,
                sku=sku,
                barcode=f"629{tenant_id.int % 10**10:010d}"[:13],
                name=sku,
                category="Medicine",
                price_cents=1000,
                currency="USD",
            )
            db.add(product)
            db.flush()
            db.add(InventoryLevel(tenant_id=tenant_id, product_id=product.id, store_id=store.id, quantity_on_hand=quantity))
            batch = PurchaseBatch(
                tenant_id=tenant_id,
                batch_number=f"PRIOR-{sku}",
                store_id=store.id,
                import_source="MANUAL",
                currency="USD",
                status="ACTIVE",
                total_cost_amount=quantity * 100,
                total_items_count=quantity,
                created_by_id=user.id,
            )
            db.add(batch)
            db.flush()
            item = BatchItem(
                tenant_id=tenant_id,
                batch_id=batch.id,
                product_id=product.id,
                store_id=store.id,
                quantity_imported=quantity,
                quantity_remaining=quantity,
                purchase_cost_per_unit=100,
                selling_price_per_unit=1000,
                manufacturer_lot=sku,
                lot_status="UNRELEASED",
                imported_serials=[],
            )
            db.add(item)
            db.flush()
            movement = StockMovement(
                tenant_id=tenant_id,
                product_id=product.id,
                store_id=store.id,
                movement_type="PURCHASE_IN",
                quantity=quantity,
                quantity_after=quantity,
                reference_type="purchase",
                reference_id=batch.id,
                user_id=user.id,
                note="prior",
            )
            db.add(movement)
            db.flush()
            snapshot[sku] = {
                "on_hand": quantity,
                "remaining": quantity,
                "movement": quantity,
                "tenant": str(tenant_id),
                "movement_id": str(movement.id),
            }
    db.commit()
    db.close()
    return snapshot


def _read_prior(conn) -> dict[str, object]:
    rows = conn.execute(
        text(
            "SELECT p.sku, p.tenant_id, i.quantity_on_hand, b.quantity_remaining, m.quantity, m.id "
            "FROM products p "
            "JOIN inventory_levels i ON i.product_id = p.id "
            "JOIN batch_items b ON b.product_id = p.id "
            "JOIN stock_movements m ON m.product_id = p.id "
            "WHERE p.sku IN ('PRIOR-A', 'PRIOR-B') "
            "ORDER BY p.sku"
        )
    ).all()
    return {
        row[0]: {
            "on_hand": row[2],
            "remaining": row[3],
            "movement": row[4],
            "tenant": str(row[1]),
            "movement_id": str(row[5]),
        }
        for row in rows
    }


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
