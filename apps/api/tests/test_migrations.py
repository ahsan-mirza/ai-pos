"""Parallel work must not leave Alembic with two heads: `upgrade head` refuses to run when it does."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from app.tenancy.revisions import MigrationRefused, plan_upgrade, tenant_version_locations, version_locations_option

API = Path(__file__).resolve().parents[1]
BASELINE = "20261031_0094"
# Tables that already exist at 20261031_0094 and that later revisions alter or reference.
_BASELINE_TABLES = (
    "CREATE TABLE roles (id CHAR(32) PRIMARY KEY, tenant_id CHAR(32), name VARCHAR(80), is_system BOOLEAN)",
    "CREATE TABLE role_permissions (role_id CHAR(32), permission VARCHAR(80), tenant_id CHAR(32))",
    "CREATE TABLE business_settings (id CHAR(32) PRIMARY KEY)",
    "CREATE TABLE reach_campaigns (id CHAR(32) PRIMARY KEY)",
    "CREATE TABLE customers (id CHAR(32) PRIMARY KEY)",
    "CREATE TABLE outbound_messages (id CHAR(32) PRIMARY KEY)",
    "CREATE TABLE delivery_channels (id CHAR(32) PRIMARY KEY)",
    "CREATE TABLE stores (id CHAR(32) PRIMARY KEY)",
    "CREATE TABLE users (id CHAR(32) PRIMARY KEY)",
    "CREATE TABLE products (id CHAR(32) PRIMARY KEY)",
    "CREATE TABLE open_orders (id CHAR(32) PRIMARY KEY)",
    "CREATE TABLE sales (id CHAR(32) PRIMARY KEY)",
    "CREATE TABLE register_shifts (id CHAR(32) PRIMARY KEY)",
    """CREATE TABLE sales_orders (
        id CHAR(32) PRIMARY KEY,
        tenant_id CHAR(32) NOT NULL,
        source VARCHAR(12) NOT NULL,
        channel_ref VARCHAR(64)
    )""",
)


@pytest.mark.parametrize(("ini", "script"), [("alembic.ini", "alembic"), ("alembic_control.ini", "alembic_control")])
def test_each_migration_tree_has_a_single_head(ini: str, script: str) -> None:
    config = Config(str(API / ini))
    config.set_main_option("script_location", str(API / script))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1, (
        f"{script} has {len(heads)} heads: {', '.join(sorted(heads))}. "
        "Two migrations share a down_revision; renumber the newer one to follow the other."
    )


def test_committed_alembic_ini_discovers_reach_and_delivery() -> None:
    """`alembic upgrade` reads alembic.ini before env.py. The ini itself has to name every folder."""
    config = Config(str(API / "alembic.ini"))
    config.set_main_option("script_location", str(API / "alembic"))
    discovered = {Path(path).resolve() for path in config.get_version_locations_list() or []}
    expected = {Path(path).resolve() for path in tenant_version_locations()}
    assert discovered == expected
    script = ScriptDirectory.from_config(config)
    assert script.get_revision("20261105_0099") is not None
    assert script.get_revision("20261105_0098") is not None
    assert len(script.get_heads()) == 1


def test_api_versions_folder_alone_cannot_resolve_the_reach_parent() -> None:
    """The API folder does not contain 20261105_0099. Hiding the plugins must fail closed."""
    config = Config(str(API / "alembic.ini"))
    config.set_main_option("script_location", str(API / "alembic"))
    config.set_main_option("version_locations", str(API / "alembic" / "versions"))
    assert config.get_version_locations_list() == [str(API / "alembic" / "versions")]
    # The revision map is built on first use, not when the directory object is created.
    with pytest.raises(KeyError, match="20261105_0099"):
        ScriptDirectory.from_config(config).get_heads()


def test_every_parent_revision_exists_and_ids_are_unique() -> None:
    script = _tenant_script()
    seen: set[str] = set()
    for revision in script.walk_revisions():
        assert revision.revision not in seen, revision.revision
        seen.add(revision.revision)
        down = revision.down_revision
        parents = () if down is None else ((down,) if isinstance(down, str) else tuple(down))
        for parent in parents:
            assert script.get_revision(parent) is not None, f"{revision.revision} revises missing {parent}"
    assert "20261105_0099" in seen
    child = script.get_revision("20261109_0100")
    assert child is not None and child.down_revision == "20261105_0099"


def _sqlite_config(path: Path) -> Config:
    config = _tenant_config()
    config.attributes["database_url"] = f"sqlite:///{path.as_posix()}"
    return config


def _prepare(path: Path) -> Config:
    url = f"sqlite:///{path.as_posix()}"
    engine = create_engine(url)
    with engine.begin() as connection:
        for statement in _BASELINE_TABLES:
            connection.exec_driver_sql(statement)
    engine.dispose()
    return _sqlite_config(path)


def test_upgrade_and_downgrade_from_the_supported_baseline(tmp_path) -> None:
    """Apply and reverse the plugin span after 20261031_0094, then the timezone revision.

    20261109_0102 adds a foreign key with ALTER, which this SQLite build cannot run.
    That revision is left as it is. The span through 20261105_0099 is applied for real.
    """
    script = _tenant_script()
    head = script.get_heads()[0]
    forward = [revision.revision for revision in script.iterate_revisions(head, BASELINE)]
    assert forward[0] == head
    assert forward[-1] == "20261101_0095"
    assert "20261105_0098" in forward and "20261105_0099" in forward
    assert BASELINE not in forward
    for revision in script.iterate_revisions(head, BASELINE):
        assert callable(revision.module.upgrade) and callable(revision.module.downgrade)

    plugin = _prepare(tmp_path / "plugin.db")
    command.stamp(plugin, BASELINE)
    command.upgrade(plugin, "20261109_0101")
    command.downgrade(plugin, BASELINE)
    command.upgrade(plugin, "20261109_0101")
    engine = create_engine(plugin.get_main_option("sqlalchemy.url"))
    with engine.connect() as connection:
        version = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
        columns = {column["name"] for column in inspect(connection).get_columns("business_settings")}
        tables = set(inspect(connection).get_table_names())
    engine.dispose()
    assert version == "20261109_0101"
    assert "promotional_capabilities" in columns and "plan_capabilities" in columns
    assert "reach_ai_agents" in tables and "delivery_connections" in tables

    timezone = _prepare(tmp_path / "timezone.db")
    command.stamp(timezone, "20261112_0105")
    command.upgrade(timezone, "head")
    command.downgrade(timezone, "20261112_0105")
    command.upgrade(timezone, "head")
    engine = create_engine(timezone.get_main_option("sqlalchemy.url"))
    with engine.connect() as connection:
        version = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
        columns = {column["name"] for column in inspect(connection).get_columns("business_settings")}
    engine.dispose()
    assert version == head
    assert "timezone" in columns


def test_pending_upgrade_applies_only_revisions_after_the_stamp() -> None:
    script = _tenant_script()
    head = script.get_heads()[0]
    plan = plan_upgrade(script, ("20261031_0094",), head, has_application_tables=True, label="Tenant")
    assert plan.from_base is False
    assert plan.revisions[0] == "20261101_0095"
    assert plan.revisions[-1] == head
    assert "20261019_0001" not in plan.revisions


def test_database_at_head_is_left_in_place() -> None:
    script = _tenant_script()
    head = script.get_heads()[0]
    plan = plan_upgrade(script, (head,), head, has_application_tables=True, label="Tenant")
    assert plan.revisions == ()
    assert plan.from_base is False


def test_existing_tables_without_a_stamp_are_not_rebuilt() -> None:
    script = _tenant_script()
    head = script.get_heads()[0]
    with pytest.raises(MigrationRefused, match="already has tables"):
        plan_upgrade(script, (), head, has_application_tables=True, label="Tenant")


def test_empty_database_can_be_created_from_the_first_revision() -> None:
    script = _tenant_script()
    head = script.get_heads()[0]
    plan = plan_upgrade(script, (), head, has_application_tables=False, label="Tenant")
    assert plan.from_base is True
    assert plan.revisions == ()


def test_stamp_from_another_release_is_refused() -> None:
    script = _tenant_script()
    head = script.get_heads()[0]
    with pytest.raises(MigrationRefused, match="not in this release"):
        plan_upgrade(script, ("20990101_9999",), head, has_application_tables=True, label="Tenant")


def test_revision_that_is_not_behind_head_is_refused() -> None:
    class Revision:
        def __init__(self, revision: str, down: str | None) -> None:
            self.revision = revision
            self.down_revision = down

    class Script:
        def get_revision(self, revision: str) -> Revision | None:
            rows = {"base": Revision("base", None), "side": Revision("side", "base"), "head": Revision("head", "base")}
            return rows.get(revision)

        def iterate_revisions(self, _upper: str, _lower: str):
            raise AssertionError("a sideways revision must be refused before any upgrade list is built")

    with pytest.raises(MigrationRefused, match="not behind"):
        plan_upgrade(Script(), ("side",), "head", has_application_tables=True, label="Tenant")


def _tenant_config() -> Config:
    config = Config(str(API / "alembic.ini"))
    config.set_main_option("script_location", str(API / "alembic"))
    config.set_main_option("version_locations", version_locations_option())
    return config


def _tenant_script() -> ScriptDirectory:
    return ScriptDirectory.from_config(_tenant_config())


def test_shared_database_reads_the_console_stamp_not_the_store_stamp(tmp_path) -> None:
    from sqlalchemy import Column, MetaData, String, Table, insert

    from app.core.database import build_engine
    from app.tenancy import cli
    from app.tenancy.registry import control_version_table

    url = f"sqlite:///{(tmp_path / 'shared.db').as_posix()}"
    separate = "postgresql://localhost/qios_control"
    assert control_version_table(url, url) == "control_alembic_version"
    assert control_version_table(separate, "postgresql://localhost/ai_pos_db") == "alembic_version"

    meta = MetaData()
    store_version = Table("alembic_version", meta, Column("version_num", String(32), primary_key=True))
    console_version = Table("control_alembic_version", meta, Column("version_num", String(32), primary_key=True))
    Table("stores", meta, Column("id", String(32), primary_key=True))
    Table("tenants", meta, Column("id", String(32), primary_key=True))
    engine = build_engine(url)
    meta.create_all(engine)
    with engine.begin() as connection:
        connection.execute(insert(store_version).values(version_num="20261031_0094"))
        connection.execute(insert(console_version).values(version_num="control_0020"))
    engine.dispose()

    store_heads, store_exists = cli._database_state(
        url, version_table="alembic_version", marker_tables=cli._TENANT_MARKERS
    )
    console_heads, console_exists = cli._database_state(
        url, version_table="control_alembic_version", marker_tables=cli._CONTROL_MARKERS
    )
    assert store_heads == ("20261031_0094",)
    assert store_exists is True
    assert console_heads == ("control_0020",)
    assert console_exists is True

    script = _control_script()
    head = script.get_heads()[0]
    with pytest.raises(MigrationRefused, match="not in this release"):
        plan_upgrade(script, store_heads, head, has_application_tables=True, label="Control database")
    plan = plan_upgrade(script, console_heads, head, has_application_tables=True, label="Control database")
    assert plan.from_base is False
    assert plan.revisions[-1] == head
    assert "20261031_0094" not in plan.revisions


def _control_script() -> ScriptDirectory:
    config = Config(str(API / "alembic_control.ini"))
    config.set_main_option("script_location", str(API / "alembic_control"))
    return ScriptDirectory.from_config(config)


def test_revision_ids_are_unique() -> None:
    for script in ("alembic", "alembic_control"):
        config = Config(str(API / f"{script}.ini"))
        config.set_main_option("script_location", str(API / script))
        if script == "alembic":
            config.set_main_option("version_locations", version_locations_option())
        revisions = list(ScriptDirectory.from_config(config).walk_revisions())
        ids = [revision.revision for revision in revisions]
        duplicates = sorted({rid for rid in ids if ids.count(rid) > 1})
        assert not duplicates, f"{script} reuses revision ids: {', '.join(duplicates)}"
