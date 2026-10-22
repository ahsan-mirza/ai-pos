"""Background jobs. Each run takes a lease row in scheduled_jobs, so with several API processes only one runs
a given job at a time; a crashed holder's lease simply expires."""

import logging
import os
import socket
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.scheduled_job import ScheduledJob

logger = logging.getLogger("ai_pos.jobs")
HOLDER = f"{socket.gethostname()}:{os.getpid()}"

JobFn = Callable[[Session, Settings], object]


@dataclass(frozen=True)
class Job:
    name: str
    description: str
    fn: JobFn
    # APScheduler trigger kwargs, e.g. {"trigger": "interval", "minutes": 1} or {"trigger": "cron", "hour": 2}
    trigger: dict[str, object]
    lease_seconds: int = 600

    @property
    def schedule(self) -> str:
        if self.trigger.get("trigger") == "interval":
            parts = [f"{value} {unit}" for unit, value in self.trigger.items() if unit != "trigger"]
            return "every " + ", ".join(parts)
        hour = int(self.trigger.get("hour", 0))
        minute = int(self.trigger.get("minute", 0))
        return f"daily at {hour:02d}:{minute:02d}"


JOBS: dict[str, Job] = {}


def register(job: Job) -> None:
    JOBS[job.name] = job


def _acquire(db: Session, name: str, lease_seconds: int) -> bool:
    now = datetime.now(UTC)
    if db.get(ScheduledJob, name) is None:
        db.add(ScheduledJob(name=name, run_count=0))
        db.commit()
    result = db.execute(
        update(ScheduledJob)
        .where(
            ScheduledJob.name == name,
            or_(ScheduledJob.locked_until.is_(None), ScheduledJob.locked_until < now),
        )
        .values(locked_until=now + timedelta(seconds=lease_seconds), locked_by=HOLDER, last_started_at=now)
    )
    db.commit()
    return result.rowcount == 1


def run_job(db: Session, settings: Settings, name: str) -> str:
    """Runs a job now if no other process holds its lease. Returns the job's status."""
    job = JOBS[name]
    if not _acquire(db, name, job.lease_seconds):
        return "busy"
    status, result = "ok", ""
    try:
        outcome = job.fn(db, settings)
        result = "" if outcome is None else str(outcome)
    except Exception as exc:  # noqa: BLE001 - recorded on the job row
        db.rollback()
        logger.exception("job %s failed", name)
        status, result = "error", str(exc)
    row = db.get(ScheduledJob, name)
    if row is not None:
        row.locked_until = None
        row.locked_by = None
        row.last_finished_at = datetime.now(UTC)
        row.last_status = status
        row.last_result = result[:2000]
        row.run_count += 1
        db.commit()
    return status
