"""Order-table RLS as a real ai_pos_app login. SET ROLE is not used."""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
os.chdir(ROOT / "apps" / "api")

TABLES = (
    "laundry_orders",
    "laundry_garments",
    "laundry_bags",
    "laundry_tags",
    "laundry_tag_events",
    "laundry_photos",
    "laundry_order_events",
    "laundry_deposits",
)


def _state(exc: BaseException) -> str | None:
    orig = getattr(exc, "orig", None)
    if orig is None:
        return None
    return getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)


def main() -> None:
    from app.core.config import env_files, get_settings

    settings = get_settings()
    app_url = make_url(settings.database_url)
    if app_url.host != "127.0.0.1" or app_url.port != 55821 or app_url.username != "ai_pos_app":
        raise SystemExit("Refusing: the application URL is not the disposable laundry login.")
    if app_url.database != "axizpos_laundry_acceptance":
        raise SystemExit("Refusing: operational database is not the laundry acceptance database.")
    loaded = [path.name for path in env_files() if path.exists()]
    if ".env" in loaded or ".env.inventory-acceptance" in loaded:
        raise SystemExit("Refusing: a developer or inventory env file is loaded.")

    control = create_engine(settings.control_database_url)
    with control.connect() as conn:
        rows = conn.execute(text("SELECT slug, id::text FROM tenants WHERE slug IN ('laundry-a', 'grocery-b')")).all()
    control.dispose()
    tenants = {slug: value for slug, value in rows}

    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        identity = conn.execute(text("SELECT current_user, session_user")).one()
        forced = {
            name: conn.execute(
                text("SELECT relforcerowsecurity FROM pg_class WHERE relname = :name"),
                {"name": name},
            ).scalar()
            for name in TABLES
        }
        missing = conn.execute(text("SELECT count(*) FROM laundry_orders")).scalar()
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenants["laundry-a"]})
        own = conn.execute(text("SELECT count(*) FROM laundry_orders")).scalar()
        sample = conn.execute(text("SELECT id::text FROM laundry_orders ORDER BY created_at LIMIT 1")).scalar()
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenants["grocery-b"]})
        foreign = conn.execute(text("SELECT count(*) FROM laundry_orders")).scalar()
    update_count = None
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenants["grocery-b"]})
        update_count = conn.execute(
            text("UPDATE laundry_orders SET instructions = 'changed' WHERE id = :id"),
            {"id": sample},
        ).rowcount
    move_state = None
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenants["laundry-a"]})
            conn.execute(
                text("UPDATE laundry_orders SET tenant_id = :other WHERE id = :id"),
                {"id": sample, "other": tenants["grocery-b"]},
            )
    except DBAPIError as exc:
        move_state = _state(exc)
    insert_state = None
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenants["grocery-b"]})
            conn.execute(
                text(
                    "INSERT INTO laundry_orders ("
                    "id, tenant_id, idempotency_key, code, intake_store_id, customer_id, order_type, currency, "
                    "express, instructions, garment_count, bag_count, measured_weight, subtotal_cents, discount_cents, "
                    "surcharge_cents, tax_cents, total_cents, amount_paid_cents, balance_due_cents, payment_status, "
                    "operational_status, collection_status, claim_status, pricing_snapshot, version, created_at, updated_at"
                    ") SELECT :id, :tenant, :key, :code, intake_store_id, customer_id, order_type, currency, "
                    "false, '', 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 'UNPAID', 'RECEIVED', 'AT_BRANCH', 'NONE', "
                    "'{}'::json, 1, created_at, updated_at FROM laundry_orders WHERE false"
                ),
                {"id": str(uuid.uuid4()), "tenant": tenants["laundry-a"], "key": uuid.uuid4().hex, "code": "LD-CROSS"},
            )
    except DBAPIError as exc:
        insert_state = _state(exc)

    # The SELECT WHERE false insert inserts nothing, so it does not prove WITH CHECK.
    # Insert a concrete row using store and customer ids read as laundry-a.
    if insert_state is None:
        with engine.connect() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenants["laundry-a"]})
            source = conn.execute(
                text("SELECT intake_store_id::text, customer_id::text FROM laundry_orders WHERE id = :id"),
                {"id": sample},
            ).one()
        try:
            with engine.begin() as conn:
                conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenants["grocery-b"]})
                conn.execute(
                    text(
                        "INSERT INTO laundry_orders ("
                        "id, tenant_id, idempotency_key, code, intake_store_id, customer_id, order_type, currency, "
                        "express, instructions, garment_count, bag_count, measured_weight, subtotal_cents, discount_cents, "
                        "surcharge_cents, tax_cents, total_cents, amount_paid_cents, balance_due_cents, payment_status, "
                        "operational_status, collection_status, claim_status, pricing_snapshot, version, created_at, updated_at"
                        ") VALUES ("
                        ":id, :tenant, :key, 'LD-CROSS', :store, :customer, 'WALK_IN', 'USD', "
                        "false, '', 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 'UNPAID', 'RECEIVED', 'AT_BRANCH', 'NONE', "
                        "'{}'::json, 1, now(), now())"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "tenant": tenants["laundry-a"],
                        "key": uuid.uuid4().hex,
                        "store": source[0],
                        "customer": source[1],
                    },
                )
        except DBAPIError as exc:
            insert_state = _state(exc)

    report = {
        "current_user": identity[0],
        "session_user": identity[1],
        "developer_env_loaded": False,
        "forced": forced,
        "missing_context_orders": missing,
        "tenant_a_orders": own,
        "tenant_b_orders": foreign,
        "cross_tenant_update_rows": update_count,
        "tenant_move_sqlstate": move_state,
        "cross_tenant_insert_sqlstate": insert_state,
    }
    passed = (
        identity[0] == "ai_pos_app"
        and all(forced.values())
        and missing == 0
        and own >= 2
        and foreign == 0
        and update_count == 0
        and move_state == "42501"
        and insert_state == "42501"
    )
    report["result"] = "PASSED" if passed else "FAILED"
    evidence = Path(__file__).resolve().parent / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "order-rls.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"result": report["result"], "tenant_a_orders": own, "tenant_b_orders": foreign, "insert": insert_state, "move": move_state}))
    if not passed:
        raise SystemExit(1)
    engine.dispose()


if __name__ == "__main__":
    main()
