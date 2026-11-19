"""Two real PostgreSQL sessions selling the same medicine lot.

Run from apps/api with the project virtualenv. Creates a disposable database,
upgrades it to head, and drops it. Does not migrate the configured database.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text  # noqa: TID251
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import build_engine
from app.core.errors import SyncRejected
from app.models.batch import BatchAllocation, BatchItem, PurchaseBatch
from app.models.business_settings import BusinessSettings
from app.models.inventory import InventoryLevel, StockMovement
from app.models.pharmacy import PharmacyProductDetails
from app.models.product import Product
from app.models.role import Role
from app.models.sale import Sale
from app.models.store import Store
from app.models.user import User
from app.services.inventory import move_stock
from app.services.settings_service import clear_settings_cache
from app.tenancy.context import TenantRef, use_tenant
from app.tenancy.scoping import DEFAULT_TENANT_ID, INCLUDE_ALL

TENANT = DEFAULT_TENANT_ID
EXPIRY = date(2027, 6, 30)
SCOPE = TenantRef(id=str(TENANT), slug="stage3d", name="Stage 3D", database_url="postgresql://unused")


def _database() -> tuple[str, str]:
    settings = get_settings()
    url = make_url(settings.database_url)
    if url.get_backend_name() != "postgresql":
        raise SystemExit("This race needs the configured PostgreSQL server, and a new disposable database on it.")
    name = f"stage3d_disp_{uuid.uuid4().hex[:8]}"
    if name == url.database:
        raise SystemExit("Refusing to use the configured database.")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    target = url.set(database=name).render_as_string(hide_password=False)
    return name, target


def _drop(name: str) -> None:
    url = make_url(get_settings().database_url).set(database="postgres")
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :name AND pid <> pg_backend_pid()"
            ),
            {"name": name},
        )
        connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
    admin.dispose()


def _upgrade(url: str) -> None:
    config = Config("alembic.ini")
    config.attributes["database_url"] = url
    command.upgrade(config, "head")


def _bootstrap(session_factory, store_id, user_id) -> None:
    db = session_factory()
    db.info[INCLUDE_ALL] = True
    with use_tenant(SCOPE):
        _bootstrap_rows(db, store_id, user_id)
    db.close()


def _bootstrap_rows(db, store_id, user_id) -> None:
    role = Role(tenant_id=TENANT, name="Race cashier")
    db.add(role)
    db.flush()
    settings_row = db.scalar(select(BusinessSettings).limit(1))
    if settings_row is None:
        settings_row = BusinessSettings(id=uuid.uuid4(), tenant_id=TENANT, currency="USD")
        db.add(settings_row)
    settings_row.business_profile = "pharmacy"
    settings_row.capabilities = None
    db.add(Store(id=store_id, tenant_id=TENANT, code="WH", name="Warehouse", currency="USD"))
    db.add(
        User(
            id=user_id,
            tenant_id=TENANT,
            username="cashier",
            email="cashier@example.test",
            full_name="Cashier",
            role_id=role.id,
        )
    )
    db.commit()


def _seed(
    session_factory,
    *,
    product_id,
    store_id,
    user_id,
    layers: list[tuple[str, date, int, str]],
) -> None:
    db = session_factory()
    db.info[INCLUDE_ALL] = True
    with use_tenant(SCOPE):
        _seed_rows(db, product_id=product_id, store_id=store_id, user_id=user_id, layers=layers)
    db.close()


def _seed_rows(db, *, product_id, store_id, user_id, layers) -> None:
    db.add(
        Product(
            id=product_id,
            tenant_id=TENANT,
            sku=f"MED-{product_id.hex[:8]}",
            barcode=f"629{product_id.int % 10**10:010d}"[:13],
            name="Amoxicillin",
            category="Medicine",
            price_cents=1500,
            currency="USD",
        )
    )
    db.flush()
    db.add(
        PharmacyProductDetails(
            product_id=product_id,
            tenant_id=TENANT,
            product_kind="MEDICINE",
            dispensing_class="PRESCRIPTION",
        )
    )
    on_hand = sum(quantity for _, _, quantity, _status in layers)
    db.add(
        InventoryLevel(
            tenant_id=TENANT,
            product_id=product_id,
            store_id=store_id,
            quantity_on_hand=on_hand,
        )
    )
    db.flush()
    for index, (lot, expiry, quantity, status) in enumerate(layers):
        batch = PurchaseBatch(
            tenant_id=TENANT,
            batch_number=f"RACE-{product_id.hex[:6]}-{index}",
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
        db.add(
            BatchItem(
                tenant_id=TENANT,
                batch_id=batch.id,
                product_id=product_id,
                store_id=store_id,
                quantity_imported=quantity,
                quantity_remaining=quantity,
                purchase_cost_per_unit=100,
                selling_price_per_unit=1500,
                expiry_date=expiry,
                manufacturer_lot=lot,
                lot_status=status,
                imported_serials=[],
            )
        )
    db.commit()


def _sell(session_factory, tenant: TenantRef, product_id, store_id, user_id, quantity: int, start) -> tuple[str, str]:
    start.wait()
    db = session_factory()
    sale_id = uuid.uuid4()
    try:
        with tenant_scope(tenant):
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
                    tenant_id=TENANT,
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
            db.commit()
        return "ok", str(sale_id)
    except (SyncRejected, Exception) as exc:  # noqa: BLE001 - the race reports every loser
        db.rollback()
        return type(exc).__name__, str(exc)
    finally:
        db.close()


class tenant_scope:
    def __init__(self, tenant: TenantRef) -> None:
        self.tenant = tenant
        self._context = None

    def __enter__(self):
        self._context = use_tenant(self.tenant)
        return self._context.__enter__()

    def __exit__(self, exc_type, exc, tb):
        return self._context.__exit__(exc_type, exc, tb)


def _check(session_factory, product_id, *, remaining: int, sales: int, allocations: int) -> None:
    db = session_factory()
    db.info[INCLUDE_ALL] = True
    on_hand = db.scalar(
        select(func.coalesce(func.sum(InventoryLevel.quantity_on_hand), 0)).where(
            InventoryLevel.product_id == product_id
        )
    )
    left = db.scalar(
        select(func.coalesce(func.sum(BatchItem.quantity_remaining), 0)).where(BatchItem.product_id == product_id)
    )
    negative = db.scalar(
        select(func.count()).select_from(BatchItem).where(
            BatchItem.product_id == product_id, BatchItem.quantity_remaining < 0
        )
    )
    movement_count = db.scalar(
        select(func.count()).select_from(StockMovement).where(
            StockMovement.product_id == product_id, StockMovement.movement_type == "SALE_OUT"
        )
    )
    sale_count = db.scalar(
        select(func.count(func.distinct(Sale.id)))
        .join(StockMovement, StockMovement.reference_id == Sale.id)
        .where(StockMovement.product_id == product_id, StockMovement.movement_type == "SALE_OUT")
    )
    allocation_count = db.scalar(
        select(func.count())
        .select_from(BatchAllocation)
        .join(BatchItem, BatchItem.id == BatchAllocation.batch_item_id)
        .where(BatchItem.product_id == product_id)
    )
    db.close()
    print(
        f"product {product_id.hex[:8]} on_hand={on_hand} remaining={left} "
        f"movements={movement_count} allocations={allocation_count} negative={negative}"
    )
    mismatched = (
        on_hand != remaining
        or left != remaining
        or negative
        or movement_count != sales
        or allocation_count != allocations
    )
    if mismatched:
        raise SystemExit(
            f"Race result mismatch: on_hand {on_hand}, remaining {left}, movements {movement_count}, "
            f"allocations {allocation_count}, expected remaining {remaining}, sales {sales}, allocations {allocations}."
        )
    if sale_count < sales:
        raise SystemExit(f"Expected at least {sales} posted sales, found {sale_count}.")


def _race(session_factory, tenant, product_id, store_id, user_id, quantity: int) -> list[tuple[str, str]]:
    import threading

    start = threading.Barrier(2)
    results: list[tuple[str, str]] = []

    def run() -> None:
        results.append(_sell(session_factory, tenant, product_id, store_id, user_id, quantity, start))

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def main() -> None:
    name, url = _database()
    print(f"disposable database {name}")
    try:
        _upgrade(url)
        engine = build_engine(url)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        tenant = TenantRef(id=str(TENANT), slug="stage3d", name="Stage 3D", database_url=url)
        clear_settings_cache()

        store_id = uuid.uuid4()
        user_id = uuid.uuid4()
        _bootstrap(factory, store_id, user_id)
        single = uuid.uuid4()
        _seed(
            factory,
            product_id=single,
            store_id=store_id,
            user_id=user_id,
            layers=[("LOT-5", EXPIRY, 5, "RELEASED")],
        )
        single_results = _race(factory, tenant, single, store_id, user_id, 4)
        print("single lot", single_results)
        winners = [item for item in single_results if item[0] == "ok"]
        if len(winners) != 1:
            raise SystemExit(f"Expected one successful sale of the five-unit lot, got {single_results}.")
        _check(factory, single, remaining=1, sales=1, allocations=1)

        several = uuid.uuid4()
        _seed(
            factory,
            product_id=several,
            store_id=store_id,
            user_id=user_id,
            layers=[
                ("LOT-SOON", EXPIRY, 3, "RELEASED"),
                ("LOT-LATER", EXPIRY + timedelta(days=30), 3, "RELEASED"),
            ],
        )
        several_results = _race(factory, tenant, several, store_id, user_id, 4)
        print("two lots", several_results)
        if len([item for item in several_results if item[0] == "ok"]) != 1:
            raise SystemExit(f"Expected one successful multi-lot sale, got {several_results}.")
        _check(factory, several, remaining=2, sales=1, allocations=2)

        mixed = uuid.uuid4()
        _seed(
            factory,
            product_id=mixed,
            store_id=store_id,
            user_id=user_id,
            layers=[
                ("LOT-RELEASED", EXPIRY, 4, "RELEASED"),
                ("LOT-HELD", EXPIRY + timedelta(days=10), 4, "UNRELEASED"),
            ],
        )
        mixed_results = _race(factory, tenant, mixed, store_id, user_id, 4)
        print("released plus unreleased", mixed_results)
        if len([item for item in mixed_results if item[0] == "ok"]) != 1:
            raise SystemExit(f"Expected the unreleased lot to stay unsold, got {mixed_results}.")
        _check(factory, mixed, remaining=4, sales=1, allocations=1)
        print("PASS")
    finally:
        _drop(name)
        print(f"dropped {name}")


if __name__ == "__main__":
    main()
