"""The real fair dispatcher, with two stores in one shared database."""

import os
from datetime import UTC, datetime, timedelta

import pytest
from reach.models import ReachCampaign, ReachCampaignRun, ReachRecipient
from reach.prepare import prepare_due
from reach.runs import cancel_run
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import build_engine
from app.models import Base
from app.models.customer import Customer
from app.models.messaging import OutboundMessage
from app.services.messaging_service import dispatch_across_tenants, priority_for
from app.services.settings_service import clear_settings_cache, load_settings
from app.tenancy import registry
from app.tenancy.context import TenantRef, use_tenant
from app.tenancy.models import ControlBase, Tenant


def _open(db) -> None:
    row = load_settings(db)
    row.managed_capabilities = {"axiz_reach": "on"}
    db.commit()
    clear_settings_cache()


def _customer(name: str) -> Customer:
    return Customer(
        code=name[:32],
        name=name,
        email=f"{name}@example.test",
        marketing_email_opt_in=True,
        customer_type="RETAIL",
    )


@pytest.fixture()
def stores(tmp_path):
    previous_database = os.environ.get("DATABASE_URL")
    previous_control = os.environ.get("CONTROL_DATABASE_URL")
    shared_url = f"sqlite:///{(tmp_path / 'shared.db').as_posix()}"
    control_url = f"sqlite:///{(tmp_path / 'control.db').as_posix()}"
    os.environ["DATABASE_URL"] = shared_url
    os.environ["CONTROL_DATABASE_URL"] = control_url
    get_settings.cache_clear()
    registry.invalidate()
    registry._control_factory.cache_clear()
    settings = get_settings()
    settings.reach_send_interval_seconds = 0
    settings.reach_send_batch = 2
    settings.reach_transactional_reserve = 1
    ControlBase.metadata.create_all(build_engine(control_url))
    engine = build_engine(shared_url)
    Base.metadata.create_all(engine)
    control = registry.control_session(settings)
    refs = {}
    for slug in ("alpha", "bravo"):
        tenant = Tenant(
            slug=slug,
            name=slug,
            status="active",
            data_plane="shared",
            database_url_encrypted=registry.encrypt_database_url(shared_url, settings),
        )
        control.add(tenant)
        control.flush()
        refs[slug] = TenantRef(
            id=str(tenant.id), slug=slug, name=slug, database_url=shared_url, data_plane="shared"
        )
        with use_tenant(refs[slug]), sessionmaker(bind=engine, expire_on_commit=False)() as db:
            _open(db)
    control.commit()
    control.close()
    yield refs
    if previous_database is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous_database
    if previous_control is None:
        os.environ.pop("CONTROL_DATABASE_URL", None)
    else:
        os.environ["CONTROL_DATABASE_URL"] = previous_control
    get_settings.cache_clear()
    registry.invalidate()
    registry._control_factory.cache_clear()


def _session(ref):
    return registry.session_factory_for(ref)()


def test_a_receipt_in_one_store_is_sent_before_another_stores_campaign(stores) -> None:
    settings = get_settings()
    older = datetime.now(UTC) - timedelta(hours=2)
    with use_tenant(stores["alpha"]), _session(stores["alpha"]) as db:
        person = _customer("alpha-buyer")
        db.add(person)
        db.flush()
        db.add(
            OutboundMessage(
                channel="email",
                to_address=person.email or "",
                customer_id=person.id,
                template_key="campaign",
                priority=priority_for("campaign"),
                body="Promo",
                status="QUEUED",
                created_at=older,
                next_attempt_at=older,
            )
        )
        db.commit()
    with use_tenant(stores["bravo"]), _session(stores["bravo"]) as db:
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

    settings.reach_send_batch = 1
    dispatch_across_tenants(settings)

    with use_tenant(stores["bravo"]), _session(stores["bravo"]) as db:
        receipt = db.scalar(select(OutboundMessage).where(OutboundMessage.template_key == "receipt"))
        assert receipt is not None
        assert receipt.status == "SENT"
    with use_tenant(stores["alpha"]), _session(stores["alpha"]) as db:
        promo = db.scalar(select(OutboundMessage).where(OutboundMessage.template_key == "campaign"))
        assert promo is not None
        assert promo.status == "QUEUED"
        assert promo.priority == 3


