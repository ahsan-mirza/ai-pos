"""Disposable PostgreSQL checks for concurrent preparation, the advisory lock, and priority.

This never opens the development database ai_pos except to ask the server to create and drop
reach_stress_ops and reach_stress_control.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

NAMES = ("reach_stress_ops", "reach_stress_control")


def _server_url(original: str) -> str:
    return original.rsplit("/", 1)[0] + "/postgres"


def _url(original: str, name: str) -> str:
    return original.rsplit("/", 1)[0] + f"/{name}"


def _drop(server: str, name: str) -> None:
    engine = create_engine(server, isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        cursor = connection.connection.cursor()
        cursor.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
            (name,),
        )
        cursor.execute(f'DROP DATABASE IF EXISTS "{name}"')
    engine.dispose()


def _alembic(url: str) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["database_url"] = url
    return config


def _hold() -> None:
    from app.core.config import get_settings
    from app.services.messaging_service import _hold_dispatch_lock
    from app.tenancy.registry import active_tenants

    settings = get_settings()
    tenants = active_tenants(settings)
    if not tenants or not _hold_dispatch_lock(tenants[0]):
        print("HELD False", flush=True)
        return
    print("HELD True", flush=True)
    time.sleep(20)


def _switch(ops: str, control: str):
    from app.core.config import get_settings
    from app.tenancy import registry

    os.environ["DATABASE_URL"] = ops
    os.environ["CONTROL_DATABASE_URL"] = control
    get_settings.cache_clear()
    registry.invalidate()
    registry._control_factory.cache_clear()
    return get_settings()


def _seed_tenants(settings, ops: str):
    from app.core.database import build_engine
    from app.services.settings_service import clear_settings_cache, load_settings
    from app.tenancy import registry
    from app.tenancy.context import TenantRef, use_tenant
    from app.tenancy.models import ControlBase, Tenant

    ControlBase.metadata.create_all(build_engine(settings.control_database_url))
    control = registry.control_session(settings)
    refs = {}
    for slug in ("alpha", "bravo", "charlie", "delta", "echo"):
        tenant = Tenant(
            slug=slug,
            name=slug,
            status="active",
            data_plane="shared",
            database_url_encrypted=registry.encrypt_database_url(ops, settings),
        )
        control.add(tenant)
        control.flush()
        refs[slug] = TenantRef(id=str(tenant.id), slug=slug, name=slug, database_url=ops, data_plane="shared")
    control.commit()
    control.close()
    for ref in refs.values():
        with use_tenant(ref), registry.session_factory_for(ref)() as db:
            row = load_settings(db)
            row.managed_capabilities = {"axiz_reach": "on"}
            row.currency = row.currency or "USD"
            db.commit()
            clear_settings_cache()
    return refs


def _session(ref):
    from app.tenancy.registry import session_factory_for

    return session_factory_for(ref)()


def _customers(db, count: int, token: str, points: int, kind: str = "RETAIL") -> None:
    from app.models.customer import Customer

    rows = []
    for index in range(count):
        missing = index % 10 == 0
        refused = index % 10 == 1
        rows.append(
            Customer(
                code=f"{token}-{index}",
                name=f"Synthetic {index}",
                email=None if missing else f"s{token}{index}@example.test",
                marketing_email_opt_in=not missing and not refused,
                loyalty_points=points,
                customer_type=kind,
            )
        )
        if len(rows) == 500:
            db.add_all(rows)
            db.flush()
            rows = []
    if rows:
        db.add_all(rows)
        db.flush()


def _campaign(db, token: str, points: int, kind: str | None = None):
    from reach.models import ReachCampaign, ReachCampaignRun

    campaign = ReachCampaign(
        name=f"Stress {token}",
        idempotency_key=token,
        channels=["email"],
        status="preparing",
        content={"email": {"body": "Hello", "subject": "Stress"}},
    )
    db.add(campaign)
    db.flush()
    run = ReachCampaignRun(
        campaign_id=campaign.id,
        run_number=1,
        status="preparing",
        channel="email",
        audience_type="loyalty",
        audience_snapshot={"customer_type": kind} if kind else {"min_loyalty_points": points},
        content_snapshot=campaign.content,
    )
    db.add(run)
    db.commit()
    return run.id


def _prepare_until(ref, run_id, settings) -> dict:
    from app.tenancy.context import use_tenant
    from reach.models import ReachCampaignRun
    from reach.prepare import prepare_due

    ticks = []
    with use_tenant(ref), _session(ref) as db:
        run = db.get(ReachCampaignRun, run_id)
        started = time.perf_counter()
        while run.status == "preparing" and len(ticks) < 500:
            tick = time.perf_counter()
            prepare_due(db, settings)
            ticks.append(time.perf_counter() - tick)
            db.refresh(run)
        return {
            "status": run.status,
            "seconds": round(time.perf_counter() - started, 3),
            "ticks": len(ticks),
            "tick_avg": round(sum(ticks) / len(ticks), 3) if ticks else 0,
            "tick_max": round(max(ticks), 3) if ticks else 0,
            "candidates": run.total_candidates,
            "queued": run.queued_count,
            "excluded": run.excluded_recipients,
        }


def _count_dupes(ref, run_id) -> int:
    from app.tenancy.context import use_tenant
    from reach.models import ReachRecipient

    with use_tenant(ref), _session(ref) as db:
        total = int(
            db.scalar(
                select(func.count()).select_from(ReachRecipient).where(ReachRecipient.campaign_run_id == run_id)
            )
            or 0
        )
        distinct = int(
            db.scalar(
                select(func.count(func.distinct(ReachRecipient.customer_id))).where(
                    ReachRecipient.campaign_run_id == run_id
                )
            )
            or 0
        )
    return total - distinct


def main() -> None:
    if os.environ.get("REACH_STRESS_ROLE") == "hold":
        _hold()
        return
    from app.core.config import get_settings
    from app.core.database import create_database

    original = get_settings().database_url
    if not original.startswith("postgresql"):
        raise SystemExit("PostgreSQL is required.")
    server = _server_url(original)
    ops = _url(original, "reach_stress_ops")
    control = _url(original, "reach_stress_control")
    for name in NAMES:
        _drop(server, name)
        create_database(server, name)
    try:
        command.upgrade(_alembic(ops), "head")
        settings = _switch(ops, control)
        settings.reach_send_interval_seconds = 0
        settings.reach_prepare_batch = 200
        settings.reach_transactional_reserve = 1
        refs = _seed_tenants(settings, ops)
        _priority(settings, refs)
        _concurrent_prepare(settings, refs)
        _lock(settings)
        print("STRESS_OK")
    finally:
        for name in NAMES:
            _drop(server, name)
        print("DROPPED", ", ".join(NAMES))


def _priority(settings, refs) -> None:
    from datetime import UTC, datetime, timedelta

    from app.models.messaging import OutboundMessage
    from app.services.messaging_service import dispatch_across_tenants, priority_for
    from app.tenancy.context import use_tenant

    older = datetime.now(UTC) - timedelta(hours=1)
    with use_tenant(refs["alpha"]), _session(refs["alpha"]) as db:
        for index in range(30):
            db.add(
                OutboundMessage(
                    channel="email",
                    to_address=f"a{index}@example.test",
                    template_key="campaign",
                    priority=priority_for("campaign"),
                    body="Promo",
                    status="QUEUED",
                    created_at=older,
                    next_attempt_at=older,
                )
            )
        db.commit()
    with use_tenant(refs["bravo"]), _session(refs["bravo"]) as db:
        db.add(
            OutboundMessage(
                channel="email",
                to_address="receipt@example.test",
                template_key="receipt",
                priority=priority_for("receipt"),
                body="Receipt",
                status="QUEUED",
            )
        )
        db.commit()
    with use_tenant(refs["charlie"]), _session(refs["charlie"]) as db:
        db.add(
            OutboundMessage(
                channel="email",
                to_address="ops@example.test",
                template_key="overdue",
                priority=priority_for("overdue"),
                body="Reminder",
                status="QUEUED",
            )
        )
        db.commit()
    settings.reach_send_batch = 1
    started = time.perf_counter()
    dispatch_across_tenants(settings)
    first = round(time.perf_counter() - started, 3)
    dispatch_across_tenants(settings)
    settings.reach_transactional_reserve = 0
    dispatch_across_tenants(settings)
    with use_tenant(refs["bravo"]), _session(refs["bravo"]) as db:
        receipt = db.scalar(select(OutboundMessage).where(OutboundMessage.template_key == "receipt"))
    with use_tenant(refs["charlie"]), _session(refs["charlie"]) as db:
        reminder = db.scalar(select(OutboundMessage).where(OutboundMessage.template_key == "overdue"))
    with use_tenant(refs["alpha"]), _session(refs["alpha"]) as db:
        sent = int(
            db.scalar(
                select(func.count()).select_from(OutboundMessage).where(
                    OutboundMessage.template_key == "campaign", OutboundMessage.status == "SENT"
                )
            )
            or 0
        )
        queued = int(
            db.scalar(
                select(func.count()).select_from(OutboundMessage).where(
                    OutboundMessage.template_key == "campaign", OutboundMessage.status == "QUEUED"
                )
            )
            or 0
        )
    if receipt.status != "SENT" or reminder.status != "SENT" or sent != 1 or queued != 29:
        reason = None
        with use_tenant(refs["alpha"]), _session(refs["alpha"]) as db:
            reason = db.scalar(select(OutboundMessage.last_error).where(OutboundMessage.template_key == "campaign"))
        raise SystemExit(
            f"priority failed receipt={receipt.status} reminder={reminder.status} sent={sent} queued={queued} error={reason}"
        )
    print("PRIORITY", {"first_dispatch_seconds": first, "campaigns_sent": sent, "campaigns_still_queued": queued})


def _concurrent_prepare(settings, refs) -> None:
    from app.tenancy.context import use_tenant

    def worker(slug: str, count: int, points: int, box: dict) -> None:
        ref = refs[slug]
        with use_tenant(ref), _session(ref) as db:
            _customers(db, count, slug, points)
            box["run"] = str(_campaign(db, slug, points))

    boxes = {slug: {} for slug in ("alpha", "bravo", "charlie", "delta", "echo")}
    threads = [
        threading.Thread(target=worker, args=(slug, 20, 100 + index, boxes[slug]))
        for index, slug in enumerate(boxes)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    errors = []

    def prepare(slug: str) -> None:
        try:
            ref = refs[slug]
            result = _prepare_until(ref, uuid.UUID(boxes[slug]["run"]), settings)
            dupes = _count_dupes(ref, uuid.UUID(boxes[slug]["run"]))
            if result["candidates"] != 20 or dupes != 0:
                errors.append((slug, result, dupes))
        except Exception as exc:  # noqa: BLE001 - the summary reports the worker failure
            errors.append((slug, str(exc)))

    threads = [threading.Thread(target=prepare, args=(slug,)) for slug in boxes]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if errors:
        raise SystemExit(f"concurrent prepare failed {errors}")
    print("CONCURRENT_PREPARE", "five tenants, 20 contacts each, duplicates 0")
    _same_run(settings, refs["alpha"])


def _same_run(settings, ref) -> None:
    from app.tenancy.context import use_tenant

    with use_tenant(ref), _session(ref) as db:
        _customers(db, 40, "race", 77, "WHOLESALE")
        run_id = _campaign(db, "race", 77, "WHOLESALE")
    barrier = threading.Barrier(2)

    def run() -> None:
        barrier.wait()
        _prepare_until(ref, run_id, settings)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    dupes = _count_dupes(ref, run_id)
    with use_tenant(ref), _session(ref) as db:
        from reach.models import ReachCampaignRun

        row = db.get(ReachCampaignRun, run_id)
        candidates = row.total_candidates if row is not None else None
    if dupes != 0 or candidates != 40:
        raise SystemExit(f"same-run race failed candidates={candidates} dupes={dupes}")
    print("SAME_RUN", {"candidates": candidates, "duplicates": dupes})
    from app.models.messaging import OutboundMessage
    from app.services.messaging_service import dispatch_due
    from app.tenancy.context import use_tenant

    for count in (1000, 5000, 10000, 25000):
        points = 1000 + count
        token = uuid.uuid4().hex[:8]
        with use_tenant(ref), _session(ref) as db:
            started = time.perf_counter()
            _customers(db, count, token, points)
            load_seconds = round(time.perf_counter() - started, 3)
            run_id = _campaign(db, token, points)
        measured = _prepare_until(ref, run_id, settings)
        dupes = _count_dupes(ref, run_id)
        sample = 50 if count > 1000 else measured["queued"]
        settings.reach_send_batch = sample
        settings.reach_transactional_reserve = 0
        with use_tenant(ref), _session(ref) as db:
            started = time.perf_counter()
            dispatch_due(db, settings, limit=sample, allow_marketing=True)
            db.commit()
            sent = int(
                db.scalar(
                    select(func.count()).select_from(OutboundMessage).where(OutboundMessage.status == "SENT")
                )
                or 0
            )
        dispatch_seconds = round(time.perf_counter() - started, 3)
        if measured["candidates"] != count or dupes != 0:
            raise SystemExit(f"size {count} failed {measured} dupes={dupes}")
        print(
            "SIZE",
            {
                "count": count,
                "load_seconds": load_seconds,
                "prepare_seconds": measured["seconds"],
                "ticks": measured["ticks"],
                "tick_avg": measured["tick_avg"],
                "tick_max": measured["tick_max"],
                "queued": measured["queued"],
                "excluded": measured["excluded"],
                "dispatch_sample": sample,
                "dispatch_seconds": dispatch_seconds,
                "sent_visible_in_tenant": sent,
                "duplicates": dupes,
            },
        )


def _lock(settings) -> None:
    import subprocess

    env = os.environ.copy()
    env["REACH_STRESS_ROLE"] = "hold"
    child = subprocess.Popen(
        [sys.executable, "-m", "tests.postgres_reach_stress"],
        env=env,
        cwd=str(Path(__file__).resolve().parents[1]),
        stdout=subprocess.PIPE,
        text=True,
    )
    line = ""
    deadline = time.time() + 30
    while time.time() < deadline and child.stdout is not None:
        chunk = child.stdout.readline().strip()
        if chunk.startswith("HELD"):
            line = chunk
            break
    from app.services.messaging_service import _hold_dispatch_lock, _release_dispatch_lock
    from app.tenancy.registry import active_tenants

    blocked = _hold_dispatch_lock(active_tenants(settings)[0])
    if blocked:
        _release_dispatch_lock()
    child.kill()
    child.wait(timeout=10)
    time.sleep(0.5)
    acquired = _hold_dispatch_lock(active_tenants(settings)[0])
    if acquired:
        _release_dispatch_lock()
    if line != "HELD True" or blocked or not acquired:
        raise SystemExit(f"lock failed line={line} blocked_should_be_false={blocked} acquired_after_kill={acquired}")
    print("LOCK", {"holder": line, "second_process_blocked": not blocked, "acquired_after_kill": acquired})


if __name__ == "__main__":
    main()
