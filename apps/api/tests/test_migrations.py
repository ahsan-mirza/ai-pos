"""Parallel work must not leave Alembic with two heads: `upgrade head` refuses to run when it does."""

import os
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.tenancy.revisions import MigrationRefused, plan_upgrade, tenant_version_locations

API = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(("ini", "script"), [("alembic.ini", "alembic"), ("alembic_control.ini", "alembic_control")])
def test_each_migration_tree_has_a_single_head(ini: str, script: str) -> None:
    config = Config(str(API / ini))
    config.set_main_option("script_location", str(API / script))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1, (
        f"{script} has {len(heads)} heads: {', '.join(sorted(heads))}. "
        "Two migrations share a down_revision; renumber the newer one to follow the other."
    )


def test_reach_revisions_are_on_the_tenant_head() -> None:
    """Production head includes plugins/reach. The API versions folder alone stops at an older revision."""
    core = Config(str(API / "alembic.ini"))
    core.set_main_option("script_location", str(API / "alembic"))
    core_heads = ScriptDirectory.from_config(core).get_heads()

    full = Config(str(API / "alembic.ini"))
    full.set_main_option("script_location", str(API / "alembic"))
    full.set_main_option("version_locations", os.pathsep.join(tenant_version_locations()))
    script = ScriptDirectory.from_config(full)
    heads = script.get_heads()
    assert len(heads) == 1, f"tenant migrations have {len(heads)} heads: {', '.join(sorted(heads))}"
    assert heads != core_heads

    reach = API.parent.parent / "plugins" / "reach" / "backend" / "migrations"
    assert any(reach in Path(revision.path).parents for revision in script.walk_revisions())


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


def _tenant_script() -> ScriptDirectory:
    config = Config(str(API / "alembic.ini"))
    config.set_main_option("script_location", str(API / "alembic"))
    config.set_main_option("version_locations", os.pathsep.join(tenant_version_locations()))
    return ScriptDirectory.from_config(config)


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
            config.set_main_option("version_locations", os.pathsep.join(tenant_version_locations()))
        revisions = list(ScriptDirectory.from_config(config).walk_revisions())
        ids = [revision.revision for revision in revisions]
        duplicates = sorted({rid for rid in ids if ids.count(rid) > 1})
        assert not duplicates, f"{script} reuses revision ids: {', '.join(duplicates)}"
