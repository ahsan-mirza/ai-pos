"""PostgreSQL races for pharmacist appointment, revocation, release, and clearance.

Run from apps/api. Creates a disposable database, upgrades and downgrades it, then drops it.
Does not migrate the configured database.

Locking: PostgreSQL READ COMMITTED. Approval, revocation, and release take
SELECT ... FOR UPDATE on the open pharmacist authorization. Release and clearance
then lock the lot row. The second session waits and re-reads the committed status.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, text

from app.core.errors import ApiError
from app.models.batch import BatchItem
from app.models.business_settings import BusinessSettings
from app.models.pharmacy_lots import PharmacistAuthorization, PharmacyGovernanceOfficer
from app.models.product import Product
from app.models.role import Role
from app.models.store import Store
from app.models.user import User
from app.services.pharmacy_lots import (
    active_pharmacist,
    approve_pharmacist,
    clear_quarantine,
    confirm_officer,
    nominate_officer,
    release_lot,
    request_pharmacist,
    revoke_pharmacist,
)
from app.services.settings_service import clear_settings_cache
from app.tenancy.context import use_tenant
from app.tenancy.scoping import INCLUDE_ALL
from pharmacy_release_race import SCOPE, TENANT, _alembic, _database, _drop, _factory, _layer

OTHER = uuid.UUID("00000000-0000-4000-8000-0000000000b2")


def _people(factory, store_id, ids: dict[str, uuid.UUID]) -> None:
    db = factory()
    db.info[INCLUDE_ALL] = True
    with use_tenant(SCOPE):
        role = Role(tenant_id=TENANT, name="Governance clerk")
        db.add(role)
        db.flush()
        settings_row = db.scalar(select(BusinessSettings).limit(1))
        settings_row.business_profile = "pharmacy"
        settings_row.capabilities = None
        db.add(Store(id=store_id, tenant_id=TENANT, code="WH", name="Warehouse", currency="USD"))
        for name, user_id in ids.items():
            db.add(
                User(
                    id=user_id,
                    tenant_id=TENANT,
                    username=name,
                    email=f"{name}@example.test",
                    full_name=name,
                    role_id=role.id,
                )
            )
        db.commit()
    db.close()


def _call(factory, fn) -> str:
    db = factory()
    try:
        with use_tenant(SCOPE):
            fn(db)
        return "ok"
    except ApiError as exc:
        return exc.code
    finally:
        db.close()


def _race(factory, left, right) -> list[str]:
    import threading

    start = threading.Barrier(2)
    results: list[str] = []

    def run(fn) -> None:
        start.wait()
        results.append(_call(factory, fn))

    threads = [threading.Thread(target=run, args=(left,)), threading.Thread(target=run, args=(right,))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def _officers(factory, nominator, confirmer, first, second) -> None:
    db = factory()
    with use_tenant(SCOPE):
        nominate_officer(db, nominator, first, "First officer", role_manager=True)
        confirm_officer(db, confirmer, first, "Confirm first officer", role_manager=True)
        nominate_officer(db, nominator, second, "Second officer", role_manager=True)
        confirm_officer(db, confirmer, second, "Confirm second officer", role_manager=True)
    db.close()


def _rls(engine, probe: str) -> None:
    admin = engine.execution_options(isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE ROLE "{probe}" NOLOGIN NOBYPASSRLS'))
        connection.execute(text(f'GRANT USAGE ON SCHEMA public TO "{probe}"'))
        connection.execute(text(f'GRANT SELECT ON pharmacy_governance_officers TO "{probe}"'))
        connection.execute(text(f'GRANT SELECT ON pharmacist_authorizations TO "{probe}"'))
    with engine.connect() as connection:
        connection.execute(text(f'SET ROLE "{probe}"'))
        connection.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))
        connection.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(OTHER)})
        hidden_officers = connection.execute(text("SELECT count(*) FROM pharmacy_governance_officers")).scalar()
        hidden_grants = connection.execute(text("SELECT count(*) FROM pharmacist_authorizations")).scalar()
        connection.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(TENANT)})
        visible_officers = connection.execute(text("SELECT count(*) FROM pharmacy_governance_officers")).scalar()
        connection.execute(text("RESET ROLE"))
        print(
            f"rls other_officers={hidden_officers} other_grants={hidden_grants} own_officers={visible_officers}"
        )
        if hidden_officers != 0 or hidden_grants != 0 or visible_officers != 2:
            raise SystemExit("Governance rows were visible to another tenant.")


def main() -> None:
    name, url = _database()
    probe = f"stage3e1_rls_{uuid.uuid4().hex[:8]}"
    print(f"disposable database {name}")
    engine = None
    try:
        _alembic(url, "upgrade", "head")
        engine, factory = _factory(url)
        clear_settings_cache()
        store_id = uuid.uuid4()
        ids = {key: uuid.uuid4() for key in ("nominator", "confirmer", "officer1", "officer2", "pharmacist", "again")}
        _people(factory, store_id, ids)
        product_id = uuid.uuid4()
        held = _layer(factory, product_id=product_id, store_id=store_id, user_id=ids["nominator"], status="UNRELEASED")
        _officers(factory, ids["nominator"], ids["confirmer"], ids["officer1"], ids["officer2"])
        db = factory()
        with use_tenant(SCOPE):
            request_pharmacist(db, ids["officer1"], ids["pharmacist"], "Pending across downgrade")
        db.close()
        engine.dispose()
        _alembic(url, "downgrade", "20261118_0117")
        engine, factory = _factory(url)
        db = factory()
        db.info[INCLUDE_ALL] = True
        revoked = db.scalar(select(PharmacistAuthorization.revoked_at).where(PharmacistAuthorization.user_id == ids["pharmacist"]))
        remaining = db.scalar(select(BatchItem.quantity_remaining).where(BatchItem.id == held))
        status = db.scalar(select(BatchItem.lot_status).where(BatchItem.id == held))
        db.close()
        if revoked is None or remaining != 4 or status != "UNRELEASED":
            raise SystemExit(f"Downgrade changed the pending grant or the lot: revoked={revoked} status={status} remaining={remaining}.")
        if _table(engine, "pharmacy_governance_officers"):
            raise SystemExit("Downgrade left pharmacy_governance_officers in place.")
        engine.dispose()
        _alembic(url, "upgrade", "head")
        engine, factory = _factory(url)
        db = factory()
        db.info[INCLUDE_ALL] = True
        with use_tenant(SCOPE):
            restored = db.scalar(select(PharmacistAuthorization).where(PharmacistAuthorization.user_id == ids["pharmacist"]))
            if restored is None or restored.status != "REVOKED" or active_pharmacist(db, ids["pharmacist"]) is not None:
                raise SystemExit("The unapproved appointment became active after the round trip.")
        db.close()
        _officers(factory, ids["nominator"], ids["confirmer"], ids["officer1"], ids["officer2"])
        db = factory()
        with use_tenant(SCOPE):
            request_pharmacist(db, ids["officer1"], ids["pharmacist"], "Ready for approval")
        db.close()
        approval = _race(
            factory,
            lambda db: approve_pharmacist(db, ids["officer2"], ids["pharmacist"], "First approval"),
            lambda db: approve_pharmacist(db, ids["officer2"], ids["pharmacist"], "Second approval"),
        )
        print("approval", approval)
        if sorted(approval) != ["not_found", "ok"]:
            raise SystemExit(f"Expected one approval, got {approval}.")
        db = factory()
        db.info[INCLUDE_ALL] = True
        active = db.scalar(
            select(func.count()).select_from(PharmacistAuthorization).where(
                PharmacistAuthorization.user_id == ids["pharmacist"],
                PharmacistAuthorization.status == "ACTIVE",
            )
        )
        db.close()
        if active != 1:
            raise SystemExit(f"Expected one active authorization, found {active}.")

        requested = _race(
            factory,
            lambda db: request_pharmacist(db, ids["officer1"], ids["again"], "First request"),
            lambda db: request_pharmacist(db, ids["officer1"], ids["again"], "Second request"),
        )
        print("duplicate request", requested)
        if sorted(requested) != ["already_pending", "ok"]:
            raise SystemExit(f"Expected one pending request, got {requested}.")

        contested = _race(
            factory,
            lambda db: revoke_pharmacist(db, ids["officer1"], ids["pharmacist"], "Revoke during release"),
            lambda db: release_lot(db, held, ids["pharmacist"], "Release during revocation"),
        )
        print("revoke versus release", contested)
        from app.models.inventory import StockMovement
        from app.models.pharmacy_lots import BatchItemEvent

        db = factory()
        db.info[INCLUDE_ALL] = True
        item = db.get(BatchItem, held)
        movement_count = db.scalar(
            select(func.count()).select_from(StockMovement).where(StockMovement.product_id == product_id)
        )
        release_events = db.scalar(
            select(func.count()).select_from(BatchItemEvent).where(
                BatchItemEvent.batch_item_id == held,
                BatchItemEvent.action == "RELEASED",
            )
        )
        revoked_auth = db.scalar(
            select(PharmacistAuthorization).where(
                PharmacistAuthorization.user_id == ids["pharmacist"],
                PharmacistAuthorization.status == "REVOKED",
            )
        )
        db.close()
        if revoked_auth is None or item.quantity_remaining != 4 or movement_count != 0:
            raise SystemExit("Revocation race changed quantity or left the authorization active.")
        if sorted(contested) == ["ok", "ok"] and item.lot_status == "RELEASED" and release_events == 1:
            pass
        elif sorted(contested) == ["ok", "pharmacist_required"] and item.lot_status == "UNRELEASED" and release_events == 0:
            pass
        else:
            raise SystemExit(
                f"Revoke/release ended as {contested}, status {item.lot_status}, events {release_events}."
            )

        second = uuid.uuid4()
        second_item = _layer(factory, product_id=second, store_id=store_id, user_id=ids["nominator"], status="UNRELEASED")
        db = factory()
        with use_tenant(SCOPE):
            approve_pharmacist(db, ids["officer2"], ids["again"], "Approve the second pharmacist")
        db.close()
        released = _race(
            factory,
            lambda db: release_lot(db, second_item, ids["again"], "First release"),
            lambda db: release_lot(db, second_item, ids["again"], "Second release"),
        )
        print("release", released)
        if sorted(released) != ["already_released", "ok"]:
            raise SystemExit(f"Expected one release, got {released}.")

        third = uuid.uuid4()
        third_item = _layer(factory, product_id=third, store_id=store_id, user_id=ids["nominator"], status="QUARANTINED")
        cleared = _race(
            factory,
            lambda db: clear_quarantine(db, third_item, ids["again"], "First clearance"),
            lambda db: clear_quarantine(db, third_item, ids["again"], "Second clearance"),
        )
        print("clearance", cleared)
        if sorted(cleared) != ["already_released", "ok"]:
            raise SystemExit(f"Expected one clearance, got {cleared}.")
        db = factory()
        db.info[INCLUDE_ALL] = True
        for item_id in (second_item, third_item):
            row = db.get(BatchItem, item_id)
            if row.quantity_remaining != 4 or row.lot_status != "RELEASED":
                raise SystemExit(f"Lot {item_id} ended as {row.lot_status} remaining {row.quantity_remaining}.")
        db.close()
        _rls(engine, probe)
        print("PASS")
    finally:
        if engine is not None:
            admin = engine.execution_options(isolation_level="AUTOCOMMIT")
            with admin.connect() as connection:
                exists = connection.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :name"), {"name": probe}).scalar()
                if exists:
                    connection.execute(text(f'REVOKE ALL ON TABLE pharmacy_governance_officers FROM "{probe}"'))
                    connection.execute(text(f'REVOKE ALL ON TABLE pharmacist_authorizations FROM "{probe}"'))
                    connection.execute(text(f'REVOKE USAGE ON SCHEMA public FROM "{probe}"'))
                    connection.execute(text(f'DROP ROLE "{probe}"'))
            engine.dispose()
        _drop(name)
        print(f"dropped {name}")


def _table(engine, table: str) -> bool:
    with engine.connect() as connection:
        found = connection.execute(text("SELECT to_regclass(:name)"), {"name": table}).scalar()
    return found is not None


if __name__ == "__main__":
    main()
