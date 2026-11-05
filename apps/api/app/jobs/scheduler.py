"""In-process APScheduler. Started from the API lifespan unless SCHEDULER_ENABLED is false."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import Settings
from app.core.database import get_session_factory
from app.jobs import catalog as _catalog  # noqa: F401  registers the jobs
from app.jobs.runner import JOBS, run_job
from app.tenancy.context import use_tenant
from app.tenancy.registry import active_tenants

logger = logging.getLogger("ai_pos.jobs")
_scheduler: BackgroundScheduler | None = None


def _runner(name: str, settings: Settings):
    def run() -> None:
        if not settings.tenancy_enabled:
            with get_session_factory()() as db:
                run_job(db, settings, name)
            return
        # Every tenant database keeps its own job leases and results.
        for tenant in active_tenants(settings):
            try:
                with use_tenant(tenant), get_session_factory()() as db:
                    run_job(db, settings, name)
            except Exception:  # noqa: BLE001 - one tenant's failure must not stop the others
                logger.exception("job %s failed for tenant %s", name, tenant.slug)

    return run


def _grace_seconds(trigger: dict[str, object]) -> int:
    """A tick that starts late still runs. The default one-second grace was skipping the reply check."""
    if trigger.get("trigger") != "interval":
        return 3600
    seconds = int(trigger.get("seconds") or 0)
    minutes = int(trigger.get("minutes") or 0)
    hours = int(trigger.get("hours") or 0)
    return max(seconds + minutes * 60 + hours * 3600, 30)


def start(settings: Settings) -> None:
    global _scheduler
    if _scheduler is not None or not settings.scheduler_enabled:
        return
    scheduler = BackgroundScheduler(timezone="UTC", job_defaults={"coalesce": True, "max_instances": 1})
    for job in JOBS.values():
        trigger = dict(job.trigger)
        kind = trigger.pop("trigger")
        scheduler.add_job(
            _runner(job.name, settings),
            kind,
            id=job.name,
            misfire_grace_time=_grace_seconds(job.trigger),
            **trigger,
        )
    scheduler.start()
    _scheduler = scheduler
    logger.info("scheduler started with %d jobs", len(JOBS))


def running() -> bool:
    return _scheduler is not None and _scheduler.running


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
