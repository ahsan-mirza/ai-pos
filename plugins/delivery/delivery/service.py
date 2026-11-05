"""Connection setup for Delivery Integrations. Marketplace calls are refused until a provider is approved."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.capabilities import FOOD_AND_BEVERAGE, Capability, has_capability
from app.core.config import Settings
from app.core.errors import ApiError
from app.core.security import encrypt_value
from app.models.channel import DeliveryChannel
from app.models.restaurant import OpenOrder
from app.models.store import Store
from app.models.user import User
from app.schemas.channels import ChannelIn
from app.services import audit, channel_service
from app.services.settings_service import load_settings
from delivery.models import DeliveryConnection
from delivery.providers import PROVIDERS, get_provider


def guard(db: Session) -> str:
    if not has_capability(db, Capability.DELIVERY_INTEGRATIONS):
        raise ApiError(403, "addon_required", "Delivery Integrations is not enabled for this business.")
    profile = load_settings(db).business_profile
    if profile not in FOOD_AND_BEVERAGE:
        raise ApiError(
            403,
            "unsupported_business",
            "Delivery Integrations is available for restaurant, cafe, and quick-service businesses.",
        )
    return profile


def providers() -> list[dict]:
    return [
        {
            "code": item.code,
            "name": item.name,
            "kind": item.kind,
            "status": item.status,
            "countries": list(item.countries),
            "capabilities": list(item.capabilities),
            "detail": item.detail,
        }
        for item in PROVIDERS
    ]


def list_connections(db: Session, store_id: uuid.UUID | None = None) -> list[dict]:
    guard(db)
    query = select(DeliveryConnection).order_by(DeliveryConnection.created_at.desc())
    if store_id is not None:
        query = query.where(DeliveryConnection.store_id == store_id)
    return [_public(db, row) for row in db.scalars(query)]


def create_connection(db: Session, actor: User, data: dict, store_id: uuid.UUID | None = None) -> dict:
    guard(db)
    _same_branch(store_id, data["store_id"])
    provider = get_provider(str(data["provider"]))
    if provider is None:
        raise ApiError(422, "unknown_provider", "Choose a provider from the catalogue.")
    store = db.get(Store, data["store_id"])
    if store is None:
        raise ApiError(422, "invalid_request", "Choose a branch for this connection.")
    existing = db.scalar(
        select(DeliveryConnection).where(
            DeliveryConnection.provider_code == provider.code,
            DeliveryConnection.store_id == store.id,
        )
    )
    if existing is not None:
        return _public(db, existing)
    row = DeliveryConnection(
        provider_code=provider.code,
        market=(data.get("market") or "").strip().upper(),
        store_id=store.id,
        status="draft",
    )
    db.add(row)
    audit.record(
        db,
        action_type="CREATE",
        action="delivery.connection.create",
        target_entity="DeliveryConnection",
        target_entity_id=row.id,
        user_id=actor.id,
        new_values={"provider": provider.code, "store_id": str(store.id)},
    )
    db.commit()
    db.refresh(row)
    return _public(db, row)


def test_connection(db: Session, connection_id: uuid.UUID, store_id: uuid.UUID | None = None) -> dict:
    guard(db)
    row = _row(db, connection_id, store_id)
    provider = get_provider(row.provider_code)
    row.last_checked_at = datetime.now(UTC)
    if provider is None or provider.status != "available":
        row.last_error = "This provider is awaiting partner approval."
        row.status = "draft" if row.status != "active" else row.status
        db.commit()
        raise ApiError(422, "provider_unavailable", row.last_error)
    if not has_capability(db, Capability.DELIVERY_CHANNELS):
        row.last_error = "Enable Delivery channels so orders can reach the register and kitchen."
        db.commit()
        raise ApiError(422, "channel_module_required", row.last_error)
    row.last_error = None
    db.commit()
    db.refresh(row)
    return _public(db, row)


def activate(
    db: Session,
    settings: Settings,
    actor: User,
    connection_id: uuid.UUID,
    store_id: uuid.UUID | None = None,
) -> dict:
    guard(db)
    row = _row(db, connection_id, store_id)
    provider = get_provider(row.provider_code)
    if provider is None or provider.status != "available":
        raise ApiError(422, "provider_unavailable", "This provider cannot be activated without partner API access.")
    if not has_capability(db, Capability.DELIVERY_CHANNELS):
        raise ApiError(422, "channel_module_required", "Enable Delivery channels before activating this connection.")
    secret = None
    if row.channel_id is None:
        created = channel_service.create_channel(
            db,
            settings,
            actor,
            ChannelIn(
                name=provider.name[:60],
                code=f"di-{uuid.uuid4().hex[:8]}",
                store_id=row.store_id,
                is_active=True,
            ),
        )
        row.channel_id = created.channel.id
        secret = created.webhook_secret
        row.credential_encrypted = encrypt_value(secret, settings)
    else:
        channel = db.get(DeliveryChannel, row.channel_id)
        if channel is not None:
            channel.is_active = True
    row.status = "active"
    row.last_error = None
    row.last_checked_at = datetime.now(UTC)
    audit.record(
        db,
        action_type="UPDATE",
        action="delivery.connection.activate",
        target_entity="DeliveryConnection",
        target_entity_id=row.id,
        user_id=actor.id,
        new_values={"provider": row.provider_code, "channel_id": str(row.channel_id)},
    )
    db.commit()
    db.refresh(row)
    body = _public(db, row)
    body["webhook_secret"] = secret
    return body


def pause(db: Session, actor: User, connection_id: uuid.UUID, store_id: uuid.UUID | None = None) -> dict:
    guard(db)
    row = _row(db, connection_id, store_id)
    if row.channel_id is not None:
        channel = db.get(DeliveryChannel, row.channel_id)
        if channel is not None:
            channel.is_active = False
    row.status = "paused"
    audit.record(
        db,
        action_type="UPDATE",
        action="delivery.connection.pause",
        target_entity="DeliveryConnection",
        target_entity_id=row.id,
        user_id=actor.id,
        new_values={"status": "paused"},
    )
    db.commit()
    db.refresh(row)
    return _public(db, row)


def orders(db: Session, store_id: uuid.UUID | None = None) -> list[dict]:
    guard(db)
    channel_query = select(DeliveryConnection.channel_id).where(DeliveryConnection.channel_id.is_not(None))
    if store_id is not None:
        channel_query = channel_query.where(DeliveryConnection.store_id == store_id)
    channel_ids = list(db.scalars(channel_query))
    if not channel_ids:
        return []
    rows = db.scalars(
        select(OpenOrder).where(OpenOrder.channel_id.in_(channel_ids)).order_by(OpenOrder.opened_at.desc()).limit(50)
    )
    return [
        {
            "id": row.id,
            "number": row.number,
            "store_id": row.store_id,
            "status": row.status,
            "external_ref": row.external_ref,
            "channel_status": row.channel_status,
            "channel_id": row.channel_id,
        }
        for row in rows
    ]


def health(db: Session, store_id: uuid.UUID | None = None) -> dict:
    profile = guard(db)
    scoped = select(DeliveryConnection)
    if store_id is not None:
        scoped = scoped.where(DeliveryConnection.store_id == store_id)
    connections = int(db.scalar(select(func.count()).select_from(scoped.subquery())) or 0)
    active = int(
        db.scalar(
            select(func.count()).select_from(
                scoped.where(DeliveryConnection.status == "active").subquery()
            )
        )
        or 0
    )
    channel_query = select(DeliveryConnection.channel_id).where(DeliveryConnection.channel_id.is_not(None))
    if store_id is not None:
        channel_query = channel_query.where(DeliveryConnection.store_id == store_id)
    channel_ids = list(db.scalars(channel_query))
    open_orders = 0
    if channel_ids:
        open_orders = int(
            db.scalar(
                select(func.count())
                .select_from(OpenOrder)
                .where(OpenOrder.channel_id.in_(channel_ids), OpenOrder.status == "OPEN")
            )
            or 0
        )
    return {
        "addon": "delivery_integrations",
        "profile": profile,
        "connections": connections,
        "active_connections": active,
        "open_orders": open_orders,
        "available_providers": sum(1 for item in PROVIDERS if item.status == "available"),
        "awaiting_partner": sum(1 for item in PROVIDERS if item.status == "awaiting_partner"),
    }


def _same_branch(actor_store: uuid.UUID | None, target: uuid.UUID) -> None:
    if actor_store is not None and actor_store != target:
        raise ApiError(404, "not_found", "Delivery connection was not found.")


def _row(db: Session, connection_id: uuid.UUID, store_id: uuid.UUID | None = None) -> DeliveryConnection:
    row = db.get(DeliveryConnection, connection_id)
    if row is None or (store_id is not None and row.store_id != store_id):
        raise ApiError(404, "not_found", "Delivery connection was not found.")
    return row


def _public(db: Session, row: DeliveryConnection) -> dict:
    path = None
    if row.channel_id is not None:
        channel = db.get(DeliveryChannel, row.channel_id)
        if channel is not None:
            path = f"/api/v1/channels/{channel.code}/orders"
    return {
        "id": row.id,
        "provider": row.provider_code,
        "market": row.market,
        "store_id": row.store_id,
        "status": row.status,
        "channel_id": row.channel_id,
        "webhook_path": path,
        "webhook_secret": None,
        "last_error": row.last_error,
        "last_checked_at": row.last_checked_at,
    }
