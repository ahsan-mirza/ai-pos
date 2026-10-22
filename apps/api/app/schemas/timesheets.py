from datetime import date, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.schemas.payloads import ApiModel

MAX_SHIFT_HOURS = 24


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError("Times must include a timezone.")
    return value


class TimeEntryPayload(ApiModel):
    """Sent by the register at clock-in (no clock_out_at) and again at clock-out."""

    id: UUID
    user_id: UUID
    store_id: UUID
    clock_in_at: datetime
    clock_out_at: datetime | None = None
    break_minutes: int = Field(default=0, ge=0, le=600)

    @field_validator("clock_in_at", "clock_out_at")
    @classmethod
    def with_timezone(cls, value: datetime | None) -> datetime | None:
        return _aware(value)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.clock_out_at is not None:
            hours = (self.clock_out_at - self.clock_in_at).total_seconds() / 3600
            if hours <= 0:
                raise ValueError("Clock-out must be after clock-in.")
            if hours > MAX_SHIFT_HOURS:
                raise ValueError(f"A single entry cannot be longer than {MAX_SHIFT_HOURS} hours.")
            if self.break_minutes >= hours * 60:
                raise ValueError("The break is longer than the time worked.")
        return self


class TimeEntryWrite(ApiModel):
    """A manager's correction or a forgotten clock-in entered on the portal."""

    user_id: UUID | None = None
    store_id: UUID | None = None
    clock_in_at: datetime
    clock_out_at: datetime
    break_minutes: int = Field(default=0, ge=0, le=600)
    note: str = Field(min_length=3, max_length=255)

    @field_validator("clock_in_at", "clock_out_at")
    @classmethod
    def with_timezone(cls, value: datetime) -> datetime | None:
        return _aware(value)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        hours = (self.clock_out_at - self.clock_in_at).total_seconds() / 3600
        if hours <= 0 or hours > MAX_SHIFT_HOURS:
            raise ValueError(f"Clock-out must be after clock-in and within {MAX_SHIFT_HOURS} hours.")
        if self.break_minutes >= hours * 60:
            raise ValueError("The break is longer than the time worked.")
        return self


class TimesheetApprove(ApiModel):
    entry_ids: list[UUID] = Field(min_length=1, max_length=1000)


class TimeEntryOut(ApiModel):
    id: UUID
    user_id: UUID
    store_code: str
    clock_in_at: datetime
    clock_out_at: datetime | None
    break_minutes: int
    worked_minutes: int
    overtime_minutes: int
    status: Literal["OPEN", "CLOSED", "APPROVED"]
    source: str
    edit_note: str
    edited_by_name: str | None
    approved_by_name: str | None
    # An entry still open after 16 hours: the person probably forgot to clock out.
    forgotten: bool


class StaffTimesheet(ApiModel):
    user_id: UUID
    name: str
    role_name: str
    worked_minutes: int
    overtime_minutes: int
    days_worked: int
    open_entries: int
    pending_approval: int
    entries: list[TimeEntryOut]


class TimesheetReport(ApiModel):
    period_from: date
    period_to: date
    daily_hours: int
    staff: list[StaffTimesheet]
