"""Measured audience preparation. Contacts are synthetic and nothing is sent to a provider."""

import time
import uuid

from sqlalchemy import func, select

from app.core.config import get_settings
from app.models.customer import Customer
from reach.models import ReachCampaign, ReachCampaignRun, ReachRecipient
from reach.prepare import prepare_due

SIZES = (1000, 5000, 10000, 25000)


def _load(session, count: int, token: str, points: int) -> None:
    rows = []
    for index in range(count):
        missing = index % 10 == 0
        refused = index % 10 == 1
        rows.append(
            Customer(
                code=f"{token}-{index}",
                name=f"Synthetic {token} {index}",
                email=None if missing else f"s{token}{index}@example.test",
                marketing_email_opt_in=not missing and not refused,
                loyalty_points=points,
                customer_type="RETAIL",
            )
        )
        if len(rows) == 500:
            session.add_all(rows)
            session.flush()
            rows = []
    if rows:
        session.add_all(rows)
        session.flush()


def test_audience_preparation_scales_in_batches(session) -> None:
    settings = get_settings()
    settings.reach_prepare_batch = 200
    measurements = []
    for count in SIZES:
        token = uuid.uuid4().hex[:8]
        started = time.perf_counter()
        points = 1000 + count
        _load(session, count, token, points)
        load_seconds = time.perf_counter() - started
        campaign = ReachCampaign(
            name=f"Scale {count}",
            idempotency_key=token,
            channels=["email"],
            status="preparing",
            content={"email": {"body": "Hello", "subject": "Scale"}},
            audience={"min_loyalty_points": points},
        )
        session.add(campaign)
        session.flush()
        run = ReachCampaignRun(
            campaign_id=campaign.id,
            run_number=1,
            status="preparing",
            channel="email",
            audience_type="loyalty",
            audience_snapshot={"min_loyalty_points": points},
            content_snapshot=campaign.content,
        )
        session.add(run)
        session.commit()
        ticks = 0
        page_times = []
        prepare_started = time.perf_counter()
        while run.status == "preparing" and ticks < 500:
            tick = time.perf_counter()
            prepare_due(session, settings)
            page_times.append(time.perf_counter() - tick)
            session.refresh(run)
            ticks += 1
        prepare_seconds = time.perf_counter() - prepare_started
        queued = int(
            session.scalar(
                select(func.count()).select_from(ReachRecipient).where(ReachRecipient.campaign_run_id == run.id, ReachRecipient.status == "queued")
            )
            or 0
        )
        skipped = int(
            session.scalar(
                select(func.count()).select_from(ReachRecipient).where(ReachRecipient.campaign_run_id == run.id, ReachRecipient.status == "skipped")
            )
            or 0
        )
        people = int(
            session.scalar(
                select(func.count()).select_from(ReachRecipient).where(ReachRecipient.campaign_run_id == run.id)
            )
            or 0
        )
        distinct = int(
            session.scalar(
                select(func.count(func.distinct(ReachRecipient.customer_id))).where(ReachRecipient.campaign_run_id == run.id)
            )
            or 0
        )
        measurements.append(
            {
                "count": count,
                "load_seconds": round(load_seconds, 3),
                "prepare_seconds": round(prepare_seconds, 3),
                "ticks": ticks,
                "page_avg": round(sum(page_times) / len(page_times), 3) if page_times else 0,
                "page_max": round(max(page_times), 3) if page_times else 0,
                "queued": queued,
                "skipped": skipped,
                "rows": people,
                "distinct": distinct,
                "candidates": run.total_candidates,
            }
        )
        assert run.status == "dispatching"
        assert people == distinct
        assert people == count
        assert run.total_candidates == count
        # Every tenth row has no address, and the next tenth has no consent.
        assert skipped == (count // 10) * 2
        assert queued == count - skipped
    print("AUDIENCE_MEASUREMENTS", measurements)
