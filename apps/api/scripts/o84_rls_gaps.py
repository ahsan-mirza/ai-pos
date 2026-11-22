"""O8.4 RLS gaps on a new disposable cluster. Not the O8.3 database.

Opens only 127.0.0.1:55943 database axizpos_o84. The API logs in as ai_pos_app.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["APP_ENV"] = "acceptance"
os.environ["DATABASE_URL"] = "postgresql+psycopg://o82boot@127.0.0.1:55943/axizpos_o84"
os.environ["CONTROL_DATABASE_URL"] = ""
os.environ["JWT_SECRET"] = "o84-jwt-secret-must-be-32-chars!!"
os.environ["PIN_SALT"] = "o84-pin-pepper-16"
os.environ["ENCRYPTION_SECRET"] = "o84-encryption-secret-32-chars!!"
os.environ["API_KEY"] = "o84-api-key-value"
os.environ["CORS_ORIGINS"] = "http://127.0.0.1:18084"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["DEFAULT_TENANT"] = ""
os.environ["O84_RLS_HARNESS"] = "1"

import httpx
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.security import create_access_token
from app.models.business_settings import BusinessSettings
from app.models.product import Product
from app.models.role import Role, RolePermission
from app.models.store import Store
from app.models.sync_event import SyncEvent
from app.models.user import User
from app.tenancy.context import TenantRef, use_tenant

BOOT = "postgresql+psycopg://o82boot@127.0.0.1:55943/postgres"
OPS = os.environ["DATABASE_URL"]
APP = "postgresql+psycopg://ai_pos_app:o84-app-role-password@127.0.0.1:55943/axizpos_o84"
TENANT_A = uuid.UUID("11111111-1111-4111-8111-111111111a84")
TENANT_B = uuid.UUID("22222222-2222-4222-8222-222222222b84")
STORE_A = uuid.UUID("33333333-3333-4333-8333-333333333a84")
STORE_B = uuid.UUID("44444444-4444-4444-8444-444444444b84")
DEVICE_A = uuid.UUID("66666666-6666-4666-8666-666666666a84")
DEVICE_B = uuid.UUID("77777777-7777-4777-8777-777777777b84")
RESULTS: list[tuple[str, bool, str]] = []


def require_disposable(url: str) -> None:
    parsed = make_url(url)
    if parsed.host != "127.0.0.1" or parsed.port != 55943:
        raise SystemExit("Refusing: target is not the disposable O8.4 cluster.")
    if parsed.database not in {"postgres", "axizpos_o84"}:
        raise SystemExit("Refusing: database name is not disposable.")


def record(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, ok, detail))
    print(("PASS" if ok else "FAIL"), name, detail)


def seed(owner) -> dict[str, str]:
    factory = sessionmaker(bind=owner, expire_on_commit=False)
    settings = get_settings()
    tokens: dict[str, str] = {}
    now = datetime.now(UTC)
    for tenant, name in ((TENANT_A, "a"), (TENANT_B, "b")):
        ref = TenantRef(id=str(tenant), slug=name, name=name, database_url=OPS)
        with use_tenant(ref), factory() as db:
            role = Role(name=f"Manager {name}", description="", is_system=False)
            db.add(role)
            db.flush()
            for permission in ("portal:access", "users:read", "inventory:adjust_stock", "accounting:manage"):
                db.add(RolePermission(role_id=role.id, permission=permission, tenant_id=tenant))
            user = User(
                username=f"manager-{name}",
                email=f"manager-{name}@example.test",
                full_name=f"Manager {name}",
                hashed_password="not-used",
                is_active=True,
                store_id=None,
                role_id=role.id,
                has_pos_access=False,
                has_portal_access=True,
                token_version=0,
            )
            reviewer = User(
                username=f"reviewer-{name}",
                email=f"reviewer-{name}@example.test",
                full_name=f"Reviewer {name}",
                hashed_password="not-used",
                is_active=True,
                store_id=None,
                role_id=role.id,
                has_pos_access=False,
                has_portal_access=True,
                token_version=0,
            )
            db.add(user)
            db.add(reviewer)
            db.add(BusinessSettings(id=uuid.uuid4(), currency="USD"))
            db.add(Product(sku=f"sku-{name}", barcode=f"bar-{name}", name=f"Product {name}", category="Grocery", price_cents=100, currency="USD"))
            db.add(SyncEvent(idempotency_key=f"sale-{name}", device_id=f"till-{name}", entity_type="sale", payload_hash="hash", occurred_at=now, applied_at=now))
            db.commit()
            for label, person in (("manager", user), ("reviewer", reviewer)):
                token, _ = create_access_token(subject=str(person.id), scope="portal", token_version=0, settings=settings, tenant_id=str(tenant))
                tokens[f"{label}-{name}"] = token
    with factory() as db, use_tenant(TenantRef(id=str(TENANT_A), slug="a", name="a", database_url=OPS)):
        for store, code in ((STORE_A, "A"), (STORE_B, "B")):
            db.add(Store(id=store, code=code, name=f"Store {code}", currency="USD"))
            db.flush()
        db.commit()
    return tokens


def extra(owner) -> None:
    now = datetime.now(UTC)
    with owner.begin() as conn:
        for tenant, event in ((TENANT_A, "event-a"), (TENANT_B, "event-b")):
            conn.execute(
                text(
                    """
                    INSERT INTO staff_provisioning_events
                      (id, tenant_id, event_id, operation, payload_hash, status, safe_message, origin_terminal_id, schema_version, created_at)
                    VALUES (:id, :tenant, :event, 'create', 'hash', 'pending', '', 'till', 1, :now)
                    """
                ),
                {"id": uuid.uuid4(), "tenant": tenant, "event": event, "now": now},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO catalog_changes (id, tenant_id, seq, dataset, record_id, operation, payload)
                    VALUES (:id, :tenant, 1, 'product', :record, 'create', '{}')
                    """
                ),
                {"id": uuid.uuid4(), "tenant": tenant, "record": event},
            )
        for tenant, store, device, session in (
            (TENANT_A, STORE_A, DEVICE_A, uuid.UUID("88888888-8888-4888-8888-888888888a84")),
            (TENANT_A, STORE_B, DEVICE_B, uuid.UUID("99999999-9999-4999-8999-999999999b84")),
        ):
            conn.execute(
                text(
                    """
                    INSERT INTO bootstrap_sessions
                      (id, tenant_id, device_id, store_id, schema_version, status, product_count, watermark, since_seq, created_at)
                    VALUES (:id, :tenant, :device, :store, 1, 'open', 1, 'w', 0, :now)
                    """
                ),
                {"id": session, "tenant": tenant, "device": device, "store": store, "now": now},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO bootstrap_snapshot_items (session_id, position, tenant_id, product_id, payload)
                    VALUES (:session, 1, :tenant, :product, '{}')
                    """
                ),
                {"session": session, "tenant": tenant, "product": uuid.uuid4()},
            )
        conn.execute(
            text(
                """
                INSERT INTO bootstrap_snapshot_items (session_id, position, tenant_id, product_id, payload)
                VALUES (:session, 2, :tenant, :product, '{}')
                """
            ),
            {"session": uuid.UUID("88888888-8888-4888-8888-888888888a84"), "tenant": TENANT_B, "product": uuid.uuid4()},
        )
        conn.execute(
            text(
                """
                INSERT INTO lost_terminal_requests (
                  id, tenant_id, created_at, updated_at, store_id, device_id, last_sequence, quantity,
                  reason, evidence, idempotency_key, status, posting_status, submitted_by_id
                )
                SELECT :id, :tenant, :now, :now, :store, :device, 1, 1, 'lost', '', 'seed-a', 'submitted', 'awaiting_approval', id
                FROM users WHERE username = 'manager-a'
                """
            ),
            {"id": uuid.uuid4(), "tenant": TENANT_A, "now": now, "store": STORE_A, "device": DEVICE_A},
        )


def scope(conn, tenant: str, store: str = "") -> None:
    conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
    conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant})
    conn.execute(text("SELECT set_config('app.store_id', :s, true)"), {"s": store})
    conn.execute(text("SELECT set_config('app.device_id', '', true)"))


def main() -> None:
    require_disposable(BOOT)
    require_disposable(OPS)
    admin = create_engine(BOOT, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS axizpos_o84"))
        conn.execute(text("CREATE DATABASE axizpos_o84"))
    admin.dispose()
    os.chdir(os.path.join(os.path.dirname(__file__), ".."))
    config = Config("alembic.ini")
    config.attributes["database_url"] = OPS
    command.upgrade(config, "head")
    owner = create_engine(OPS, isolation_level="AUTOCOMMIT")
    with owner.connect() as conn:
        if conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'ai_pos_app'")).scalar() is None:
            conn.exec_driver_sql(
                "CREATE ROLE ai_pos_app LOGIN PASSWORD 'o84-app-role-password' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
            )
        conn.execute(text("GRANT CONNECT ON DATABASE axizpos_o84 TO ai_pos_app"))
        conn.execute(text("GRANT USAGE ON SCHEMA public TO ai_pos_app"))
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ai_pos_app"))
        conn.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ai_pos_app"))
        role = conn.execute(text("SELECT rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname = 'ai_pos_app'")).one()
        record("role", role.rolcanlogin and not role.rolsuper and not role.rolbypassrls, "LOGIN NOSUPERUSER NOBYPASSRLS")
    tokens = seed(owner)
    extra(owner)
    owner.dispose()

    env = os.environ.copy()
    env["DATABASE_URL"] = APP
    api = subprocess.Popen(
        [os.environ.get("O84_PYTHON", sys.executable), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "18084"],
        env=env,
        cwd=os.getcwd(),
    )
    try:
        identity = None
        for _ in range(40):
            try:
                response = httpx.get("http://127.0.0.1:18084/o83-harness-identity", timeout=2)
                if response.status_code == 200:
                    identity = response.json()
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        record("api identity", identity == {"role": "ai_pos_app", "database": "axizpos_o84", "port": "55943"}, str(identity))
        headers = {"Authorization": f"Bearer {tokens['manager-a']}", "X-O83-Tenant": str(TENANT_A)}
        created = httpx.post(
            "http://127.0.0.1:18084/api/v1/inventory/lost-terminal-requests",
            headers=headers,
            json={
                "store_id": str(STORE_A),
                "device_id": str(DEVICE_A),
                "last_sequence": 3,
                "quantity": 2,
                "reason": "till missing",
                "evidence": "test",
                "idempotency_key": "api-lost-a",
            },
            timeout=15,
        )
        record("api lost-terminal submit", created.status_code == 201 and created.json().get("posting_status") == "awaiting_approval", f"{created.status_code} {created.text[:180]}")
        other = httpx.post(
            "http://127.0.0.1:18084/api/v1/inventory/lost-terminal-requests",
            headers={"Authorization": f"Bearer {tokens['manager-b']}", "X-O83-Tenant": str(TENANT_A)},
            json={
                "store_id": str(STORE_A),
                "device_id": str(DEVICE_A),
                "last_sequence": 1,
                "quantity": 1,
                "reason": "cross",
                "idempotency_key": "cross",
            },
            timeout=15,
        )
        record("api rejects other tenant token", other.status_code == 401, str(other.status_code))
    finally:
        api.terminate()
        api.wait(timeout=20)

    app = create_engine(APP)
    with app.connect() as conn:
        scope(conn, str(TENANT_A))
        record("staff stays one with bypass", conn.execute(text("SELECT COUNT(*) FROM staff_provisioning_events")).scalar() == 1, "staff")
        record("catalog stays one with bypass", conn.execute(text("SELECT COUNT(*) FROM catalog_changes")).scalar() == 1, "catalog")
        record("snapshots stay in tenant", conn.execute(text("SELECT COUNT(*) FROM bootstrap_snapshot_items")).scalar() == 2, "snapshots")
        hidden = conn.execute(text("SELECT COUNT(*) FROM bootstrap_sessions")).scalar()
        record("missing store hides bootstrap", hidden == 0, f"count={hidden}")
        scope(conn, str(TENANT_A), str(STORE_A))
        record("store A bootstrap", conn.execute(text("SELECT COUNT(*) FROM bootstrap_sessions")).scalar() == 1, "bootstrap")
        record("store A lost requests", conn.execute(text("SELECT COUNT(*) FROM lost_terminal_requests")).scalar() >= 1, "lost")
        scope(conn, str(TENANT_A), str(STORE_B))
        record("store B hides store A lost request", conn.execute(text("SELECT COUNT(*) FROM lost_terminal_requests WHERE idempotency_key = 'seed-a'")).scalar() == 0, "lost-b")
        updated = conn.execute(text("UPDATE users SET full_name = 'hacked' WHERE username = 'manager-b'")).rowcount
        record("cross-tenant update changes nothing", updated == 0, f"rows={updated}")
        deleted = conn.execute(text("DELETE FROM products WHERE name = 'Product b'")).rowcount
        record("cross-tenant delete changes nothing", deleted == 0, f"rows={deleted}")
        try:
            conn.execute(
                text(
                    """
                    INSERT INTO staff_provisioning_events
                      (id, tenant_id, event_id, operation, payload_hash, status, safe_message, origin_terminal_id, schema_version, created_at)
                    VALUES (:id, :tenant, 'cross', 'create', 'h', 'pending', '', 't', 1, NOW())
                    """
                ),
                {"id": uuid.uuid4(), "tenant": TENANT_B},
            )
            record("cross-tenant staff insert", False, "accepted")
        except Exception as exc:
            record("cross-tenant staff insert", type(exc).__name__ == "ProgrammingError", type(exc).__name__)
        conn.rollback()
        empty = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
        record("rollback clears tenant context", empty == 0, f"count={empty}")
    fresh = app.connect()
    leaked = fresh.execute(text("SELECT COUNT(*) FROM users")).scalar()
    record("new connection has no tenant", leaked == 0, f"count={leaked}")
    fresh.close()
    app.dispose()
    failed = [item for item in RESULTS if not item[1]]
    print(f"{len(RESULTS) - len(failed)} passed, {len(failed)} failed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
