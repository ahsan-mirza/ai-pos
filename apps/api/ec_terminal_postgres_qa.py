# ruff: noqa: TID251
"""Disposable PostgreSQL checks for EC assignment constraints and control migrations.

Prints statuses only. Connection strings are never written.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

from app.core.config import get_settings
from app.tenancy.registry import control_url

ROOT = Path(__file__).resolve().parents[2]
NAMES = ("ecqa_fresh", "ecqa_upgrade", "ecqa_race")


def _safe(exc: BaseException) -> str:
    original = getattr(exc, "orig", None)
    code = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None) or ""
    detail = str(original or exc).splitlines()[0]
    if "://" in detail:
        detail = detail.split("://", 1)[0]
    return f"{type(exc).__name__} {code} {detail[:180]}".strip()


def _admin_engine(url):
    return create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")


def _drop(admin, name: str) -> None:
    with admin.connect() as connection:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :name AND pid <> pg_backend_pid()"
            ),
            {"name": name},
        )
        connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))


def _create(admin, name: str) -> None:
    _drop(admin, name)
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))


def _alembic(url: str, *args: str) -> None:
    env = os.environ.copy()
    env["APP_ENV"] = "development"
    env["CONTROL_DATABASE_URL"] = url
    completed = subprocess.run(
        ["node", "scripts/python.mjs", "--env=development", "-m", "alembic", "-c", "alembic_control.ini", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip().splitlines()
        detail = tail[-1] if tail else "alembic failed"
        if "://" in detail or "password" in detail.lower():
            detail = "alembic failed"
        raise RuntimeError(detail)


def _columns(engine, table: str) -> list[str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :table ORDER BY column_name"
            ),
            {"table": table},
        ).scalars()
        return list(rows)


def _version(engine) -> str:
    with engine.connect() as connection:
        for table in ("control_alembic_version", "alembic_version"):
            found = connection.execute(
                text("SELECT to_regclass(:name)"),
                {"name": table},
            ).scalar()
            if found:
                return str(connection.execute(text(f"SELECT version_num FROM {table}")).scalar())
    return "missing"


def audit_development(engine) -> tuple[int, int]:
    print("development revision", _version(engine))
    columns = _columns(engine, "hardware_assignments")
    expected = {"label", "register_id", "assigned_at", "assigned_by_user_id", "assignment_history"}
    print("assignment columns present", sorted(expected & set(columns)))
    print("assignment columns missing", sorted(expected - set(columns)))
    payment = _columns(engine, "commercial_payments")
    pay_expected = {"environment", "scenario", "provider_reference"}
    print("payment columns present", sorted(pay_expected & set(payment)))
    print("payment columns missing", sorted(pay_expected - set(payment)))
    with engine.connect() as connection:
        serials = connection.execute(
            text(
                "SELECT count(*) FROM ("
                " SELECT serial FROM hardware_assignments"
                " WHERE serial <> '' AND status <> 'returned'"
                " GROUP BY serial HAVING count(*) > 1) duplicates"
            )
        ).scalar()
        registers = connection.execute(
            text(
                "SELECT count(*) FROM ("
                " SELECT register_id FROM hardware_assignments"
                " WHERE register_id IS NOT NULL AND status = 'active'"
                " GROUP BY register_id HAVING count(*) > 1) duplicates"
            )
        ).scalar()
    print("duplicate active serial groups", int(serials or 0))
    print("duplicate active register groups", int(registers or 0))
    return int(serials or 0), int(registers or 0)


def fresh(admin, base) -> None:
    _create(admin, "ecqa_fresh")
    url = base.set(database="ecqa_fresh").render_as_string(hide_password=False)
    _alembic(url, "upgrade", "head")
    engine = create_engine(url)
    print("fresh revision", _version(engine))
    columns = set(_columns(engine, "hardware_assignments"))
    print("fresh assignment fields", {"label", "register_id", "assignment_history"} <= columns)
    payment = set(_columns(engine, "commercial_payments"))
    print("fresh payment fields", {"environment", "scenario", "provider_reference"} <= payment)
    engine.dispose()


def upgrade_from_0030(admin, base) -> None:
    _create(admin, "ecqa_upgrade")
    url = base.set(database="ecqa_upgrade").render_as_string(hide_password=False)
    _alembic(url, "upgrade", "control_0030")
    engine = create_engine(url)
    before = set(_columns(engine, "hardware_assignments"))
    print("at 0030 assignment extras absent", "label" not in before and "register_id" not in before)
    tenant_id = uuid.uuid4()
    category_id = uuid.uuid4()
    item_id = uuid.uuid4()
    order_id = uuid.uuid4()
    line_id = uuid.uuid4()
    assignment_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO tenants (id, slug, name, database_url_encrypted, status, profile, "
                "data_plane, plan, practice_mode, created_at, updated_at) "
                "VALUES (:id, 'ecqa', 'EC QA', 'x', 'active', 'electronics_wholesale', 'legacy', 'LITE', "
                "true, NOW(), NOW())"
            ),
            {"id": tenant_id},
        )
        connection.execute(
            text("INSERT INTO hardware_categories (id, name) VALUES (:id, 'QA terminals')"),
            {"id": category_id},
        )
        connection.execute(
            text(
                "INSERT INTO hardware_items (id, sku, name, category_id, updated_at) "
                "VALUES (:id, 'QA-1', 'QA terminal', :category, NOW())"
            ),
            {"id": item_id, "category": category_id},
        )
        connection.execute(
            text(
                "INSERT INTO hardware_orders (id, reference, tenant_id, created_at, updated_at) "
                "VALUES (:id, 'QA-0001', :tenant, NOW(), NOW())"
            ),
            {"id": order_id, "tenant": tenant_id},
        )
        connection.execute(
            text(
                "INSERT INTO hardware_order_lines (id, order_id, item_id, sku, name, mode, quantity, serials) "
                "VALUES (:id, :order_id, :item_id, 'QA-1', 'QA terminal', 'lease', 1, '[]')"
            ),
            {"id": line_id, "order_id": order_id, "item_id": item_id},
        )
        connection.execute(
            text(
                "INSERT INTO hardware_assignments "
                "(id, tenant_id, order_line_id, item_id, serial, quantity, status, created_at) "
                "VALUES (:id, :tenant, :line, :item, 'QA-SERIAL', 1, 'active', NOW())"
            ),
            {"id": assignment_id, "tenant": tenant_id, "line": line_id, "item": item_id},
        )
    engine.dispose()
    _alembic(url, "upgrade", "head")
    engine = create_engine(url)
    with engine.connect() as connection:
        serial = connection.execute(
            text("SELECT serial FROM hardware_assignments WHERE id = :id"),
            {"id": assignment_id},
        ).scalar()
    print("upgrade kept serial", serial == "QA-SERIAL")
    print("upgrade revision", _version(engine))
    engine.dispose()
    _alembic(url, "downgrade", "control_0030")
    engine = create_engine(url)
    after = set(_columns(engine, "hardware_assignments"))
    with engine.connect() as connection:
        serial = connection.execute(
            text("SELECT serial FROM hardware_assignments WHERE id = :id"),
            {"id": assignment_id},
        ).scalar()
    print("downgrade removed assignment extras", "label" not in after and "register_id" not in after)
    print("downgrade kept serial", serial == "QA-SERIAL")
    engine.dispose()


def race(admin, base) -> None:
    _create(admin, "ecqa_race")
    url = base.set(database="ecqa_race").render_as_string(hide_password=False)
    _alembic(url, "upgrade", "head")
    engine = create_engine(url)
    register_id = uuid.uuid4()
    ids = [uuid.uuid4(), uuid.uuid4()]
    with engine.begin() as connection:
        tenant_id = uuid.uuid4()
        category_id = uuid.uuid4()
        item_id = uuid.uuid4()
        order_id = uuid.uuid4()
        connection.execute(
            text(
                "INSERT INTO tenants (id, slug, name, database_url_encrypted, status, profile, "
                "data_plane, plan, practice_mode, created_at, updated_at) "
                "VALUES (:id, 'ecrace', 'EC Race', 'x', 'active', 'electronics_wholesale', 'legacy', "
                "'LITE', true, NOW(), NOW())"
            ),
            {"id": tenant_id},
        )
        connection.execute(
            text("INSERT INTO hardware_categories (id, name) VALUES (:id, 'Race terminals')"),
            {"id": category_id},
        )
        connection.execute(
            text(
                "INSERT INTO hardware_items (id, sku, name, category_id, updated_at) "
                "VALUES (:id, 'RACE-1', 'Race', :category, NOW())"
            ),
            {"id": item_id, "category": category_id},
        )
        connection.execute(
            text(
                "INSERT INTO hardware_orders (id, reference, tenant_id, created_at, updated_at) "
                "VALUES (:id, 'RACE-0001', :tenant, NOW(), NOW())"
            ),
            {"id": order_id, "tenant": tenant_id},
        )
        for index, assignment_id in enumerate(ids):
            line_id = uuid.uuid4()
            connection.execute(
                text(
                    "INSERT INTO hardware_order_lines (id, order_id, item_id, sku, name, mode, quantity, serials) "
                    "VALUES (:id, :order_id, :item_id, 'RACE-1', 'Race', 'purchase', 1, '[]')"
                ),
                {"id": line_id, "order_id": order_id, "item_id": item_id},
            )
            connection.execute(
                text(
                    "INSERT INTO hardware_assignments "
                    "(id, tenant_id, order_line_id, item_id, serial, quantity, status, created_at) "
                    "VALUES (:id, :tenant, :line, :item, :serial, 1, 'active', NOW())"
                ),
                {
                    "id": assignment_id,
                    "tenant": tenant_id,
                    "line": line_id,
                    "item": item_id,
                    "serial": f"RACE-{index}",
                },
            )
    results: list[str] = []
    barrier = threading.Barrier(2)

    def claim(assignment_id: uuid.UUID) -> None:
        local = create_engine(url)
        try:
            barrier.wait(timeout=10)
            with local.begin() as connection:
                connection.execute(
                    text("UPDATE hardware_assignments SET register_id = :register WHERE id = :id"),
                    {"register": register_id, "id": assignment_id},
                )
            results.append("ok")
        except Exception as exc:
            results.append(type(exc).__name__)
            print("race rejected", type(exc).__name__)
        finally:
            local.dispose()

    threads = [threading.Thread(target=claim, args=(assignment_id,)) for assignment_id in ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    winners = results.count("ok")
    with engine.connect() as connection:
        active = connection.execute(
            text(
                "SELECT count(*) FROM hardware_assignments "
                "WHERE register_id = :register AND status = 'active'"
            ),
            {"register": register_id},
        ).scalar()
    print("race winners", winners)
    print("race active rows", int(active or 0))
    engine.dispose()


def main() -> int:
    get_settings.cache_clear()
    settings = get_settings()
    if not settings.control_database_url:
        print("control database is not configured")
        return 1
    base = make_url(control_url(settings))
    admin = _admin_engine(base)
    try:
        serial_groups, register_groups = audit_development(create_engine(base))
        if serial_groups == 0 and register_groups == 0:
            _alembic(base.render_as_string(hide_password=False), "upgrade", "head")
            print("development upgraded", _version(create_engine(base)))
        else:
            print("development upgrade skipped")
        fresh(admin, base)
        upgrade_from_0030(admin, base)
        race(admin, base)
    finally:
        for name in NAMES:
            try:
                _drop(admin, name)
            except Exception as exc:
                print("cleanup", name, _safe(exc))
        admin.dispose()
    print("disposable databases dropped")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("qa failed", _safe(exc))
        sys.exit(1)
