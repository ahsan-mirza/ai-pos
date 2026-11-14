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


# Billing, security, and cache work keep running while paid features are locked.
_OPEN_WHEN_LOCKED = frozenset({"cache_invalidation", "anomaly_scan", "expire_pro_ai_trials"})


def _paid_job_blocked(settings: Settings, name: str) -> bool:
    if name in _OPEN_WHEN_LOCKED or not settings.tenancy_enabled:
        return False
    from app.console.transfers import operations_open

    return not operations_open()


def _runner(name: str, settings: Settings):
    def run() -> None:
        if name == "dispatch_messages" and settings.tenancy_enabled:
            try:
                _dispatch_fair(settings, name)
            except Exception:  # noqa: BLE001 - the next tick retries; one failure must not stop the scheduler
                logger.exception("fair dispatch failed")
            return
        if not settings.tenancy_enabled:
            with get_session_factory()() as db:
                run_job(db, settings, name)
            return
        # Every tenant database keeps its own job leases and results.
        for tenant in active_tenants(settings):
            try:
                with use_tenant(tenant), get_session_factory()() as db:
                    if _paid_job_blocked(settings, name):
                        from app.jobs.runner import note_skip

                        note_skip(db, name, "subscription locked")
                        continue
                    run_job(db, settings, name)
            except Exception:  # noqa: BLE001 - one tenant's failure must not stop the others
                logger.exception("job %s failed for tenant %s", name, tenant.slug)

    return run


def _dispatch_fair(settings: Settings, name: str) -> None:
    """Pick one message at a time across tenants. A receipt is not left behind a campaign."""
    from app.services import messaging_service

    if _paid_job_blocked(settings, name):
        for tenant in active_tenants(settings):
            try:
                with use_tenant(tenant), get_session_factory()() as db:
                    from app.jobs.runner import note_skip

                    note_skip(db, name, "subscription locked")
            except Exception:  # noqa: BLE001 - one tenant's failure must not stop the others
                logger.exception("job %s failed for tenant %s", name, tenant.slug)
        return
    for tenant in active_tenants(settings):
        try:
            with use_tenant(tenant), get_session_factory()() as db:
                from reach.prepare import prepare_due

                prepare_due(db, settings)
        except Exception:  # noqa: BLE001 - one store's audience must not stop another store's receipts
            logger.exception("campaign audience preparation failed for tenant %s", tenant.slug)
    messaging_service.dispatch_across_tenants(settings)


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
