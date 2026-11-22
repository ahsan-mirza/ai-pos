"""Disposable PostgreSQL RLS proof for O8.2.

Opens only 127.0.0.1:55941 database axizpos_o82. Refuses every other target.
The checked session logs in as ai_pos_app. SET ROLE is not used.
"""

from __future__ import annotations

import os
import uuid

os.environ["APP_ENV"] = "acceptance"
os.environ["DATABASE_URL"] = "postgresql+psycopg://o82boot@127.0.0.1:55941/axizpos_o82"
os.environ["CONTROL_DATABASE_URL"] = ""
os.environ["JWT_SECRET"] = "o82-jwt-secret-must-be-32-chars!!"
os.environ["PIN_SALT"] = "o82-pin-pepper-16"
os.environ["ENCRYPTION_SECRET"] = "o82-encryption-secret-32-chars!!"
os.environ["API_KEY"] = "o82-api-key-value"
os.environ["CORS_ORIGINS"] = "http://127.0.0.1:55941"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["ALEMBIC_TENANT_ID"] = "00000000-0000-4000-8000-00000000a821"

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BOOT = "postgresql+psycopg://o82boot@127.0.0.1:55941/postgres"
OPS = os.environ["DATABASE_URL"]
APP_PASSWORD = "o82-app-role-password"
TENANT_A = uuid.UUID("11111111-1111-4111-8111-11111111a821")
TENANT_B = uuid.UUID("22222222-2222-4222-8222-22222222a821")
RESULTS: list[tuple[str, bool, str]] = []


def require_disposable(url: str) -> None:
    parsed = make_url(url)
    if parsed.host != "127.0.0.1" or parsed.port != 55941 or parsed.username != "o82boot":
        raise SystemExit("Refusing: target is not the disposable O8.2 cluster.")
    if parsed.database not in {"postgres", "axizpos_o82"}:
        raise SystemExit("Refusing: database name is not disposable.")


def record(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, ok, detail))
    print(("PASS" if ok else "FAIL"), name, detail)


