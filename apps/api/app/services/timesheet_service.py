"""Time clock: entries synced from registers (offline-first), manager corrections, approval, and timesheets.

Overtime follows the UAE default of 8 normal hours a day: minutes worked beyond that on one day are overtime."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import Principal
from app.core.errors import ApiError, SyncRejected
from app.models.store import Store
from app.models.time_entry import TimeEntry
from app.models.user import User
from app.schemas.timesheets import (
    StaffTimesheet,
    TimeEntryOut,
    TimeEntryPayload,
    TimeEntryWrite,
    TimesheetReport,
)
from app.services.sync_service import SyncContext, register_handler
from app.services.sync_validation import parse_payload, require_store

DAILY_MINUTES = 8 * 60
FORGOTTEN_AFTER = timedelta(hours=16)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def worked_minutes(entry: TimeEntry) -> int:
    if entry.clock_out_at is None:
        return 0
    seconds = (_aware(entry.clock_out_at) - _aware(entry.clock_in_at)).total_seconds()
    return max(0, int(seconds // 60) - entry.break_minutes)


def apply_time_entry(db: Session, settings: Settings, payload: dict[str, object], ctx: SyncContext) -> uuid.UUID:
    data = parse_payload(TimeEntryPayload, payload)
    require_store(db, data.store_id)
    if db.get(User, data.user_id) is None:
        raise SyncRejected("The person clocking in does not exist.")
    entry = db.get(TimeEntry, data.id)
    if entry is None:
        entry = TimeEntry(
            id=data.id,
            user_id=data.user_id,
            store_id=data.store_id,
            device_id=ctx.device.id if ctx.device is not None else None,
            clock_in_at=data.clock_in_at,
            source="register",
        )
        db.add(entry)
    elif entry.user_id != data.user_id:
        raise SyncRejected("A time entry cannot move to another person.")
    elif entry.status == "APPROVED":
        return entry.id
    if entry.edited_by_id is None:
        entry.clock_in_at = data.clock_in_at
        entry.clock_out_at = data.clock_out_at
        entry.break_minutes = data.break_minutes
    entry.status = "CLOSED" if entry.clock_out_at is not None else "OPEN"
    return entry.id


register_handler("time_entry", apply_time_entry)


def _names(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, User]:
    wanted = {item for item in ids if item}
    return {user.id: user for user in db.scalars(select(User).where(User.id.in_(wanted))).unique()} if wanted else {}


def _overtime_by_entry(entries: list[TimeEntry]) -> dict[uuid.UUID, int]:
    """Overtime is counted per day: once a day's total passes 8 hours, the rest of that day is overtime."""
    out: dict[uuid.UUID, int] = {}
    by_day: dict[date, list[TimeEntry]] = defaultdict(list)
    for entry in entries:
        by_day[_aware(entry.clock_in_at).date()].append(entry)
    for day_entries in by_day.values():
        used = 0
        for entry in sorted(day_entries, key=lambda row: _aware(row.clock_in_at)):
            minutes = worked_minutes(entry)
            normal = max(0, min(minutes, DAILY_MINUTES - used))
            out[entry.id] = minutes - normal
            used += minutes
    return out


