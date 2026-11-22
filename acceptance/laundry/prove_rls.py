"""Row-level security as a real ai_pos_app login. SET ROLE is not used."""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
os.chdir(ROOT / "apps" / "api")

EVIDENCE = Path(__file__).resolve().parent / "evidence"


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
    tenants = {slug: uuid.UUID(value) for slug, value in rows}
    if set(tenants) != {"laundry-a", "grocery-b"}:
        raise SystemExit("Both acceptance tenants must be registered.")

    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        identity = conn.execute(
            text(
                "SELECT current_user, session_user, "
                "(SELECT rolsuper FROM pg_roles WHERE rolname = current_user), "
                "(SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user), "
                "(SELECT rolcanlogin FROM pg_roles WHERE rolname = current_user)"
            )
        ).one()
    if identity[0] != "ai_pos_app" or identity[1] != "ai_pos_app" or identity[2] or identity[3] or not identity[4]:
        raise SystemExit("Application login is not ai_pos_app without bypass.")

    now = datetime.now(UTC)
    category_id = uuid.uuid4()
    service_id = uuid.uuid4()
    code = category_id.hex[:12]
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenants["grocery-b"])})
        before = conn.execute(text("SELECT count(*) FROM brands")).scalar()
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenants["laundry-a"])})
        conn.execute(
            text(
                "INSERT INTO laundry_service_categories "
                "(id, tenant_id, code, name, display_order, is_active, created_at, updated_at) "
                "VALUES (:id, :tenant, :code, 'RLS category', 0, true, :now, :now)"
            ),
            {"id": category_id, "tenant": tenants["laundry-a"], "code": code, "now": now},
        )
        conn.execute(
            text(
                "INSERT INTO laundry_services (id, tenant_id, category_id, code, name, pricing_unit, "
                "base_rate_cents, min_charge_cents, min_quantity, weight_precision, tax_category, "
                "price_includes_tax, allow_zero_rate, turnaround_minutes, workflow_code, is_active, created_at, updated_at) "
                "VALUES (:id, :tenant, :category, :code, 'RLS piece', 'PIECE', 1000, 0, 0, 0, "
                "'STANDARD', false, false, 1440, '', true, :now, :now)"
            ),
            {"id": service_id, "tenant": tenants["laundry-a"], "category": category_id, "code": code, "now": now},
        )
    with engine.connect() as conn:
        hidden = conn.execute(text("SELECT count(*) FROM laundry_services")).scalar()
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenants["laundry-a"])})
        visible = conn.execute(text("SELECT count(*) FROM laundry_services WHERE id = :id"), {"id": service_id}).scalar()
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenants["grocery-b"])})
        foreign = conn.execute(text("SELECT count(*) FROM laundry_services WHERE id = :id"), {"id": service_id}).scalar()
        grocery_after = conn.execute(text("SELECT count(*) FROM brands")).scalar()
    update_state = None
    update_count = None
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenants["grocery-b"])})
            result = conn.execute(
                text("UPDATE laundry_services SET name = 'changed' WHERE id = :id"),
                {"id": service_id},
            )
            update_count = result.rowcount
    except DBAPIError as exc:
        update_state = _state(exc)
    move_state = None
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenants["laundry-a"])})
            conn.execute(
                text("UPDATE laundry_services SET tenant_id = :other WHERE id = :id"),
                {"id": service_id, "other": tenants["grocery-b"]},
            )
    except DBAPIError as exc:
        move_state = _state(exc)
    insert_state = None
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenants["grocery-b"])})
            conn.execute(
                text(
                    "INSERT INTO laundry_service_categories "
                    "(id, tenant_id, code, name, display_order, is_active, created_at, updated_at) "
                    "VALUES (:id, :tenant, 'cross', 'Cross', 0, true, :now, :now)"
                ),
                {"id": uuid.uuid4(), "tenant": tenants["laundry-a"], "now": now},
            )
    except DBAPIError as exc:
        insert_state = _state(exc)

    report = {
        "current_user": identity[0],
        "session_user": identity[1],
        "env_files": loaded,
        "developer_env_loaded": False,
        "missing_context_rows": hidden,
        "tenant_a_visible": visible,
        "tenant_b_visible": foreign,
        "grocery_brands_before": before,
        "grocery_brands_after": grocery_after,
        "cross_tenant_update_sqlstate": update_state,
        "cross_tenant_update_rows": update_count,
        "tenant_move_sqlstate": move_state,
        "cross_tenant_insert_sqlstate": insert_state,
    }
    passed = (
        hidden == 0
        and visible == 1
        and foreign == 0
        and before == grocery_after
        and update_count == 0
        and move_state == "42501"
        and insert_state == "42501"
    )
    report["result"] = "PASSED" if passed else "FAILED"
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "rls.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    if not passed:
        raise SystemExit(1)
    engine.dispose()


if __name__ == "__main__":
    main()
