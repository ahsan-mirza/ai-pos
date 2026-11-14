"""Disposable PostgreSQL rehearsal for 20261114_0112. Does not touch the development database."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from psycopg.types.json import Json  # noqa: TID251
from sqlalchemy import create_engine, inspect, text  # noqa: TID251

from app.core.config import get_settings
from app.core.database import create_database

NAMES = ("reach_mig_fresh", "reach_mig_upgrade")


def _server_url() -> str:
    url = get_settings().database_url
    if not url.startswith("postgresql"):
        raise SystemExit("This rehearsal needs the development Postgres server.")
    return url.rsplit("/", 1)[0] + "/postgres"


def _database_url(name: str) -> str:
    return get_settings().database_url.rsplit("/", 1)[0] + f"/{name}"


def _drop(name: str) -> None:
    engine = create_engine(_server_url(), isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        cursor = connection.connection.cursor()
        cursor.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
            (name,),
        )
        cursor.execute(f'DROP DATABASE IF EXISTS "{name}"')
    engine.dispose()


def _alembic(url: str) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["database_url"] = url
    return config


def _fresh() -> None:
    url = _database_url("reach_mig_fresh")
    command.upgrade(_alembic(url), "head")
    engine = create_engine(url)
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("reach_campaign_runs")}
    for name in (
        "prepare_after_id",
        "content_snapshot",
        "total_candidates",
        "invalid_contact_count",
        "no_consent_count",
        "duplicate_count",
        "report_version",
        "report_dirty",
    ):
        if name not in columns:
            raise SystemExit(f"fresh database is missing {name}")
    recipient = {column["name"] for column in inspector.get_columns("reach_recipients")}
    if "processing_started_at" not in recipient or "lease_until" not in recipient:
        raise SystemExit("fresh database is missing recipient lease columns")
    if "reach_report_artifacts" not in inspector.get_table_names():
        raise SystemExit("fresh database is missing reach_report_artifacts")
    version = engine.connect().execute(text("SELECT version_num FROM alembic_version")).scalar()
    engine.dispose()
    if version != "20261114_0112":
        raise SystemExit(f"fresh head is {version}")
    print("FRESH", version)


def _insert(connection, table: str, values: dict) -> None:
    columns = inspect(connection).get_columns(table)
    payload: dict = {}
    for column in columns:
        name = column["name"]
        if name in values:
            value = values[name]
            payload[name] = Json(value) if isinstance(value, (dict, list)) else value
            continue
        if column["nullable"] or column.get("default") is not None:
            continue
        kind = str(column["type"]).lower()
        if "int" in kind or "numeric" in kind:
            payload[name] = 0
        elif "bool" in kind:
            payload[name] = False
        elif "json" in kind:
            payload[name] = Json({})
        elif "char" in kind or "text" in kind:
            payload[name] = "legacy"
        elif "date" in kind:
            payload[name] = values["created_at"]
        else:
            raise SystemExit(f"{table}.{name} has no rehearsal value")
    names = ", ".join(payload)
    binds = ", ".join(f":{name}" for name in payload)
    connection.execute(text(f"INSERT INTO {table} ({names}) VALUES ({binds})"), payload)


def _upgrade_and_rollback() -> None:
    url = _database_url("reach_mig_upgrade")
    started = datetime.now(UTC)
    command.upgrade(_alembic(url), "20261114_0111")
    engine = create_engine(url)
    tenant_id = uuid.uuid4()
    campaign_id = uuid.uuid4()
    run_id = uuid.uuid4()
    now = datetime.now(UTC)
    with engine.begin() as connection:
        _insert(
            connection,
            "reach_campaigns",
            {
                "id": campaign_id,
                "tenant_id": tenant_id,
                "name": "Legacy",
                "description": "",
                "objective": "promotion",
                "status": "completed",
                "channels": ["email"],
                "audience": {},
                "content": {},
                "idempotency_key": "legacy-key",
                "eligible_count": 1,
                "suppressed_count": 0,
                "queued_count": 1,
                "created_at": now,
                "updated_at": now,
            },
        )
        _insert(
            connection,
            "reach_campaign_runs",
            {
                "id": run_id,
                "tenant_id": tenant_id,
                "campaign_id": campaign_id,
                "run_number": 1,
                "status": "completed",
                "channel": "email",
                "audience_type": "all",
                "audience_snapshot": {},
                "total_recipients": 1,
                "eligible_recipients": 1,
                "created_at": now,
                "updated_at": now,
            },
        )
        _insert(
            connection,
            "reach_recipients",
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "campaign_id": campaign_id,
                "phone": "0000",
                "body": "Hello",
                "status": "sent",
                "created_at": now,
                "updated_at": now,
            },
        )
        _insert(
            connection,
            "outbound_messages",
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "channel": "email",
                "to_address": "hidden@example.test",
                "template_key": "receipt",
                "priority": 1,
                "body": "Receipt",
                "status": "QUEUED",
                "provider_message_id": "provider-kept",
                "dedupe_key": "legacy-receipt",
                "next_attempt_at": now,
                "created_at": now,
            },
        )
    engine.dispose()
    command.upgrade(_alembic(url), "head")
    engine = create_engine(url)
    with engine.connect() as connection:
        run = connection.execute(
            text("SELECT run_number, status, report_version, total_candidates FROM reach_campaign_runs")
        ).one()
        if tuple(run) != (1, "completed", 0, 0):
            raise SystemExit(f"upgrade changed the existing run: {run}")
        null_run = connection.execute(
            text("SELECT count(*) FROM reach_recipients WHERE campaign_run_id IS NULL")
        ).scalar()
        if null_run != 1:
            raise SystemExit("legacy recipient with a null run id was not preserved")
        priority = connection.execute(
            text("SELECT priority, provider_message_id, status FROM outbound_messages")
        ).one()
        if tuple(priority) != (1, "provider-kept", "QUEUED"):
            raise SystemExit(f"outbox row changed: {priority}")
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    engine.dispose()
    if version != "20261114_0112":
        raise SystemExit(f"upgrade head is {version}")
    command.downgrade(_alembic(url), "20261114_0111")
    engine = create_engine(url)
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("reach_campaign_runs")}
    if "report_version" in columns or "reach_report_artifacts" in inspector.get_table_names():
        raise SystemExit("rollback left 0112 objects behind")
    with engine.connect() as connection:
        kept = connection.execute(text("SELECT count(*) FROM reach_campaign_runs")).scalar()
        people = connection.execute(text("SELECT count(*) FROM reach_recipients")).scalar()
        priority = connection.execute(text("SELECT priority FROM outbound_messages")).scalar()
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    engine.dispose()
    if (kept, people, priority, version) != (1, 1, 1, "20261114_0111"):
        raise SystemExit(f"rollback damaged existing rows: {(kept, people, priority, version)}")
    elapsed = (datetime.now(UTC) - started).total_seconds()
    print("UPGRADE_ROLLBACK", version, "seconds", round(elapsed, 3))


def _lock() -> None:
    url = _database_url("reach_mig_fresh")
    first = create_engine(url).connect()
    second = create_engine(url).connect()
    held = first.execute(text("SELECT pg_try_advisory_lock(48291017)")).scalar()
    blocked = second.execute(text("SELECT pg_try_advisory_lock(48291017)")).scalar()
    first.execute(text("SELECT pg_advisory_unlock(48291017)"))
    first.commit()
    released = second.execute(text("SELECT pg_try_advisory_lock(48291017)")).scalar()
    second.execute(text("SELECT pg_advisory_unlock(48291017)"))
    second.commit()
    first.close()
    second.close()
    if not held or blocked or not released:
        raise SystemExit(f"advisory lock result held={held} blocked={blocked} released={released}")
    print("LOCK", "held", bool(held), "second_blocked", not bool(blocked), "released", bool(released))


def main() -> None:
    for name in NAMES:
        _drop(name)
        create_database(_server_url(), name)
    try:
        _fresh()
        _lock()
        _upgrade_and_rollback()
    finally:
        for name in NAMES:
            _drop(name)
        print("DROPPED", ", ".join(NAMES))


if __name__ == "__main__":
    main()