def test_cancelling_one_store_does_not_touch_the_other(stores) -> None:
    older = datetime.now(UTC) - timedelta(minutes=5)
    with use_tenant(stores["alpha"]), _session(stores["alpha"]) as db:
        campaign = ReachCampaign(name="Alpha", idempotency_key="alpha-key", channels=["email"], status="dispatching")
        db.add(campaign)
        db.flush()
        run = ReachCampaignRun(
            campaign_id=campaign.id,
            run_number=1,
            status="dispatching",
            channel="email",
            audience_type="selected",
            audience_snapshot={},
        )
        db.add(run)
        db.flush()
        message = OutboundMessage(
            channel="email",
            to_address="a@example.test",
            template_key="campaign",
            priority=3,
            body="Alpha",
            status="QUEUED",
            context={"campaign_run_id": str(run.id)},
            created_at=older,
            next_attempt_at=older,
        )
        db.add(message)
        db.flush()
        db.add(
            ReachRecipient(
                campaign_id=campaign.id,
                campaign_run_id=run.id,
                outbound_message_id=message.id,
                phone="a@example.test",
                status="queued",
            )
        )
        db.commit()
        run_id = run.id
    with use_tenant(stores["bravo"]), _session(stores["bravo"]) as db:
        db.add(
            OutboundMessage(
                channel="email",
                to_address="b@example.test",
                template_key="campaign",
                priority=3,
                body="Bravo",
                status="QUEUED",
            )
        )
        db.commit()

    with use_tenant(stores["alpha"]), _session(stores["alpha"]) as db:
        cancel_run(db, run_id)
        db.commit()

    with use_tenant(stores["bravo"]), _session(stores["bravo"]) as db:
        other = db.scalar(select(OutboundMessage).where(OutboundMessage.body == "Bravo"))
        assert other is not None
        assert other.status == "QUEUED"
    with use_tenant(stores["alpha"]), _session(stores["alpha"]) as db:
        own = db.scalar(select(OutboundMessage).where(OutboundMessage.body == "Alpha"))
        assert own is not None
        assert own.status == "SKIPPED"


def test_each_store_prepares_only_its_own_audience(stores) -> None:
    from types import SimpleNamespace

    batch = SimpleNamespace(reach_prepare_batch=1, reach_daily_recipient_limit=1000)
    for slug, count in (("alpha", 3), ("bravo", 1)):
        with use_tenant(stores[slug]), _session(stores[slug]) as db:
            people = []
            for index in range(count):
                person = _customer(f"{slug}-{index}")
                db.add(person)
                people.append(person)
            db.flush()
            campaign = ReachCampaign(
                name=slug,
                idempotency_key=f"{slug}-prep",
                channels=["email"],
                status="preparing",
                content={"email": {"body": "Hello", "subject": slug}},
            )
            db.add(campaign)
            db.flush()
            db.add(
                ReachCampaignRun(
                    campaign_id=campaign.id,
                    run_number=1,
                    status="preparing",
                    channel="email",
                    audience_type="selected",
                    audience_snapshot={"customer_ids": [str(person.id) for person in people]},
                    content_snapshot=campaign.content,
                )
            )
            db.commit()

    with use_tenant(stores["alpha"]), _session(stores["alpha"]) as db:
        prepare_due(db, batch)
        alpha_rows = list(db.scalars(select(ReachRecipient)))
    with use_tenant(stores["bravo"]), _session(stores["bravo"]) as db:
        bravo_before = list(db.scalars(select(ReachRecipient)))
        prepare_due(db, batch)
        bravo_rows = list(db.scalars(select(ReachRecipient)))

    assert len(alpha_rows) == 3
    assert bravo_before == []
    assert len(bravo_rows) == 1
    assert {row.customer_id for row in alpha_rows}.isdisjoint({row.customer_id for row in bravo_rows})
