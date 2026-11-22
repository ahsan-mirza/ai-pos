"""One cross-tenant write against the disposable O8.3 database."""

from sqlalchemy import create_engine, text

APP = "postgresql+psycopg://ai_pos_app:o83-app-role-password@127.0.0.1:55942/axizpos_o83"


def main() -> None:
    engine = create_engine(APP)
    with engine.connect() as conn:
        print("user", conn.execute(text("SELECT current_user")).scalar())
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        conn.execute(text("SELECT set_config('app.tenant_id', '11111111-1111-4111-8111-111111111a83', true)"))
        print("staff", conn.execute(text("SELECT COUNT(*) FROM staff_provisioning_events")).scalar())
        try:
            conn.execute(
                text(
                    """
                    INSERT INTO sync_events (
                        id, tenant_id, idempotency_key, device_id, entity_type, payload_hash, occurred_at, applied_at
                    ) VALUES (
                        gen_random_uuid(), '22222222-2222-4222-8222-222222222b83', 'cross', 'x', 'sale', 'h', NOW(), NOW()
                    )
                    """
                )
            )
            conn.commit()
            print("insert accepted")
        except Exception as exc:
            conn.rollback()
            print("insert", type(exc).__name__)
    engine.dispose()


if __name__ == "__main__":
    main()
