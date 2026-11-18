"""The production window is one approved step. Pharmacy 0114 is outside it."""

from app.tenancy.preflight import (
    CONTROL_ALLOWED,
    CONTROL_TARGET,
    OPERATIONAL_ALLOWED,
    OPERATIONAL_TARGET,
    HistoryView,
    judge_revision,
)


def test_parent_revision_is_the_only_forward_step() -> None:
    safe, reason = judge_revision(
        ("20261114_0112",),
        allowed=OPERATIONAL_ALLOWED,
        target=OPERATIONAL_TARGET,
        has_tables=True,
        known=True,
        ahead=False,
        pending=(OPERATIONAL_TARGET,),
    )
    assert safe is True
    assert reason == "approved parent"


def test_database_already_at_the_target_is_safe() -> None:
    safe, reason = judge_revision(
        (CONTROL_TARGET,),
        allowed=CONTROL_ALLOWED,
        target=CONTROL_TARGET,
        has_tables=True,
        known=True,
        ahead=False,
        pending=(),
    )
    assert safe is True
    assert reason == "already at the approved target"


def test_revision_ahead_of_the_target_is_refused() -> None:
    safe, reason = judge_revision(
        ("20261118_0114",),
        allowed=OPERATIONAL_ALLOWED,
        target=OPERATIONAL_TARGET,
        has_tables=True,
        known=True,
        ahead=True,
        pending=(),
    )
    assert safe is False
    assert reason == "revision is ahead of the approved target"


def test_unstamped_tables_unknown_revisions_and_extra_steps_are_refused() -> None:
    unstamped, _ = judge_revision(
        (),
        allowed=OPERATIONAL_ALLOWED,
        target=OPERATIONAL_TARGET,
        has_tables=True,
        known=True,
        ahead=False,
        pending=(),
    )
    unknown, _ = judge_revision(
        ("20990101_9999",),
        allowed=OPERATIONAL_ALLOWED,
        target=OPERATIONAL_TARGET,
        has_tables=True,
        known=False,
        ahead=False,
        pending=(),
    )
    several, _ = judge_revision(
        ("20261114_0112",),
        allowed=OPERATIONAL_ALLOWED,
        target=OPERATIONAL_TARGET,
        has_tables=True,
        known=True,
        ahead=False,
        pending=("20261118_0113", "20261118_0114"),
    )
    older, older_reason = judge_revision(
        ("20261031_0094",),
        allowed=OPERATIONAL_ALLOWED,
        target=OPERATIONAL_TARGET,
        has_tables=True,
        known=True,
        ahead=False,
        pending=(),
    )
    assert unstamped is False
    assert unknown is False
    assert several is False
    assert older is False
    assert older_reason == "revision is outside the approved window"


def test_report_line_names_the_database_and_not_a_url() -> None:
    line = HistoryView(
        database="ai_pos",
        role="operational",
        current="20261114_0112",
        target=OPERATIONAL_TARGET,
        pending=OPERATIONAL_TARGET,
        tables="yes",
        safe="yes",
        reason="approved parent",
    ).line()
    assert "database=ai_pos" in line
    assert "://" not in line
    assert "@" not in line
