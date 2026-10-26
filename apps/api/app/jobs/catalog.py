"""The job list. Feature modules add their jobs here so the scheduler and the Jobs page see the same set."""

from sqlalchemy.orm import Session

from app.core.capabilities import Capability, has_capability
from app.core.config import Settings
from app.jobs.runner import Job, register
from app.services import (
    credit_risk_service,
    credit_service,
    dunning_service,
    expiry_service,
    fx_service,
    gl_service,
    insights_service,
    integrated_payment_service,
    kitchen_agent_service,
    loyalty_service,
    markdown_service,
    messaging_service,
    price_list_service,
    quote_service,
    replenishment_service,
    sales_order_service,
    warranty_service,
)


def _expire_quotes(db: Session, settings: Settings) -> str:
    return f"{quote_service.expire_quotes(db)} quotes expired"


def _credit_holds(db: Session, settings: Settings) -> str:
    return f"{credit_service.refresh_all(db, settings)} accounts changed hold"


def _credit_risk(db: Session, settings: Settings) -> str:
    return f"{credit_risk_service.refresh_all(db)} accounts scored"


def _dispatch(db: Session, settings: Settings) -> str:
    counts = messaging_service.dispatch_due(db, settings)
    return ", ".join(f"{value} {key}" for key, value in counts.items())


def _warranty_reminders(db: Session, settings: Settings) -> str:
    return f"{warranty_service.send_reminders(db, settings)} reminders queued"


def _layaway(db: Session, settings: Settings) -> str:
    return f"{dunning_service.send_layaway_reminders(db, settings)} reminders queued"


def _fx(db: Session, settings: Settings) -> str:
    return f"{fx_service.sync_rates(db, settings)} rates updated ({settings.fx_provider})"


def _overdue(db: Session, settings: Settings) -> str:
    return f"{dunning_service.send_overdue_reminders(db, settings)} reminders queued"


def _loyalty_expiry(db: Session, settings: Settings) -> str:
    return f"points lapsed for {loyalty_service.expire_points(db)} customers"


def _gl_posting(db: Session, settings: Settings) -> str:
    return gl_service.job(db)


def _batch_expiry(db: Session, settings: Settings) -> str:
    return expiry_service.run_alert(db)


def _kitchen_brief(db: Session, settings: Settings) -> str:
    if not has_capability(db, Capability.RECIPES):
        return "recipes module is off"
    found = kitchen_agent_service.brief(db, None)
    urgent = sum(1 for card in found.cards if card.severity == "high")
    return f"{len(found.cards)} kitchen cards, {urgent} urgent"


def _anomaly_scan(db: Session, settings: Settings) -> str:
    return insights_service.run_scan(db)


def _demand(db: Session, settings: Settings) -> str:
    return f"{replenishment_service.snapshot_demand(db)} product-days refreshed"


def _allocate_backorders(db: Session, settings: Settings) -> str:
    return sales_order_service.allocate_all(db)


def _price_changes(db: Session, settings: Settings) -> str:
    return price_list_service.apply_due(db)


def _markdowns(db: Session, settings: Settings) -> str:
    return markdown_service.apply_due(db)


def _payment_refunds(db: Session, settings: Settings) -> str:
    return integrated_payment_service.process_refunds(db, settings)


