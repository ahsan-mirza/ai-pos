"""Parallel work must not leave Alembic with two heads: `upgrade head` refuses to run when it does."""

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

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


def test_revision_ids_are_unique() -> None:
    for script in ("alembic", "alembic_control"):
        config = Config()
        config.set_main_option("script_location", str(API / script))
        revisions = list(ScriptDirectory.from_config(config).walk_revisions())
        ids = [revision.revision for revision in revisions]
        duplicates = sorted({rid for rid in ids if ids.count(rid) > 1})
        assert not duplicates, f"{script} reuses revision ids: {', '.join(duplicates)}"
