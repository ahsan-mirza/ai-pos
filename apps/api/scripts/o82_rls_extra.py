"""Read-only follow-up on the disposable O8.2 database. Does not migrate."""

from __future__ import annotations

import uuid

from sqlalchemy import create_engine, text

OPS = "postgresql+psycopg://o82boot@127.0.0.1:55941/axizpos_o82"
APP = "postgresql+psycopg://ai_pos_app:o82-app-role-password@127.0.0.1:55941/axizpos_o82"
TENANT_A = "11111111-1111-4111-8111-11111111a821"
TENANT_B = "22222222-2222-4222-8222-22222222a821"
TABLES = (
    "users",
    "products",
    "sync_events",
    "bootstrap_sessions",
    "terminal_allocations",
    "staff_provisioning_events",
    "catalog_changes",
)


def main() -> None:
    owner = create_engine(OPS, isolation_level="AUTOCOMMIT")
    with owner.connect() as conn:
        who = conn.execute(text("SELECT current_database(), inet_server_port()")).one()
        print("database", who[0], "port", who[1])
        rows = conn.execute(
            text(
                """
                SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relname = ANY(:names)
                ORDER BY c.relname
                """
            ),
            {"names": list(TABLES)},
        )
        for row in rows:
            print("rls", row.relname, "enabled", row.relrowsecurity, "forced", row.relforcerowsecurity)
        policies = conn.execute(
            text(
                """
                SELECT c.relname, pg_get_expr(p.polqual, p.polrelid)
                FROM pg_policy p
                JOIN pg_class c ON c.oid = p.polrelid
                WHERE c.relname = ANY(:names)
                ORDER BY c.relname
                """
            ),
            {"names": list(TABLES)},
        )
        for row in policies:
            print("policy", row[0], row[1])
        role = conn.execute(
            text("SELECT id FROM roles WHERE tenant_id = :tid LIMIT 1"),
            {"tid": TENANT_A},
        ).scalar()
        if role is None:
            role = uuid.uuid4()
            conn.execute(text("SELECT set_config('app.bypass_rls', 'on', false)"))
            conn.execute(
                text(
                    """
                    INSERT INTO roles (id, tenant_id, name, description, is_system, created_at, updated_at)
                    VALUES (:id, :tid, 'Cashier', '', false, NOW(), NOW())
                    """
                ),
                {"id": role, "tid": TENANT_A},
            )
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', false)"))
        conn.execute(text("DELETE FROM users WHERE email LIKE 'o82-%'"))
        for tenant, name in ((TENANT_A, "a"), (TENANT_B, "b")):
            conn.execute(
                text(
                    """
                    INSERT INTO users (
                        id, tenant_id, username, email, full_name, hashed_password, is_active,
                        role_id, has_pos_access, has_portal_access, can_sell_open_price,
                        failed_login_attempts, token_version, reset_code_attempts, created_at, updated_at
                    ) VALUES (
                        :id, :tid, :username, :email, :full_name, 'not-a-secret', true,
                        :role, true, false, false, 0, 0, 0, NOW(), NOW()
                    )
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "tid": tenant,
                    "username": f"o82{name}",
                    "email": f"o82-{name}@example.test",
                    "full_name": f"O82 {name}",
                    "role": role,
                },
            )
    owner.dispose()

    app = create_engine(APP)
    with app.connect() as conn:
        who = conn.execute(text("SELECT current_user")).scalar()
        print("app_user", who)
        conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": TENANT_A})
        own = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
        other = conn.execute(text("SELECT COUNT(*) FROM users WHERE tenant_id = :tid"), {"tid": TENANT_B}).scalar()
        sync_other = conn.execute(text("SELECT COUNT(*) FROM sync_events WHERE tenant_id = :tid"), {"tid": TENANT_B}).scalar()
        print("users_as_a", own, "users_b_visible", other, "sync_b_visible", sync_other)
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        widened_users = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
        widened_staff = conn.execute(text("SELECT COUNT(*) FROM staff_provisioning_events")).scalar()
        print("bypass_users", widened_users, "bypass_staff", widened_staff)
        conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(uuid.uuid4())})
        missing = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
        print("unknown_tenant_users", missing)
        conn.rollback()
    app.dispose()


if __name__ == "__main__":
    main()
