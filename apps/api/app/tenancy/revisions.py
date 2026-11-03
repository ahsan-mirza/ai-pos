"""Tenant revision folders Alembic has to see before it decides what head is.

Reach revisions live in plugins/reach/backend/migrations and continue the tenant
chain. Alembic builds that chain from the config's version_locations. Passing
version_locations to context.configure() does not add them.
"""

import os
from dataclasses import dataclass
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = API_ROOT.parent.parent


def tenant_version_locations() -> list[str]:
    """Absolute version directories, joined later with os.pathsep for Alembic."""
    locations = [API_ROOT / "alembic" / "versions"]
    reach = REPO_ROOT / "plugins" / "reach" / "backend" / "migrations"
    if reach.is_dir():
        locations.append(reach)
    return [str(path) for path in locations]


def version_locations_option() -> str:
    return os.pathsep.join(tenant_version_locations())


def attach_tenant_versions(script) -> None:
    """Add plugin revisions when this ScriptDirectory was built from alembic.ini alone."""
    locations = tenant_version_locations()
    loaded = {Path(path).resolve() for path in script.version_locations}
    wanted = {Path(path).resolve() for path in locations}
    if wanted <= loaded:
        return
    script.version_locations = locations
    script.__dict__.pop("_version_locations", None)
    from alembic.script.revision import RevisionMap

    script.revision_map = RevisionMap(script._load_revisions)


class MigrationRefused(Exception):
    """The only available Alembic action would rebuild or roll back a database that already has rows."""


@dataclass(frozen=True)
class UpgradePlan:
    """Forward revisions to apply. `from_base` is only for a database with no application tables."""

    revisions: tuple[str, ...]
    from_base: bool


def _parent_ids(revision: object) -> tuple[str, ...]:
    down = revision.down_revision  # type: ignore[attr-defined]
    if down is None:
        return ()
    if isinstance(down, str):
        return (down,)
    return tuple(down)


def _is_ancestor(script, older: str, newer: str) -> bool:
    """True when `older` is `newer` or sits on the path of down_revisions behind it."""
    if older == newer:
        return True
    seen: set[str] = set()
    stack = [newer]
    while stack:
        current_id = stack.pop()
        if current_id in seen:
            continue
        seen.add(current_id)
        revision = script.get_revision(current_id)
        if revision is None:
            continue
        for parent in _parent_ids(revision):
            if parent == older:
                return True
            stack.append(parent)
    return False


def plan_upgrade(
    script,
    current: tuple[str, ...],
    head: str,
    *,
    has_application_tables: bool,
    label: str,
) -> UpgradePlan:
    """Revisions still ahead of `current`. Never a downgrade, and never a from-scratch replay over existing tables."""
    if len(current) > 1:
        stamped = ", ".join(current)
        raise MigrationRefused(
            f"{label} has several stamped revisions ({stamped}). Refusing to migrate so existing rows stay in place."
        )
    if current == (head,):
        return UpgradePlan((), False)
    if not current:
        if has_application_tables:
            raise MigrationRefused(
                f"{label} already has tables but no migration stamp. "
                "Refusing to run the history from the beginning, which would try to recreate those tables."
            )
        return UpgradePlan((), True)
    stamped = current[0]
    try:
        known = script.get_revision(stamped) is not None
    except Exception as error:
        # Alembic raises CommandError instead of returning None for an id this release does not contain.
        if type(error).__name__ not in {"CommandError", "ResolutionError"}:
            raise
        known = False
    if not known:
        raise MigrationRefused(
            f"{label} is stamped {stamped}, which is not in this release. "
            "Refusing to migrate so existing rows stay in place."
        )
    if not _is_ancestor(script, stamped, head):
        raise MigrationRefused(
            f"{label} is at {stamped}, which is not behind {head}. Refusing to downgrade or recreate existing tables."
        )
    pending = tuple(revision.revision for revision in reversed(list(script.iterate_revisions(head, stamped))))
    if not pending:
        raise MigrationRefused(
            f"{label} has no forward revision from {stamped} to {head}. Existing rows were left in place."
        )
    return UpgradePlan(pending, False)
