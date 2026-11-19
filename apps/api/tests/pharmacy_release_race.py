"""Two PostgreSQL sessions releasing or clearing the same medicine lot.

Run from apps/api with the project virtualenv. Creates a disposable database,
proves upgrade and downgrade of the pharmacist authorization table, then drops
the database. Does not migrate the configured database.
"""

from __future__ import annotations

import uuid
from datetime import date

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import build_engine
from app.core.errors import ApiError
from app.models.batch import BatchItem, PurchaseBatch
from app.models.business_settings import BusinessSettings
from app.models.inventory import InventoryLevel, StockMovement
from app.models.pharmacy import PharmacyProductDetails
from app.models.pharmacy_lots import BatchItemEvent, PharmacistAuthorization
from app.models.product import Product
from app.models.role import Role
from app.models.store import Store
from app.models.user import User
from app.services.pharmacy_lots import clear_quarantine, release_lot
from app.services.settings_service import clear_settings_cache
from app.tenancy.context import TenantRef, use_tenant
from app.tenancy.scoping import DEFAULT_TENANT_ID, INCLUDE_ALL

TENANT = DEFAULT_TENANT_ID
OTHER = uuid.UUID("00000000-0000-4000-8000-0000000000b2")
EXPIRY = date(2027, 6, 30)
SCOPE = TenantRef(id=str(TENANT), slug="stage3e", name="Stage 3E", database_url="postgresql://unused")


def _database() -> tuple[str, str]:
    settings = get_settings()
    url = make_url(settings.database_url)
    if url.get_backend_name() != "postgresql":
        raise SystemExit("This race needs the configured PostgreSQL server, and a new disposable database on it.")
    name = f"stage3e_disp_{uuid.uuid4().hex[:8]}"
    if name == url.database:
        raise SystemExit("Refusing to use the configured database.")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    return name, url.set(database=name).render_as_string(hide_password=False)


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


def _alembic(url: str, direction: str, revision: str) -> None:
    config = Config("alembic.ini")
    config.attributes["database_url"] = url
    if direction == "upgrade":
        command.upgrade(config, revision)
    else:
        command.downgrade(config, revision)


def _factory(url: str):
    engine = build_engine(url)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def _table_exists(engine, table: str) -> bool:
    with engine.connect() as connection:
        found = connection.execute(text("SELECT to_regclass(:name)"), {"name": table}).scalar()
    return found is not None


def _bootstrap(factory, store_id, grantor_id, pharmacist_id) -> None:
    db = factory()
    db.info[INCLUDE_ALL] = True
    with use_tenant(SCOPE):
        role = Role(tenant_id=TENANT, name="Release clerk")
        db.add(role)
        db.flush()
        settings_row = db.scalar(select(BusinessSettings).limit(1))
        settings_row.business_profile = "pharmacy"
        settings_row.capabilities = None
        db.add(Store(id=store_id, tenant_id=TENANT, code="WH", name="Warehouse", currency="USD"))
        for user_id, username in ((grantor_id, "grantor"), (pharmacist_id, "pharmacist")):
            db.add(
                User(
                    id=user_id,
                    tenant_id=TENANT,
                    username=username,
                    email=f"{username}@example.test",
                    full_name=username,
                    role_id=role.id,
                )
            )
        db.flush()
        db.add(
            PharmacistAuthorization(
                tenant_id=TENANT,
                user_id=pharmacist_id,
                requested_by_id=grantor_id,
                granted_by_id=grantor_id,
                approved_by_id=grantor_id,
                reason="Appointed for the release race",
                status="ACTIVE",
                approval_basis="LEGACY",
            )
        )
        db.commit()
    db.close()


def _reappoint(factory, grantor_id, pharmacist_id) -> None:
    db = factory()
    db.info[INCLUDE_ALL] = True
    with use_tenant(SCOPE):
        db.add(
            PharmacistAuthorization(
                tenant_id=TENANT,
                user_id=pharmacist_id,
                requested_by_id=grantor_id,
                granted_by_id=grantor_id,
                approved_by_id=grantor_id,
                reason="Appointed again after the migration round trip",
                status="ACTIVE",
                approval_basis="LEGACY",
            )
        )
        db.commit()
    db.close()