def report(
    db: Session, *, start: date, end: date, store_scope: uuid.UUID | None, user_id: uuid.UUID | None = None
) -> TimesheetReport:
    if end < start or (end - start).days > 62:
        raise ApiError(422, "validation_error", "Choose a period of at most two months.")
    since = datetime.combine(start, time.min, UTC)
    until = datetime.combine(end + timedelta(days=1), time.min, UTC)
    query = select(TimeEntry).where(TimeEntry.clock_in_at >= since, TimeEntry.clock_in_at < until)
    if store_scope is not None:
        query = query.where(TimeEntry.store_id == store_scope)
    if user_id is not None:
        query = query.where(TimeEntry.user_id == user_id)
    entries = list(db.scalars(query.order_by(TimeEntry.clock_in_at)))
    users = _names(
        db,
        {row.user_id for row in entries}
        | {row.edited_by_id for row in entries}
        | {row.approved_by_id for row in entries},
    )
    stores = {row.id: row.code for row in db.scalars(select(Store))}
    now = datetime.now(UTC)
    grouped: dict[uuid.UUID, list[TimeEntry]] = defaultdict(list)
    for entry in entries:
        grouped[entry.user_id].append(entry)
    staff = []
    for person_id, rows in grouped.items():
        overtime = _overtime_by_entry(rows)
        out = [
            TimeEntryOut(
                id=row.id,
                user_id=row.user_id,
                store_code=stores.get(row.store_id, ""),
                clock_in_at=_aware(row.clock_in_at),
                clock_out_at=_aware(row.clock_out_at) if row.clock_out_at else None,
                break_minutes=row.break_minutes,
                worked_minutes=worked_minutes(row),
                overtime_minutes=overtime.get(row.id, 0),
                status=row.status,  # type: ignore[arg-type]
                source=row.source,
                edit_note=row.edit_note,
                edited_by_name=users[row.edited_by_id].full_name if row.edited_by_id in users else None,
                approved_by_name=users[row.approved_by_id].full_name if row.approved_by_id in users else None,
                forgotten=row.clock_out_at is None and now - _aware(row.clock_in_at) > FORGOTTEN_AFTER,
            )
            for row in rows
        ]
        person = users.get(person_id)
        staff.append(
            StaffTimesheet(
                user_id=person_id,
                name=person.full_name if person else "Unknown",
                role_name=person.role.name if person and person.role else "",
                worked_minutes=sum(row.worked_minutes for row in out),
                overtime_minutes=sum(row.overtime_minutes for row in out),
                days_worked=len({row.clock_in_at.date() for row in out}),
                open_entries=sum(1 for row in out if row.status == "OPEN"),
                pending_approval=sum(1 for row in out if row.status == "CLOSED"),
                entries=out,
            )
        )
    staff.sort(key=lambda row: row.name.lower())
    return TimesheetReport(period_from=start, period_to=end, daily_hours=DAILY_MINUTES // 60, staff=staff)


def _editable(db: Session, principal: Principal, entry_id: uuid.UUID) -> TimeEntry:
    entry = db.get(TimeEntry, entry_id)
    if entry is None or (principal.store_id is not None and entry.store_id != principal.store_id):
        raise ApiError(404, "not_found", "Time entry was not found.")
    if entry.status == "APPROVED":
        raise ApiError(409, "approved", "This entry is approved; payroll may already use it.")
    return entry


def correct(db: Session, principal: Principal, entry_id: uuid.UUID, data: TimeEntryWrite) -> None:
    entry = _editable(db, principal, entry_id)
    entry.clock_in_at = data.clock_in_at
    entry.clock_out_at = data.clock_out_at
    entry.break_minutes = data.break_minutes
    entry.status = "CLOSED"
    entry.edited_by_id = principal.user.id if principal.user else None
    entry.edit_note = data.note.strip()
    db.commit()


def add_manual(db: Session, principal: Principal, data: TimeEntryWrite) -> None:
    if data.user_id is None or data.store_id is None:
        raise ApiError(422, "validation_error", "Choose the person and the branch.")
    if principal.store_id is not None and data.store_id != principal.store_id:
        raise ApiError(403, "store_scope", "You can only add time at your own branch.")
    if db.get(User, data.user_id) is None:
        raise ApiError(404, "not_found", "That person was not found.")
    db.add(
        TimeEntry(
            user_id=data.user_id,
            store_id=data.store_id,
            clock_in_at=data.clock_in_at,
            clock_out_at=data.clock_out_at,
            break_minutes=data.break_minutes,
            source="portal",
            status="CLOSED",
            edited_by_id=principal.user.id if principal.user else None,
            edit_note=data.note.strip(),
        )
    )
    db.commit()


def approve(db: Session, principal: Principal, entry_ids: list[uuid.UUID]) -> int:
    approved = 0
    now = datetime.now(UTC)
    for entry in db.scalars(select(TimeEntry).where(TimeEntry.id.in_(entry_ids))):
        if principal.store_id is not None and entry.store_id != principal.store_id:
            continue
        if entry.status != "CLOSED":
            continue
        entry.status = "APPROVED"
        entry.approved_by_id = principal.user.id if principal.user else None
        entry.approved_at = now
        approved += 1
    db.commit()
    return approved


def approved_minutes(db: Session, *, user_id: uuid.UUID, start: date, end: date) -> tuple[int, int]:
    """(normal, overtime) approved minutes for one person in a period, for payroll."""
    since = datetime.combine(start, time.min, UTC)
    until = datetime.combine(end + timedelta(days=1), time.min, UTC)
    entries = list(
        db.scalars(
            select(TimeEntry).where(
                TimeEntry.user_id == user_id,
                TimeEntry.status == "APPROVED",
                TimeEntry.clock_in_at >= since,
                TimeEntry.clock_in_at < until,
            )
        )
    )
    overtime = _overtime_by_entry(entries)
    total = sum(worked_minutes(entry) for entry in entries)
    extra = sum(overtime.values())
    return total - extra, extra
