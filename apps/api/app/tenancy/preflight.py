"""Read-only production migration gate.

The approved window is one step: the operational parent may move to 20261118_0113, and the
registry parent may move to control_0040. The pharmacy revision 20261118_0114 is outside
that window, so a graph whose head is 0114 must not be upgraded with `upgrade head`.
"""

from __future__ import annotations

from dataclasses import dataclass

from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.tenancy.revisions import MigrationRefused, _is_ancestor, plan_upgrade

OPERATIONAL_TARGET = "20261118_0113"
OPERATIONAL_ALLOWED = frozenset({OPERATIONAL_TARGET, "20261114_0112"})
CONTROL_TARGET = "control_0040"
CONTROL_ALLOWED = frozenset({CONTROL_TARGET, "control_0039"})


@dataclass(frozen=True)
class HistoryView:
    database: str
    role: str
    current: str
    target: str
    pending: str
    tables: str
    safe: str
    reason: str

    def line(self) -> str:
        return (
            f"database={self.database} role={self.role} current={self.current} target={self.target} "
            f"pending={self.pending} tables={self.tables} safe={self.safe} reason={self.reason}"
        )


def judge_revision(
    current: tuple[str, ...],
    *,
    allowed: frozenset[str],
    target: str,
    has_tables: bool,
    known: bool,
    ahead: bool,
    pending: tuple[str, ...],
) -> tuple[bool, str]:
    """Decide whether one history may move, without applying anything."""
    if len(current) > 1:
        return False, "multiple stamped revisions"
    if not current:
        if has_tables:
            return False, "application tables exist without a stamp"
        return False, "database cannot be classified"
    if not known:
        return False, "revision is not in this release"
    if ahead:
        return False, "revision is ahead of the approved target"
    stamped = current[0]
    if stamped == target:
        if pending:
            return False, "stamp is the target but further revisions are pending"
        return True, "already at the approved target"
    if stamped not in allowed:
        return False, "revision is outside the approved window"
    if pending != (target,):
        return False, "pending revisions are not the single approved step"
    return True, "approved parent"


def _known(script: ScriptDirectory, revision: str) -> bool:
    try:
        return script.get_revision(revision) is not None
    except Exception as error:
        if type(error).__name__ not in {"CommandError", "ResolutionError"}:
            raise
        return False


def _ahead(script: ScriptDirectory, stamped: str, target: str) -> bool:
    return stamped != target and _is_ancestor(script, target, stamped)


def describe_history(
    script: ScriptDirectory,
    current: tuple[str, ...],
    *,
    database: str,
    role: str,
    allowed: frozenset[str],
    target: str,
    has_tables: bool,
) -> HistoryView:
    pending: tuple[str, ...] = ()
    known = True
    ahead = False
    if len(current) == 1:
        known = _known(script, current[0])
        if known:
            ahead = _ahead(script, current[0], target)
            if not ahead and current[0] != target:
                try:
                    plan = plan_upgrade(
                        script, current, target, has_application_tables=has_tables, label=database
                    )
                    pending = plan.revisions
                except MigrationRefused:
                    pending = ()
    safe, reason = judge_revision(
        current,
        allowed=allowed,
        target=target,
        has_tables=has_tables,
        known=known,
        ahead=ahead,
        pending=pending,
    )
    return HistoryView(
        database=database,
        role=role,
        current=current[0] if len(current) == 1 else (",".join(current) or "none"),
        target=target,
        pending=",".join(pending) or "none",
        tables="yes" if has_tables else "no",
        safe="yes" if safe else "no",
        reason=reason,
    )


def database_name(url: str) -> str:
    return make_url(url).database or "unnamed"


def collect_reports(settings, *, tenant_rows: list[tuple[str, str, str]]) -> list[HistoryView]:
    """Build the report. `tenant_rows` is (slug, data_plane, database_url) from the registry."""
    from app.tenancy import registry
    from app.tenancy.cli import _CONTROL_MARKERS, _TENANT_MARKERS, _alembic, _database_state, _one_head

    reports: list[HistoryView] = []
    tenant_script = ScriptDirectory.from_config(_alembic("alembic", "alembic.ini"))
    control_script = ScriptDirectory.from_config(_alembic("alembic_control", "alembic_control.ini"))
    _one_head(tenant_script, "Tenant migrations")
    _one_head(control_script, "Control migrations")

    control_url = registry.control_url(settings)
    control_table = registry.control_version_table(control_url, settings.database_url)
    reports.append(
        _view_url(
            control_script,
            control_url,
            role="registry",
            version_table=control_table,
            markers=_CONTROL_MARKERS,
            allowed=CONTROL_ALLOWED,
            target=CONTROL_TARGET,
            read_state=_database_state,
        )
    )

    seen: set[str] = set()
    shared_slugs: list[str] = []
    for slug, plane, url in tenant_rows:
        if plane == "shared":
            shared_slugs.append(slug)
            continue
        if url in seen:
            continue
        seen.add(url)
        reports.append(
            _view_url(
                tenant_script,
                url,
                role="tenant-store",
                version_table="alembic_version",
                markers=_TENANT_MARKERS,
                allowed=OPERATIONAL_ALLOWED,
                target=OPERATIONAL_TARGET,
                read_state=_database_state,
            )
        )

    if settings.database_url not in seen:
        reports.append(
            _view_url(
                tenant_script,
                settings.database_url,
                role="operational",
                version_table="alembic_version",
                markers=_TENANT_MARKERS,
                allowed=OPERATIONAL_ALLOWED,
                target=OPERATIONAL_TARGET,
                read_state=_database_state,
            )
        )
    if shared_slugs:
        reports.append(
            HistoryView(
                database=database_name(settings.database_url),
                role="shared-tenants",
                current=",".join(shared_slugs),
                target=OPERATIONAL_TARGET,
                pending="uses-operational-database",
                tables="same",
                safe="yes",
                reason="these stores share the operational database and are not migrated separately",
            )
        )
    return reports


def _view_url(script, url: str, *, role: str, version_table: str, markers, allowed, target, read_state) -> HistoryView:
    name = database_name(url)
    try:
        current, has_tables = read_state(url, version_table=version_table, marker_tables=markers)
    except OperationalError:
        return HistoryView(name, role, "unread", target, "none", "unread", "no", "database cannot be reached")
    return describe_history(
        script,
        current,
        database=name,
        role=role,
        allowed=allowed,
        target=target,
        has_tables=has_tables,
    )


def load_tenant_rows(session: Session) -> list[tuple[str, str, str]]:
    from sqlalchemy import select

    from app.tenancy.models import Tenant

    rows = []
    for row in session.scalars(select(Tenant).order_by(Tenant.slug)):
        rows.append((row.slug, row.data_plane, row.database_url))
    return rows
