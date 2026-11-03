"""Suggestions from catalogue and promotion events. Nothing here sends a message."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, has_capability
from app.core.config import get_settings
from app.core.errors import ApiError
from app.models.product import Product
from app.models.promotion import Promotion
from app.models.store import Store
from reach.models import ReachCampaignSuggestion
from reach.service import launch


def on_product_created(db: Session, product: Product) -> None:
    if not has_capability(db, Capability.AXIZ_REACH):
        return
    _add(
        db,
        event_key=f"product:{product.id}",
        event_type="new_product",
        title=f"New arrival: {product.name}"[:120],
        reason="A product was added to the catalogue.",
        body=f"Good news. {product.name} is now in the catalogue. Ask us if you would like to know more.",
        audience={},
    )


def on_promotion_created(db: Session, promotion: Promotion) -> None:
    if not has_capability(db, Capability.AXIZ_REACH):
        return
    detail = promotion.description or "Ask us what is included."
    _add(
        db,
        event_key=f"promotion:{promotion.id}",
        event_type="promotion",
        title=f"Offer: {promotion.name}"[:120],
        reason="A promotion was created.",
        body=f"There is an offer called {promotion.name}. {detail}",
        audience={},
    )


def list_suggestions(db: Session) -> list[ReachCampaignSuggestion]:
    from reach.service import require_reach

    require_reach(db)
    _scan(db)
    return list(
        db.scalars(
            select(ReachCampaignSuggestion)
            .where(ReachCampaignSuggestion.status == "open")
            .order_by(ReachCampaignSuggestion.created_at.desc())
            .limit(50)
        )
    )


def dismiss(db: Session, suggestion_id: uuid.UUID) -> ReachCampaignSuggestion:
    row = _open(db, suggestion_id)
    row.status = "dismissed"
    db.commit()
    db.refresh(row)
    return row


def draft_from_suggestion(db: Session, actor_id: uuid.UUID | None, suggestion_id: uuid.UUID):
    row = _open(db, suggestion_id)
    campaign = launch(
        db,
        actor_id,
        {
            "idempotency_key": f"suggestion-{row.id}",
            "name": row.title,
            "description": row.reason,
            "objective": row.event_type,
            "channels": ["whatsapp"],
            "audience": row.audience or {},
            "content": {"whatsapp": {"body": row.body, "subject": row.title}},
            "mode": "draft",
            "origin": "ai",
        },
    )
    row.status = "drafted"
    row.campaign_id = campaign.id
    db.commit()
    return campaign


def _open(db: Session, suggestion_id: uuid.UUID) -> ReachCampaignSuggestion:
    from reach.service import require_reach

    require_reach(db)
    row = db.get(ReachCampaignSuggestion, suggestion_id)
    if row is None or row.status != "open":
        raise ApiError(404, "not_found", "Suggestion not found.")
    return row


def _add(db: Session, **fields: object) -> None:
    if db.scalar(select(ReachCampaignSuggestion.id).where(ReachCampaignSuggestion.event_key == fields["event_key"])):
        return
    db.add(ReachCampaignSuggestion(audience=fields.pop("audience") or {}, **fields))  # type: ignore[arg-type]
    try:
        db.commit()
    except IntegrityError:
        db.rollback()


def _scan(db: Session) -> None:
    since = datetime.now(UTC) - timedelta(days=7)
    for product in db.scalars(select(Product).where(Product.created_at >= since).limit(20)):
        on_product_created(db, product)
    for promotion in db.scalars(select(Promotion).where(Promotion.is_active.is_(True)).limit(20)):
        on_promotion_created(db, promotion)
    for store in db.scalars(select(Store).where(Store.created_at >= since, Store.is_active.is_(True)).limit(10)):
        _add(
            db,
            event_key=f"store:{store.id}",
            event_type="new_branch",
            title=f"New branch: {store.name}"[:120],
            reason="A branch was opened.",
            body=f"We have a location called {store.name}. Ask us for the address.",
            audience={},
        )
    day = datetime.now(UTC).date().isoformat()
    settings = get_settings()
    _add(
        db,
        event_key=f"inactive:{day}",
        event_type="reengagement",
        title="Customers who have been quiet",
        reason=f"Customers with no recent purchase in {settings.reach_inactive_days} days.",
        body="It's been a while since your last visit. We would like to welcome you back.",
        audience={"inactive_days": settings.reach_inactive_days},
    )
