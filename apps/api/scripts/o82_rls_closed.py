"""Unknown-tenant counts with bypass off. Disposable database only."""

from sqlalchemy import create_engine, text

APP = "postgresql+psycopg://ai_pos_app:o82-app-role-password@127.0.0.1:55941/axizpos_o82"


def main() -> None:
    engine = create_engine(APP)
    with engine.connect() as conn:
        print("user", conn.execute(text("SELECT current_user")).scalar())
        conn.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))
        conn.execute(
            text("SELECT set_config('app.tenant_id', '33333333-3333-4333-8333-333333333333', true)")
        )
        print("unknown_users", conn.execute(text("SELECT COUNT(*) FROM users")).scalar())
        print("unknown_sync", conn.execute(text("SELECT COUNT(*) FROM sync_events")).scalar())
        print("unknown_alloc", conn.execute(text("SELECT COUNT(*) FROM terminal_allocations")).scalar())
        print("unknown_staff", conn.execute(text("SELECT COUNT(*) FROM staff_provisioning_events")).scalar())
        conn.execute(text("SELECT set_config('app.tenant_id', '', true)"))
        print("empty_users", conn.execute(text("SELECT COUNT(*) FROM users")).scalar())
        print("empty_sync", conn.execute(text("SELECT COUNT(*) FROM sync_events")).scalar())
        conn.rollback()
    engine.dispose()


if __name__ == "__main__":
    main()
