"""A 14-day Pro AI promotion layered on a Free or Growth subscription.

The subscription row, its Standard practice trial, and issued invoices are not changed.
Access stops at expires_at even when the expiry job has not run yet.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core import capabilities as catalog
from app.core.config import Settings
from app.core.errors import ApiError
from app.schemas.billing import PromotionalTrialOut, TrialConfigOut
from app.tenancy.models import BillingPlan, BillingPolicy, PromotionalTrial, Subscription, Tenant

log = logging.getLogger("ai_pos.billing")

TRIAL_TYPE = "PRO_AI_PROMOTIONAL"
TRIAL_DAYS = 14
ELIGIBLE_PLANS = frozenset({"FREE", "GROWTH"})
PLAN_CODE = "PRO_AI"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _policy(db: Session) -> BillingPolicy:
    row = db.get(BillingPolicy, 1)
    if row is None:
        row = BillingPolicy(
            id=1,
            grace_days=5,
            pro_ai_trial_enabled=True,
            pro_ai_trial_days=TRIAL_DAYS,
            pro_ai_trial_plans=["FREE", "GROWTH"],
            new_annual_discount_bps=2000,
            commercial_revision=1,
            updated_at=datetime.now(UTC),
        )
        db.add(row)
        db.flush()
    return row


def trial_enabled(db: Session) -> bool:
    return bool(_policy(db).pro_ai_trial_enabled)


def trial_days(db: Session) -> int:
    """Length used for a trial that starts now. Existing rows keep the expiry they were given."""
    days = int(_policy(db).pro_ai_trial_days or TRIAL_DAYS)
    return days if days > 0 else TRIAL_DAYS


def eligible_plan_codes(db: Session) -> frozenset[str]:
    raw = _policy(db).pro_ai_trial_plans or ["FREE", "GROWTH"]
    return frozenset(str(code) for code in raw)


def bump_revision(db: Session) -> int:
    row = _policy(db)
    row.commercial_revision = int(row.commercial_revision or 0) + 1
    row.updated_at = datetime.now(UTC)
    db.flush()
    return int(row.commercial_revision)


def set_trial_enabled(db: Session, enabled: bool) -> bool:
    row = _policy(db)
    row.pro_ai_trial_enabled = enabled
    row.updated_at = datetime.now(UTC)
    db.flush()
    return enabled


def _subscription(db: Session, tenant_id: uuid.UUID) -> tuple[Subscription | None, BillingPlan | None]:
    row = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
    if row is None:
        return None, None
    return row, db.get(BillingPlan, row.plan_id)


def _row(db: Session, tenant_id: uuid.UUID) -> PromotionalTrial | None:
    return db.scalar(
        select(PromotionalTrial).where(
            PromotionalTrial.tenant_id == tenant_id,
            PromotionalTrial.trial_type == TRIAL_TYPE,
        )
    )


def effective_status(row: PromotionalTrial | None, now: datetime | None = None) -> str:
    """Active only inside the stored window. A late worker does not keep Pro AI open."""
    if row is None:
        return "not_started"
    if row.status != "active":
        return row.status
    moment = now or datetime.now(UTC)
    if _aware(row.expires_at) <= moment:
        return "expired"
    return "active"


def _block_reason(db: Session, tenant: Tenant, now: datetime) -> str | None:
    if not trial_enabled(db):
        return "The Pro AI trial is switched off."
    if tenant.status != "active":
        return "This store cannot start a trial."
    subscription, plan = _subscription(db, tenant.id)
    if subscription is None or plan is None or subscription.status != "active":
        return "A Free or Growth subscription is required."
    if plan.code not in eligible_plan_codes(db):
        return "This plan is not eligible for the Pro AI trial."
    existing = _row(db, tenant.id)
    status = effective_status(existing, now)
    if status == "active":
        return None
    if existing is not None:
        return "This store has already used its Pro AI trial."
    return None


def _labels(keys: list[str]) -> list[str]:
    return [catalog.SPECS[capability].label for capability in catalog.parse(keys)]


def _module_keys(db: Session, profile: str) -> list[str]:
    plan = db.scalar(select(BillingPlan).where(BillingPlan.code == PLAN_CODE, BillingPlan.active.is_(True)))
    if plan is None:
        return []
    allowed = {capability.value for capability in catalog.compatible(profile)}
    parsed = catalog.parse(plan.included_modules or [])
    return [capability.value for capability in parsed if capability.value in allowed]


def present(db: Session, tenant: Tenant, profile: str = "", now: datetime | None = None) -> PromotionalTrialOut:
    moment = now or datetime.now(UTC)
    _subscription_row, plan = _subscription(db, tenant.id)
    row = _row(db, tenant.id)
    status = effective_status(row, moment)
    reason = _block_reason(db, tenant, moment)
    eligible = reason is None and status == "not_started"
    remaining = None
    if status == "active" and row is not None:
        remaining = max(0, (_aware(row.expires_at) - moment).days)
    keys = _module_keys(db, profile) if status == "active" else []
    return PromotionalTrialOut(
        eligible=eligible,
        reason=None if eligible or status == "active" else reason,
        status=status,  # type: ignore[arg-type]
        base_plan_code=plan.code if plan is not None else None,
        base_plan_name=plan.name if plan is not None else None,
        promotional_plan_code=PLAN_CODE,
        trial_days=trial_days(db),
        starts_at=_aware(row.starts_at) if row is not None else None,
        expires_at=_aware(row.expires_at) if row is not None else None,
        days_remaining=remaining,
        capabilities=_labels(keys),
        capability_keys=keys,
        enabled=trial_enabled(db),
        reminder=_reminder(row, status, remaining, plan.code if plan is not None else "your plan"),
    )


def _reminder(row: PromotionalTrial | None, status: str, remaining: int | None, base: str) -> str | None:
    if status == "active" and remaining is not None:
        if remaining <= 2:
            return f"Your Pro AI trial ends in {remaining} days."
        return f"Your Pro AI trial is active — {remaining} days remaining."
    if status == "expired":
        return f"Your Pro AI trial has ended. Your account is now on {base}."
    if row is not None and status == "cancelled":
        return f"Your Pro AI trial has ended. Your account is now on {base}."
    return None


def start(db: Session, tenant: Tenant, actor_id: uuid.UUID | None, now: datetime | None = None) -> PromotionalTrial:
    """Opens the one lifetime trial. A second call returns the same row and does not move the expiry."""
    moment = now or datetime.now(UTC)
    existing = _row(db, tenant.id)
    if existing is not None and effective_status(existing, moment) == "active":
        return existing
    reason = _block_reason(db, tenant, moment)
    if reason is not None:
        code = "trial_disabled" if not trial_enabled(db) else "trial_ineligible"
        if existing is not None:
            code = "trial_consumed"
        raise ApiError(409, code, reason)
    _subscription_row, plan = _subscription(db, tenant.id)
    assert plan is not None
    row = PromotionalTrial(
        tenant_id=tenant.id,
        trial_type=TRIAL_TYPE,
        status="active",
        base_plan_code=plan.code,
        promotional_plan_code=PLAN_CODE,
        starts_at=moment,
        expires_at=moment + timedelta(days=trial_days(db)),
        consumed_at=moment,
        granted_by=actor_id,
        notices_sent=["started"],
        created_at=moment,
        updated_at=moment,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        found = _row(db, tenant.id)
        if found is not None and effective_status(found, moment) == "active":
            return found
        raise ApiError(409, "trial_consumed", "This store has already used its Pro AI trial.") from None
    return row


def effective_limits(db: Session, tenant_id: uuid.UUID, now: datetime | None = None) -> dict | None:
    """Base-plan caps, widened to Pro AI while the promotion is inside its window."""
    subscription, plan = _subscription(db, tenant_id)
    if subscription is None or plan is None or subscription.status == "canceled":
        return None
    base = dict(plan.resource_limits) if plan.resource_limits else None
    row = _row(db, tenant_id)
    if effective_status(row, now) != "active":
        return base
    promo_plan = db.scalar(select(BillingPlan).where(BillingPlan.code == PLAN_CODE))
    promo = dict(promo_plan.resource_limits) if promo_plan is not None and promo_plan.resource_limits else None
    if promo is None:
        return base
    if base is None:
        return promo
    merged: dict[str, int | None] = {}
    for key in set(base) | set(promo):
        left = base.get(key) if key in base else None
        right = promo.get(key) if key in promo else None
        if (key in base and left is None) or (key in promo and right is None):
            merged[key] = None
        elif left is None:
            merged[key] = int(right) if right is not None else None
        elif right is None:
            merged[key] = int(left)
        else:
            merged[key] = max(int(left), int(right))
    return merged


def _notice(row: PromotionalTrial, kind: str) -> bool:
    sent = [str(item) for item in (row.notices_sent or [])]
    if kind in sent:
        return False
    sent.append(kind)
    row.notices_sent = sent
    flag_modified(row, "notices_sent")
    return True


def publish_window(settings: Settings, tenant: Tenant, keys: list[str], until: datetime | None) -> None:
    """Copies the Pro AI module list onto the store. Paid add-ons on the same row are left alone."""
    from app.console.entitlements import tenant_session
    from app.services import audit
    from app.services.settings_service import load_settings

    with tenant_session(tenant, settings) as store:
        row = load_settings(store, lock=True)
        before = list(row.promotional_capabilities or [])
        row.promotional_capabilities = keys or None
        row.promotional_until = until
        if before != keys:
            audit.record(
                store,
                action_type="UPDATE",
                action="billing.pro_ai_trial",
                target_entity="Settings",
                target_entity_id=row.id,
                client_device="billing",
                old_values={"promotional_capabilities": before},
                new_values={
                    "promotional_capabilities": keys,
                    "promotional_until": until.isoformat() if until else None,
                },
                reason_notes="Pro AI promotional trial",
            )
        store.commit()
        from app.services.addon_access import invalidate_access_cache

        invalidate_access_cache(tenant.id)


def _maybe_email(settings: Settings, tenant: Tenant, kind: str, expires_at: datetime) -> None:
    """Sends only when the console mailbox is already on. A missing mailbox is not an error."""
    if not tenant.owner_email:
        return
    from app.console.mail import platform_link, send
    from app.services.messaging_providers import Outgoing, ProviderError

    if platform_link(settings) is None:
        return
    subject = {
        "started": "Your Pro AI trial has started",
        "d7": "7 days left on your Pro AI trial",
        "d3": "3 days left on your Pro AI trial",
        "d1": "1 day left on your Pro AI trial",
        "expired": "Your Pro AI trial has ended",
    }.get(kind, "Pro AI trial")
    body = (
        f"{tenant.name} stays on {tenant.plan}. "
        f"The Pro AI promotion runs until {expires_at.date().isoformat()} UTC. "
        "There is no charge. Business data is not removed."
    )
    try:
        send(settings, Outgoing(to=tenant.owner_email, subject=subject, body=body))
    except ProviderError:
        log.info("pro ai trial notice %s was not emailed for %s", kind, tenant.slug)


def expire_due(settings: Settings, now: datetime | None = None) -> str:
    """Marks elapsed trials and records each reminder once. The base subscription is not written."""
    from app.tenancy import registry

    moment = now or datetime.now(UTC)
    expired = 0
    reminded = 0
    mail: list[tuple[uuid.UUID, str, datetime]] = []
    with registry.control_session(settings) as db:
        statement = select(PromotionalTrial).where(PromotionalTrial.status == "active")
        bind = db.get_bind()
        if bind is not None and bind.dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        rows = list(db.scalars(statement))
        for row in rows:
            if row.status != "active":
                continue
            tenant = db.get(Tenant, row.tenant_id)
            if _aware(row.expires_at) <= moment:
                row.status = "expired"
                row.expiration_reason = "elapsed"
                row.updated_at = moment
                if _notice(row, "expired"):
                    expired += 1
                    if tenant is not None:
                        publish_window(settings, tenant, [], row.expires_at)
                        mail.append((tenant.id, "expired", row.expires_at))
                continue
            days = (_aware(row.expires_at) - moment).days
            kind = "d1" if days <= 1 else "d3" if days <= 3 else "d7" if days <= 7 else None
            if kind is None or tenant is None or not _notice(row, kind):
                continue
            reminded += 1
            row.updated_at = moment
            mail.append((tenant.id, kind, row.expires_at))
        db.commit()
        for tenant_id, kind, stamp in mail:
            tenant = db.get(Tenant, tenant_id)
            if tenant is not None:
                _maybe_email(settings, tenant, kind, stamp)
    return f"{expired} promotional trials expired, {reminded} reminders recorded"


def trial_config(db: Session) -> TrialConfigOut:
    row = _policy(db)
    trials = list(db.scalars(select(PromotionalTrial).where(PromotionalTrial.trial_type == TRIAL_TYPE)))
    return TrialConfigOut(
        enabled=bool(row.pro_ai_trial_enabled),
        days=trial_days(db),
        eligible_plans=sorted(eligible_plan_codes(db)),
        promotional_plan=PLAN_CODE,
        active_trials=sum(1 for trial in trials if effective_status(trial) == "active"),
        consumed_trials=len(trials),
        commercial_revision=int(row.commercial_revision or 1),
    )


def configure_trial(db: Session, *, enabled: bool, days: int | None, plans: list[str] | None) -> TrialConfigOut:
    """Changes future enrollment only. Stored trials keep their expiry and are not restarted."""
    row = _policy(db)
    if days is not None:
        row.pro_ai_trial_days = days
    if plans is not None:
        cleaned: list[str] = []
        for code in plans:
            token = str(code).strip().upper()
            if token and token not in cleaned:
                cleaned.append(token)
        if not cleaned:
            raise ApiError(422, "invalid_trial", "Choose at least one eligible plan.")
        known = set(db.scalars(select(BillingPlan.code)))
        missing = [code for code in cleaned if code not in known]
        if missing:
            raise ApiError(422, "invalid_trial", f"Unknown plan: {', '.join(missing)}.")
        row.pro_ai_trial_plans = cleaned
        flag_modified(row, "pro_ai_trial_plans")
    row.pro_ai_trial_enabled = enabled
    bump_revision(db)
    db.flush()
    return trial_config(db)


def republish_active(settings: Settings, db: Session) -> None:
    """Refreshes Pro AI modules on open trials. The stored expiry is not moved."""
    from app.console.billing import _business_profile

    rows = list(
        db.scalars(
            select(PromotionalTrial).where(
                PromotionalTrial.trial_type == TRIAL_TYPE,
                PromotionalTrial.status == "active",
            )
        )
    )
    for row in rows:
        if effective_status(row) != "active":
            continue
        tenant = db.get(Tenant, row.tenant_id)
        if tenant is None:
            continue
        keys = _module_keys(db, _business_profile(settings, tenant))
        publish_window(settings, tenant, keys, row.expires_at)
