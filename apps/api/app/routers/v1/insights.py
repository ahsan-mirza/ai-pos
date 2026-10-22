import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, require_capability
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.insights import (
    AnomalyReport,
    InsightFeed,
    KitchenReport,
    PricingReport,
    ShrinkReport,
    TableReport,
    UpsellReport,
)
from app.services import insights_service, restaurant_insights_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanAudit = Annotated[Principal, Depends(authorize(Permission.AUDIT_READ))]
CanRead = Annotated[Principal, Depends(authorize(Permission.PORTAL_REPORTS_READ))]
# Waiters see add-on prompts on the register; managers see the same pairs in the portal.
AtRegister = Annotated[Principal, Depends(authorize(allow_device=True, scopes=("pos", "portal")))]


@router.get("/anomalies", response_model=AnomalyReport)
def anomalies(
    db: Db,
    principal: CanAudit,
    days: Annotated[int, Query(ge=7, le=365)] = 30,
    store_id: uuid.UUID | None = None,
) -> AnomalyReport:
    """Cashiers whose voids, no-sale opens, refunds or price overrides stand out from their peers, and drawers
    that keep coming up short or over."""
    return insights_service.anomalies(db, principal, days=days, store_id=store_id)


@router.get("/pricing", response_model=PricingReport)
def pricing(
    db: Db,
    principal: CanRead,
    store_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> PricingReport:
    """Price changes worth making: below the margin floor, demand outrunning stock, expiring batches, dead stock."""
    return insights_service.pricing(db, principal, store_id=store_id, limit=limit)


@router.get("/shrink", response_model=ShrinkReport)
def shrink(
    db: Db,
    principal: CanRead,
    days: Annotated[int, Query(ge=7, le=730)] = 90,
    store_id: uuid.UUID | None = None,
) -> ShrinkReport:
    """Stock lost to damage, expiry, theft and count differences, at cost, against sales."""
    return insights_service.shrink(db, principal, days=days, store_id=store_id)


@router.get("/kitchen", response_model=KitchenReport, dependencies=[Depends(require_capability(Capability.KDS))])
def kitchen(db: Db, principal: CanRead, store_id: uuid.UUID | None = None) -> KitchenReport:
    """Prep times per station, a fitted prep-time model, the wait a new ticket faces now, and tickets at risk."""
    return restaurant_insights_service.kitchen(db, principal, store_id=store_id)


@router.get("/tables", response_model=TableReport, dependencies=[Depends(require_capability(Capability.TABLES))])
def tables(
    db: Db,
    principal: CanRead,
    store_id: uuid.UUID | None = None,
    days: Annotated[int, Query(ge=7, le=365)] = 28,
) -> TableReport:
    """How long tables are held by party size and day-part, revenue per table-hour, and when open tables free up."""
    return restaurant_insights_service.tables(db, principal, store_id=store_id, days=days)


@router.get("/upsell", response_model=UpsellReport)
def upsell(
    db: Db,
    principal: AtRegister,
    product_id: Annotated[list[uuid.UUID] | None, Query(max_length=50)] = None,
    store_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> UpsellReport:
    """Add-ons guests usually order with what is on the order (pass product_id for each line), or the strongest
    pairs across the menu."""
    return restaurant_insights_service.upsell(
        db, principal, product_ids=product_id or [], store_id=store_id, limit=limit
    )


@router.get("/feed", response_model=InsightFeed)
def feed(db: Db, principal: Annotated[Principal, Depends(authorize(Permission.PORTAL_ACCESS))]) -> InsightFeed:
    """The most urgent signals for the header bell, filtered to what this user may see."""
    return insights_service.feed(db, principal)