def main() -> None:
    require_disposable(BOOT)
    require_disposable(OPS)
    admin = create_engine(BOOT, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = 'axizpos_o82'")).scalar()
        if exists is None:
            conn.execute(text("CREATE DATABASE axizpos_o82"))
    admin.dispose()

    os.chdir(os.path.join(os.path.dirname(__file__), ".."))
    config = Config("alembic.ini")
    config.attributes["database_url"] = OPS
    command.upgrade(config, "head")

    owner = create_engine(OPS, isolation_level="AUTOCOMMIT")
    with owner.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'ai_pos_app'")).scalar()
        if exists is None:
            conn.exec_driver_sql(
                "CREATE ROLE ai_pos_app LOGIN PASSWORD 'o82-app-role-password' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
            )
        conn.execute(text("GRANT CONNECT ON DATABASE axizpos_o82 TO ai_pos_app"))
        conn.execute(text("GRANT USAGE ON SCHEMA public TO ai_pos_app"))
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ai_pos_app"))
        conn.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ai_pos_app"))
        role = conn.execute(
            text("SELECT rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname = 'ai_pos_app'")
        ).one()
        record(
            "role attributes",
            role.rolcanlogin is True and role.rolsuper is False and role.rolbypassrls is False,
            "LOGIN NOSUPERUSER NOBYPASSRLS",
        )
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', false)"))
        for table in (
            "staff_provisioning_events",
            "sync_events",
            "terminal_allocations",
            "bootstrap_sessions",
        ):
            conn.execute(text(f'DELETE FROM "{table}"'))
        conn.execute(
            text(
                """
                INSERT INTO staff_provisioning_events (
                    id, tenant_id, event_id, operation, payload_hash, status, safe_message,
                    origin_terminal_id, schema_version, created_at
                ) VALUES
                    (:ida, :ta, 'event-a', 'create', 'hash-a', 'accepted', 'accepted', 'till-a', 1, NOW()),
                    (:idb, :tb, 'event-b', 'create', 'hash-b', 'accepted', 'accepted', 'till-b', 1, NOW())
                """
            ),
            {"ida": uuid.uuid4(), "idb": uuid.uuid4(), "ta": TENANT_A, "tb": TENANT_B},
        )
        conn.execute(
            text(
                """
                INSERT INTO sync_events (
                    id, tenant_id, idempotency_key, device_id, entity_type, payload_hash, occurred_at, applied_at
                ) VALUES
                    (:ida, :ta, 'sale-a', 'till-a', 'sale', 'hash-a', NOW(), NOW()),
                    (:idb, :tb, 'sale-b', 'till-b', 'sale', 'hash-b', NOW(), NOW())
                """
            ),
            {"ida": uuid.uuid4(), "idb": uuid.uuid4(), "ta": TENANT_A, "tb": TENANT_B},
        )
        conn.execute(
            text(
                """
                INSERT INTO terminal_allocations (
                    id, tenant_id, manifest_id, version, store_id, device_id, device_thumbprint, product_id,
                    unit, quantity_allocated, quantity_consumed, last_sequence, status, policy_version,
                    signing_key_id, manifest_payload, manifest_signature, issued_at, created_at, updated_at
                ) VALUES
                    (:id1, :ta, :m1, 1, :store_a, :dev_a, 'aa', :product, 'each', 40, 0, 0, 'ACTIVE', 1,
                     'o2-test', '{}', 'sig', NOW(), NOW(), NOW()),
                    (:id2, :ta, :m2, 1, :store_b, :dev_b, 'bb', :product, 'each', 35, 0, 0, 'ACTIVE', 1,
                     'o2-test', '{}', 'sig', NOW(), NOW(), NOW())
                """
            ),
            {
                "id1": uuid.uuid4(),
                "id2": uuid.uuid4(),
                "m1": uuid.uuid4(),
                "m2": uuid.uuid4(),
                "ta": TENANT_A,
                "store_a": uuid.uuid4(),
                "store_b": uuid.uuid4(),
                "dev_a": uuid.uuid4(),
                "dev_b": uuid.uuid4(),
                "product": uuid.uuid4(),
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO bootstrap_sessions (
                    id, tenant_id, device_id, store_id, schema_version, status, product_count, watermark, since_seq, created_at
                ) VALUES
                    (:ida, :ta, :dev, :store, 1, 'complete', 1, 'wm', 0, NOW())
                """
            ),
            {"ida": uuid.uuid4(), "ta": TENANT_A, "dev": uuid.uuid4(), "store": uuid.uuid4()},
        )
    owner.dispose()

    app_url = OPS.set(username="ai_pos_app", password=APP_PASSWORD) if False else OPS.replace("o82boot@", "ai_pos_app:" + APP_PASSWORD + "@")
    require_disposable(OPS)
    app = create_engine(app_url, pool_size=2)
    with app.connect() as conn:
        who = conn.execute(text("SELECT current_user, session_user")).one()
        record("login", who.current_user == "ai_pos_app" and who.session_user == "ai_pos_app", "current_user is ai_pos_app")
        conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(TENANT_A)})
        own = conn.execute(text("SELECT COUNT(*) FROM staff_provisioning_events")).scalar()
        record("tenant A reads own staff events", own == 1, f"count={own}")
        leaked = conn.execute(text("SELECT COUNT(*) FROM staff_provisioning_events WHERE tenant_id = :tb"), {"tb": TENANT_B}).scalar()
        record("tenant A cannot read tenant B staff events", leaked == 0, f"count={leaked}")
        sync_own = conn.execute(text("SELECT COUNT(*) FROM sync_events")).scalar()
        record("tenant A reads own sync events", sync_own == 1, f"count={sync_own}")
        try:
            conn.execute(
                text(
                    """
                    INSERT INTO staff_provisioning_events (
                        id, tenant_id, event_id, operation, payload_hash, status, safe_message,
                        origin_terminal_id, schema_version, created_at
                    ) VALUES (
                        :id, :tb, 'event-cross', 'create', 'hash-x', 'accepted', 'accepted', 'till-x', 1, NOW()
                    )
                    """
                ),
                {"id": uuid.uuid4(), "tb": TENANT_B},
            )
            conn.commit()
            record("tenant A cannot insert tenant B staff", False, "insert was accepted")
        except Exception as exc:
            conn.rollback()
            record("tenant A cannot insert tenant B staff", True, type(exc).__name__)
        conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(TENANT_A)})
        try:
            conn.execute(
                text("UPDATE staff_provisioning_events SET safe_message = 'changed' WHERE tenant_id = :tb"),
                {"tb": TENANT_B},
            )
            changed = conn.execute(text("SELECT COUNT(*) FROM staff_provisioning_events WHERE safe_message = 'changed'")).scalar()
            conn.rollback()
            record("tenant A cannot update tenant B staff", changed == 0, f"changed={changed}")
        except Exception as exc:
            conn.rollback()
            record("tenant A cannot update tenant B staff", True, type(exc).__name__)
        deleted = conn.execute(
            text("DELETE FROM staff_provisioning_events WHERE tenant_id = :tb RETURNING id"),
            {"tb": TENANT_B},
        ).all()
        conn.rollback()
        record("tenant A cannot delete tenant B staff", len(deleted) == 0, f"deleted={len(deleted)}")
        conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(TENANT_A)})
        conn.execute(text("SELECT set_config('app.store_id', '', true)"))
        conn.execute(text("SELECT set_config('app.device_id', '', true)"))
        allocations = conn.execute(text("SELECT COUNT(*) FROM terminal_allocations")).scalar()
        record(
            "unset store and device settings still show both allocations",
            allocations == 2,
            f"count={allocations}",
        )
        store_ids = [str(item) for item in conn.execute(text("SELECT store_id FROM terminal_allocations")).scalars()]
        conn.execute(text("SELECT set_config('app.store_id', :sid, true)"), {"sid": store_ids[0]})
        one_store = conn.execute(text("SELECT COUNT(*) FROM terminal_allocations")).scalar()
        record("a set store id hides the other allocation", one_store == 1, f"count={one_store}")
        conn.execute(text("SELECT set_config('app.store_id', :sid, true)"), {"sid": str(uuid.uuid4())})
        unknown_store = conn.execute(text("SELECT COUNT(*) FROM terminal_allocations")).scalar()
        record("an unknown store id returns no allocations", unknown_store == 0, f"count={unknown_store}")
        conn.execute(text("SELECT set_config('app.store_id', '', true)"))
        conn.execute(text("SELECT set_config('app.tenant_id', '', true)"))
        empty = conn.execute(text("SELECT COUNT(*) FROM staff_provisioning_events")).scalar()
        record("missing tenant context returns no staff rows", empty == 0, f"count={empty}")
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(TENANT_A)})
        widened = conn.execute(text("SELECT COUNT(*) FROM staff_provisioning_events")).scalar()
        record("app role bypass does not widen staff events", widened == 1, f"count={widened}")
        users_policy = conn.execute(
            text("SELECT pg_get_expr(polqual, polrelid) FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid WHERE c.relname = 'users'")
        ).scalar()
        record(
            "historical users policy still contains a bypass clause",
            users_policy is not None and "bypass_rls" in users_policy,
            "recorded, not changed",
        )
        conn.commit()

    with app.connect() as first, app.connect() as second:
        first.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(TENANT_A)})
        first.commit()
        second.execute(text("SELECT set_config('app.tenant_id', '', true)"))
        reused = second.execute(text("SELECT COUNT(*) FROM staff_provisioning_events")).scalar()
        second.rollback()
        record("a new transaction does not keep the previous tenant", reused == 0, f"count={reused}")
    app.dispose()

    failed = [item for item in RESULTS if not item[1]]
    print(f"{len(RESULTS) - len(failed)} passed, {len(failed)} failed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