def _layer(factory, *, product_id, store_id, user_id, status: str) -> uuid.UUID:
    db = factory()
    db.info[INCLUDE_ALL] = True
    with use_tenant(SCOPE):
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
        db.add(
            InventoryLevel(
                tenant_id=TENANT,
                product_id=product_id,
                store_id=store_id,
                quantity_on_hand=4,
            )
        )
        db.flush()
        batch = PurchaseBatch(
            tenant_id=TENANT,
            batch_number=f"REL-{product_id.hex[:8]}",
            store_id=store_id,
            import_source="MANUAL",
            currency="USD",
            status="ACTIVE",
            total_cost_amount=400,
            total_items_count=4,
            created_by_id=user_id,
        )
        db.add(batch)
        db.flush()
        item = BatchItem(
            tenant_id=TENANT,
            batch_id=batch.id,
            product_id=product_id,
            store_id=store_id,
            quantity_imported=4,
            quantity_remaining=4,
            purchase_cost_per_unit=100,
            selling_price_per_unit=1500,
            expiry_date=EXPIRY,
            manufacturer_lot="MFG-RACE",
            lot_status=status,
            imported_serials=[],
        )
        db.add(item)
        db.commit()
        item_id = item.id
    db.close()
    return item_id


def _race(factory, item_id, pharmacist_id, action) -> list[str]:
    import threading

    start = threading.Barrier(2)
    results: list[str] = []

    def run() -> None:
        start.wait()
        db = factory()
        try:
            with use_tenant(SCOPE):
                action(db, item_id, pharmacist_id, "Checked and ready")
            results.append("ok")
        except ApiError as exc:
            results.append(exc.code)
        finally:
            db.close()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def _expect_one(factory, item_id, previous: str, results: list[str]) -> None:
    print(previous, results)
    if sorted(results) != ["already_released", "ok"]:
        raise SystemExit(f"Expected one success and one already-released rejection, got {results}.")
    db = factory()
    db.info[INCLUDE_ALL] = True
    item = db.get(BatchItem, item_id)
    events = db.scalars(select(BatchItemEvent).where(BatchItemEvent.batch_item_id == item_id)).all()
    movements = db.scalar(
        select(func.count()).select_from(StockMovement).where(StockMovement.product_id == item.product_id)
    )
    if item.lot_status != "RELEASED" or item.quantity_remaining != 4 or item.released_by_id is None:
        raise SystemExit(f"Lot ended as {item.lot_status} with remaining {item.quantity_remaining}.")
    released = [event for event in events if event.from_status == previous and event.to_status == "RELEASED"]
    if len(released) != 1 or movements != 0:
        raise SystemExit(f"Expected one {previous} to RELEASED event and no stock movement, got {len(released)} and {movements}.")
    db.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(TENANT)})
    db.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))
    try:
        db.execute(text("UPDATE batch_item_events SET reason = 'rewritten' WHERE id = :id"), {"id": released[0].id})
        db.commit()
        raise SystemExit("The append-only trigger allowed an event update.")
    except Exception as exc:  # noqa: BLE001 - the trigger is the assertion
        db.rollback()
        if "append-only" not in str(exc):
            raise
    db.close()


