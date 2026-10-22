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


def start(settings: Settings) -> None:
    global _scheduler
    if _scheduler is not None or not settings.scheduler_enabled:
        return
    scheduler = BackgroundScheduler(timezone="UTC", job_defaults={"coalesce": True, "max_instances": 1})
    for job in JOBS.values():
        trigger = dict(job.trigger)
        kind = trigger.pop("trigger")
        scheduler.add_job(_runner(job.name, settings), kind, id=job.name, **trigger)
    scheduler.start()
    _scheduler = scheduler
    logger.info("scheduler started with %d jobs", len(JOBS))


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