register(
    Job("dispatch_messages", "Send queued customer messages", _dispatch, {"trigger": "interval", "minutes": 1}, 120)
)
register(
    Job(
        "payment_refunds",
        "Send card and pay-later refunds to the provider, retrying failures",
        _payment_refunds,
        {"trigger": "interval", "minutes": 1},
        120,
    )
)
register(
    Job(
        "expire_quotes",
        "Release stock held by expired quotes and layaways",
        _expire_quotes,
        {"trigger": "interval", "minutes": 30},
    )
)
register(
    Job(
        "credit_holds",
        "Put long-overdue accounts on credit hold, lift paid ones",
        _credit_holds,
        {"trigger": "cron", "hour": 2, "minute": 0},
    )
)
register(
    Job(
        "credit_risk",
        "Score wholesale accounts for credit risk",
        _credit_risk,
        {"trigger": "cron", "hour": 2, "minute": 15},
    )
)
register(
    Job(
        "warranty_reminders",
        "Remind customers 30 days before their warranty ends",
        _warranty_reminders,
        {"trigger": "cron", "hour": 9, "minute": 0},
    )
)
register(
    Job(
        "layaway_reminders",
        "Weekly reminder of the balance left on open layaways",
        _layaway,
        {"trigger": "cron", "hour": 11, "minute": 0},
    )
)
register(
    Job(
        "fx_rates",
        "Refresh exchange rates for accepted foreign currencies",
        _fx,
        {"trigger": "cron", "hour": 6, "minute": 0},
    )
)
register(
    Job(
        "overdue_reminders",
        "Weekly reminder to accounts with overdue invoices",
        _overdue,
        {"trigger": "cron", "hour": 10, "minute": 0},
    )
)
register(
    Job(
        "loyalty_expiry",
        "Lapse loyalty points older than the programme's expiry",
        _loyalty_expiry,
        {"trigger": "cron", "hour": 3, "minute": 0},
    )
)
register(
    Job(
        "demand_snapshot",
        "Refresh daily demand history used by replenishment forecasts",
        _demand,
        {"trigger": "cron", "hour": 1, "minute": 30},
    )
)
register(
    Job(
        "anomaly_scan",
        "Flag unusual voids, refunds, no-sale opens, price overrides and cash variances",
        _anomaly_scan,
        {"trigger": "cron", "hour": 5, "minute": 30},
    )
)
register(
    Job(
        "batch_expiry",
        "Summarise expired and soon-to-expire batches (expiry-first stock)",
        _batch_expiry,
        {"trigger": "cron", "hour": 6, "minute": 0},
    )
)
register(
    Job(
        "kitchen_agent",
        "Check ingredient stock, recipes, and batch expiry for restaurant and cafe",
        _kitchen_brief,
        {"trigger": "cron", "hour": 6, "minute": 15},
    )
)
register(
    Job(
        "gl_posting",
        "Post the last 45 days of documents to the general ledger",
        _gl_posting,
        {"trigger": "interval", "minutes": 15},
    )
)
register(
    Job(
        "sales_order_allocation",
        "Reserve newly available stock for backordered sales order lines, oldest order first",
        _allocate_backorders,
        {"trigger": "cron", "hour": 4, "minute": 30},
    )
)
register(
    Job(
        "price_changes",
        "Apply scheduled retail and tier price changes that are due",
        _price_changes,
        {"trigger": "interval", "minutes": 5},
    )
)
register(
    Job(
        "apply_markdowns",
        "Start markdowns that are due and restore prices when they end",
        _markdowns,
        {"trigger": "interval", "minutes": 5},
    )
)


def _reorder_reminders(db: Session, settings: Settings) -> str:
    del settings
    from app.core.capabilities import Capability, has_capability
    from app.services import reorder_service

    if not has_capability(db, Capability.CUSTOMER_REORDERS):
        return "customer reorders are off"
    return reorder_service.generate_due(db)


register(
    Job(
        "customer_reorders",
        "Open reminders for customer reorder plans that are due",
        _reorder_reminders,
        {"trigger": "interval", "minutes": 15},
    )
)


def _issue_coupons(db: Session, settings: Settings) -> str:
    del settings
    from app.core.capabilities import Capability, has_capability
    from app.services import coupon_service

    if not has_capability(db, Capability.PROMOTIONS):
        return "promotions are off"
    return f"{coupon_service.issue_due(db)} vouchers issued"


register(
    Job(
        "customer_coupons",
        "Issue customer vouchers from buying history",
        _issue_coupons,
        {"trigger": "interval", "hours": 1},
    )
)


def _drain_cache(db: Session, settings: Settings) -> str:
    del settings
    from sqlalchemy import select

    from app.core.cache import delete
    from app.models.cache import CacheInvalidation

    rows = db.scalars(select(CacheInvalidation)).all()
    for row in rows:
        delete(row.cache_key)
        db.delete(row)
    return f"{len(rows)} cache keys dropped"


register(
    Job(
        "cache_invalidation",
        "Drop cache keys recorded in the same transaction as the change",
        _drain_cache,
        {"trigger": "interval", "minutes": 1},
    )
)
