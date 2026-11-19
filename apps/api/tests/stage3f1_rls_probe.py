"""Login as ai_pos_app against the disposable Stage 3F.1 database. Not a product test."""

from __future__ import annotations

import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

TENANT = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


def main() -> None:
    base = make_url(os.environ["DATABASE_URL"])
    if base.host != "127.0.0.1" or base.port != 55442 or base.database != "stage3f1_alembic":
        raise SystemExit("Refusing to probe a database that is not the disposable Stage 3F.1 target.")
    engine = create_engine(base.set(username="ai_pos_app"))
    with engine.connect() as conn:
        who = conn.execute(
            text(
                "SELECT current_user, "
                "(SELECT rolsuper FROM pg_roles WHERE rolname = current_user), "
                "(SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user)"
            )
        ).one()
        print(f"login={who[0]} super={who[1]} bypass={who[2]}")
        conn.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))
        conn.execute(text("SELECT set_config('app.tenant_id', '', true)"))
        print("empty_tenant_recalls", conn.execute(text("SELECT count(*) FROM pharmacy_recalls")).scalar())
        print("empty_tenant_products", conn.execute(text("SELECT count(*) FROM products")).scalar())
        try:
            conn.execute(
                text(
                    "INSERT INTO pharmacy_recalls "
                    "(id, tenant_id, reference, source_text, severity, reason, status, created_at) "
                    "VALUES ('cccccccc-cccc-4ccc-8ccc-cccccccccccc', :tenant, 'PROBE-LEAK', 'x', 'low', 'x', 'OPEN', now())"
                ),
                {"tenant": TENANT},
            )
            conn.commit()
            print("empty_tenant_insert UNEXPECTED_SUCCESS")
        except Exception as exc:  # noqa: BLE001 - the refusal is the result
            conn.rollback()
            print("empty_tenant_insert", type(exc).__name__)
        conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": OTHER})
        print("other_tenant_recalls", conn.execute(text("SELECT count(*) FROM pharmacy_recalls")).scalar())
        print("other_tenant_products", conn.execute(text("SELECT count(*) FROM products")).scalar())
        conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": TENANT})
        print("own_tenant_recalls", conn.execute(text("SELECT count(*) FROM pharmacy_recalls")).scalar())
        print("own_tenant_products", conn.execute(text("SELECT count(*) FROM products")).scalar())
        import time

        started = time.perf_counter()
        for _ in range(100):
            conn.execute(
                text(
                    "SELECT id FROM pharmacy_recalls "
                    "WHERE status = 'OPEN' ORDER BY created_at LIMIT 20"
                )
            ).all()
        elapsed = time.perf_counter() - started
        print(f"recall_lookup_100_ms {elapsed * 1000:.1f} per_call_ms {elapsed * 10:.2f}")
        conn.commit()


if __name__ == "__main__":
    main()