def _rls(engine, probe: str) -> None:
    admin = engine.execution_options(isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE ROLE "{probe}" NOLOGIN NOBYPASSRLS'))
        connection.execute(text(f'GRANT USAGE ON SCHEMA public TO "{probe}"'))
        connection.execute(text(f'GRANT SELECT ON pharmacist_authorizations TO "{probe}"'))
    with engine.connect() as connection:
        policy = connection.execute(
            text(
                "SELECT polname FROM pg_policy "
                "WHERE polrelid = 'pharmacist_authorizations'::regclass"
            )
        ).scalar()
        connection.execute(text(f'SET ROLE "{probe}"'))
        connection.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))
        connection.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(OTHER)})
        hidden = connection.execute(text("SELECT count(*) FROM pharmacist_authorizations")).scalar()
        connection.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(TENANT)})
        visible = connection.execute(text("SELECT count(*) FROM pharmacist_authorizations")).scalar()
        connection.execute(text("RESET ROLE"))
        print(f"rls policy={policy} other_tenant_rows={hidden} own_tenant_rows={visible}")
        if policy != "tenant_isolation" or hidden != 0 or visible != 1:
            raise SystemExit("The pharmacist authorization policy did not isolate the tenant.")


def main() -> None:
    name, url = _database()
    probe = f"stage3e_rls_{uuid.uuid4().hex[:8]}"
    print(f"disposable database {name}")
    engine = None
    try:
        _alembic(url, "upgrade", "head")
        engine, factory = _factory(url)
        if not _table_exists(engine, "pharmacist_authorizations"):
            raise SystemExit("Upgrade did not create pharmacist_authorizations.")
        clear_settings_cache()
        store_id, grantor_id, pharmacist_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        _bootstrap(factory, store_id, grantor_id, pharmacist_id)
        held = uuid.uuid4()
        held_item = _layer(factory, product_id=held, store_id=store_id, user_id=grantor_id, status="UNRELEASED")
        engine.dispose()
        _alembic(url, "downgrade", "20261118_0116")
        engine, factory = _factory(url)
        if _table_exists(engine, "pharmacist_authorizations"):
            raise SystemExit("Downgrade left pharmacist_authorizations in place.")
        db = factory()
        db.info[INCLUDE_ALL] = True
        status = db.scalar(select(BatchItem.lot_status).where(BatchItem.id == held_item))
        remaining = db.scalar(select(BatchItem.quantity_remaining).where(BatchItem.id == held_item))
        db.close()
        if status != "UNRELEASED" or remaining != 4:
            raise SystemExit(f"Downgrade changed stock: {status} remaining {remaining}.")
        engine.dispose()
        _alembic(url, "upgrade", "head")
        engine, factory = _factory(url)
        db = factory()
        db.info[INCLUDE_ALL] = True
        status = db.scalar(select(BatchItem.lot_status).where(BatchItem.id == held_item))
        auths = db.scalar(select(func.count()).select_from(PharmacistAuthorization))
        db.close()
        if status != "UNRELEASED" or auths != 0:
            raise SystemExit(f"Second upgrade changed stock or restored an authorization: {status}, rows {auths}.")
        _reappoint(factory, grantor_id, pharmacist_id)
        release_results = _race(factory, held_item, pharmacist_id, release_lot)
        _expect_one(factory, held_item, "UNRELEASED", release_results)
        quarantined = uuid.uuid4()
        quarantined_item = _layer(
            factory, product_id=quarantined, store_id=store_id, user_id=grantor_id, status="QUARANTINED"
        )
        clear_results = _race(factory, quarantined_item, pharmacist_id, clear_quarantine)
        _expect_one(factory, quarantined_item, "QUARANTINED", clear_results)
        _rls(engine, probe)
        print("PASS")
    finally:
        if engine is not None:
            admin = engine.execution_options(isolation_level="AUTOCOMMIT")
            with admin.connect() as connection:
                exists = connection.execute(
                    text("SELECT 1 FROM pg_roles WHERE rolname = :name"), {"name": probe}
                ).scalar()
                if exists:
                    connection.execute(text(f'REVOKE ALL ON TABLE pharmacist_authorizations FROM "{probe}"'))
                    connection.execute(text(f'REVOKE USAGE ON SCHEMA public FROM "{probe}"'))
                    connection.execute(text(f'DROP ROLE "{probe}"'))
            engine.dispose()
        _drop(name)
        print(f"dropped {name}")


if __name__ == "__main__":
    main()
