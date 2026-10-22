"""Delivery channels. Orders arrive by signed webhook (or are keyed in at the register), become DELIVERY open orders
on the channel's branch, wait in the register's incoming queue to be accepted (then go to the kitchen) or rejected,
and are settled with the "channel" tender: the app owes that money, less its commission, until it pays out."""

import hashlib
import hmac
import json
import secrets
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Protocol

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import Principal
from app.core.errors import ApiError
from app.core.security import decrypt_value, encrypt_value
from app.models.channel import ChannelPayout, DeliveryChannel
from app.models.product import Product
from app.models.restaurant import OpenOrder, OpenOrderItem
from app.models.sale import Sale
from app.models.sale_tender import SaleTender
from app.models.store import Store
from app.models.user import User
from app.schemas.channels import (
    ChannelDecision,
    ChannelIn,
    ChannelItemIn,
    ChannelOrderIn,
    ChannelOut,
    ChannelSecretOut,
    ManualChannelOrder,
    PayoutIn,
    PayoutOut,
    SettlementReport,
    SettlementRow,
    WebhookResult,
)
from app.schemas.orders import OrderOut
from app.services import audit, order_service

MAX_BODY_BYTES = 256 * 1024
POSTED = ("completed", "partially_refunded", "refunded")


def _now() -> datetime:
    return datetime.now(UTC)


# --- Adapters ---------------------------------------------------------------------------------------------


class ChannelAdapter(Protocol):
    """Turns a provider's webhook body into the normalised order. Named providers (Talabat, Deliveroo, Careem)
    plug in here; until then they send the generic format."""

    code: str

    def parse(self, payload: object) -> ChannelOrderIn: ...


class GenericAdapter:
    code = "generic"

    def parse(self, payload: object) -> ChannelOrderIn:
        return ChannelOrderIn.model_validate(payload)


ADAPTERS: dict[str, ChannelAdapter] = {"generic": GenericAdapter()}


def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


# --- Channels ---------------------------------------------------------------------------------------------


def _out(channel: DeliveryChannel) -> ChannelOut:
    return ChannelOut(
        id=channel.id,
        name=channel.name,
        code=channel.code,
        store_id=channel.store_id,
        adapter=channel.adapter,
        commission_bps=channel.commission_bps,
        price_markup_bps=channel.price_markup_bps,
        auto_accept=channel.auto_accept,
        default_prep_minutes=channel.default_prep_minutes,
        is_active=channel.is_active,
        webhook_path=f"/api/v1/channels/{channel.code}/orders",
        created_at=channel.created_at,
    )


def list_channels(db: Session, principal: Principal) -> list[ChannelOut]:
    statement = select(DeliveryChannel).order_by(DeliveryChannel.name)
    if principal.store_id is not None:
        statement = statement.where(DeliveryChannel.store_id == principal.store_id)
    return [_out(channel) for channel in db.scalars(statement)]


def _check(db: Session, data: ChannelIn, channel_id: uuid.UUID | None) -> None:
    if db.get(Store, data.store_id) is None:
        raise ApiError(422, "invalid_request", "Choose the branch the channel's orders arrive at.")
    taken = db.scalar(
        select(DeliveryChannel.id).where(DeliveryChannel.code == data.code, DeliveryChannel.id != channel_id)
    )
    if taken is not None:
        raise ApiError(409, "conflict", f"The code {data.code} is already used by another channel.")


def create_channel(db: Session, settings: Settings, actor: User, data: ChannelIn) -> ChannelSecretOut:
    _check(db, data, None)
    secret = secrets.token_urlsafe(32)
    channel = DeliveryChannel(
        id=uuid.uuid4(),
        **data.model_dump(),
        webhook_secret=encrypt_value(secret, settings),
        created_by_id=actor.id,
    )
    db.add(channel)
    audit.record(
        db,
        action_type="CREATE",
        action="channel.create",
        target_entity="DeliveryChannel",
        target_entity_id=channel.id,
        user_id=actor.id,
        new_values=data.model_dump(mode="json"),
    )
    db.commit()
    return ChannelSecretOut(channel=_out(channel), webhook_secret=secret)


def _channel(db: Session, channel_id: uuid.UUID) -> DeliveryChannel:
    channel = db.get(DeliveryChannel, channel_id)
    if channel is None:
        raise ApiError(404, "not_found", "Delivery channel was not found.")
    return channel


def update_channel(db: Session, actor: User, channel_id: uuid.UUID, data: ChannelIn) -> ChannelOut:
    channel = _channel(db, channel_id)
    _check(db, data, channel.id)
    before = _out(channel).model_dump(mode="json")
    for name, value in data.model_dump().items():
        setattr(channel, name, value)
    audit.record(
        db,
        action_type="UPDATE",
        action="channel.update",
        target_entity="DeliveryChannel",
        target_entity_id=channel.id,
        user_id=actor.id,
        old_values=before,
        new_values=data.model_dump(mode="json"),
    )
    db.commit()
    return _out(channel)


def rotate_secret(db: Session, settings: Settings, actor: User, channel_id: uuid.UUID) -> ChannelSecretOut:
    channel = _channel(db, channel_id)
    secret = secrets.token_urlsafe(32)
    channel.webhook_secret = encrypt_value(secret, settings)
    audit.record(
        db,
        action_type="UPDATE",
        action="channel.rotate_secret",
        target_entity="DeliveryChannel",
        target_entity_id=channel.id,
        user_id=actor.id,
    )
    db.commit()
    return ChannelSecretOut(channel=_out(channel), webhook_secret=secret)


# --- Intake -----------------------------------------------------------------------------------------------


def _match(db: Session, item: ChannelItemIn) -> Product | None:
    if item.product_id is not None:
        return db.get(Product, item.product_id)
    for column, value in ((Product.sku, item.sku), (Product.barcode, item.barcode), (Product.plu_code, item.plu)):
        if value:
            product = db.scalar(select(Product).where(column == value.strip()))
            if product is not None:
                return product
    return None


def _lines(
    db: Session, channel: DeliveryChannel, items: list[ChannelItemIn]
) -> list[tuple[Product, ChannelItemIn, int]]:
    matched: list[tuple[Product, ChannelItemIn, int]] = []
    unknown: list[str] = []
    for item in items:
        product = _match(db, item)
        label = item.sku or item.barcode or item.plu or item.name or str(item.product_id)
        if product is None or product.is_ingredient:
            unknown.append(label)
            continue
        if product.is_serialized or product.sold_by_weight:
            raise ApiError(422, "invalid_request", f"{product.name} cannot be ordered through a delivery app.")
        price = item.unit_price_cents
        if price is None:
            price = (product.price_cents * (10_000 + channel.price_markup_bps) + 5_000) // 10_000
        matched.append((product, item, price))
    if unknown:
        raise ApiError(
            422,
            "unknown_items",
            f"These items do not match the menu: {', '.join(unknown)}.",
            details={"unknown": unknown},
        )
    return matched


def _fire(db: Session, order: OpenOrder) -> None:
    fired = [item for item in order_service.live_items(order) if item.sent_at is None]
    if not fired:
        return
    now = _now()
    for item in fired:
        item.sent_at = now
    for hook in order_service.ON_SEND:
        hook(db, order, fired)


def intake(
    db: Session,
    channel: DeliveryChannel,
    data: ChannelOrderIn,
    *,
    opener: User,
    accepted: bool,
) -> tuple[OpenOrder, bool]:
    """Opens the order (or returns the one this external id already opened)."""
    existing = db.scalar(
        select(OpenOrder).where(OpenOrder.channel_id == channel.id, OpenOrder.external_ref == data.external_id)
    )
    if existing is not None:
        return existing, False
    lines = _lines(db, channel, data.items)
    customer = data.customer
    note = " · ".join(
        part for part in (customer.name if customer else None, customer.phone if customer else None, data.notes) if part
    )
    order = OpenOrder(
        store_id=channel.store_id,
        number=order_service._next_number(db, channel.store_id),
        service_type="DELIVERY",
        status="OPEN",
        covers=0,
        name=f"{channel.name} {data.external_id}"[:80],
        note=note[:255] or None,
        opened_by_id=opener.id,
        revision=1,
        channel_id=channel.id,
        external_ref=data.external_id,
        channel_status="ACCEPTED" if accepted else "PENDING",
        prep_minutes=(data.prep_minutes or channel.default_prep_minutes) if accepted else data.prep_minutes,
        channel_payload=data.model_dump(mode="json", exclude={"items"}),
        opened_at=_now(),
        updated_at=_now(),
    )
    db.add(order)
    db.flush()
    for position, (product, item, price) in enumerate(lines):
        order.items.append(
            OpenOrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=item.quantity,
                unit_price_cents=price,
                note=(item.note or "").strip() or None,
                position=position,
                added_by_id=opener.id,
            )
        )
    db.flush()
    if accepted:
        _fire(db, order)
    return order, True


def receive_webhook(db: Session, settings: Settings, code: str, body: bytes, signature: str | None) -> WebhookResult:
    channel = db.scalar(select(DeliveryChannel).where(DeliveryChannel.code == code))
    if channel is None or not channel.is_active:
        raise ApiError(404, "not_found", "This delivery channel does not exist or is switched off.")
    if len(body) > MAX_BODY_BYTES:
        raise ApiError(413, "payload_too_large", "The order is too large.")
    given = (signature or "").strip().removeprefix("sha256=")
    expected = sign(decrypt_value(channel.webhook_secret, settings), body)
    if not given or not hmac.compare_digest(given, expected):
        raise ApiError(401, "invalid_signature", "The X-Channel-Signature does not match this channel's secret.")
    try:
        payload = json.loads(body)
        data = ADAPTERS.get(channel.adapter, ADAPTERS["generic"]).parse(payload)
    except (ValueError, ValidationError) as exc:
        raise ApiError(422, "invalid_request", "The order body is not in the expected format.") from exc
    opener = db.get(User, channel.created_by_id)
    if opener is None:
        raise ApiError(409, "conflict", "The channel has no owner to open orders for.")
    order, created = intake(db, channel, data, opener=opener, accepted=channel.auto_accept)
    if created:
        audit.record(
            db,
            action_type="CREATE",
            action="channel.order_received",
            target_entity="OpenOrder",
            target_entity_id=order.id,
            store_id=order.store_id,
            client_device="system",
            details={"channel": channel.code, "external_id": data.external_id, "lines": len(data.items)},
        )
    db.commit()
    return WebhookResult(
        order_id=order.id,
        number=order.number,
        result="created" if created else "duplicate",
        channel_status=order.channel_status,
    )


def manual_order(db: Session, principal: Principal, data: ManualChannelOrder) -> OrderOut:
    """A delivery-app order keyed in at the register; it is accepted at once and its items added as a tab."""
    channel = _channel(db, data.channel_id)
    if not channel.is_active:
        raise ApiError(422, "invalid_request", f"{channel.name} is switched off.")
    order_service._scope(principal, channel.store_id)
    actor = order_service._actor(db, principal, data.user_id, channel.store_id)
    existing = db.scalar(
        select(OpenOrder).where(OpenOrder.channel_id == channel.id, OpenOrder.external_ref == data.external_ref)
    )
    if existing is not None:
        raise ApiError(
            409, "conflict", f"{channel.name} order {data.external_ref} is already open as #{existing.number}."
        )
    order = OpenOrder(
        store_id=channel.store_id,
        number=order_service._next_number(db, channel.store_id),
        service_type="DELIVERY",
        status="OPEN",
        name=f"{channel.name} {data.external_ref}"[:80],
        note=" · ".join(part for part in (data.customer_name, data.note) if part) or None,
        opened_by_id=actor.id,
        revision=1,
        channel_id=channel.id,
        external_ref=data.external_ref,
        channel_status="ACCEPTED",
        prep_minutes=channel.default_prep_minutes,
        opened_at=_now(),
        updated_at=_now(),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order_service.orders_out(db, [order])[0]


def _pending(db: Session, principal: Principal, order_id: uuid.UUID, data: ChannelDecision) -> tuple[OpenOrder, User]:
    order = order_service._writable(db, principal, order_id, data.revision)
    actor = order_service._actor(db, principal, data.user_id, order.store_id)
    if order.channel_id is None or order.channel_status != "PENDING":
        raise ApiError(409, "not_pending", "Only a delivery order waiting for a decision can be accepted or rejected.")
    return order, actor


def accept(db: Session, principal: Principal, order_id: uuid.UUID, data: ChannelDecision) -> OrderOut:
    order, actor = _pending(db, principal, order_id, data)
    channel = db.get(DeliveryChannel, order.channel_id)
    order.channel_status = "ACCEPTED"
    order.prep_minutes = data.prep_minutes or order.prep_minutes or (channel.default_prep_minutes if channel else 20)
    _fire(db, order)
    audit.record(
        db,
        action_type="UPDATE",
        action="channel.order_accept",
        target_entity="OpenOrder",
        target_entity_id=order.id,
        store_id=order.store_id,
        user_id=actor.id,
        details={"prep_minutes": order.prep_minutes},
    )
    order_service._touch(order)
    db.commit()
    return order_service.orders_out(db, [order])[0]


def reject(db: Session, principal: Principal, order_id: uuid.UUID, data: ChannelDecision) -> OrderOut:
    order, actor = _pending(db, principal, order_id, data)
    reason = (data.reason or "").strip() or "Rejected by the restaurant"
    now = _now()
    for item in order_service.live_items(order):
        item.voided_at = now
        item.void_reason = reason
        item.voided_by_id = actor.id
    order.channel_status = "REJECTED"
    order.status = "VOID"
    order.closed_at = now
    audit.record(
        db,
        action_type="UPDATE",
        action="channel.order_reject",
        target_entity="OpenOrder",
        target_entity_id=order.id,
        store_id=order.store_id,
        user_id=actor.id,
        reason_notes=reason,
    )
    order_service._touch(order)
    db.commit()
    return order_service.orders_out(db, [order])[0]


def channel_names(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    return dict(db.execute(select(DeliveryChannel.id, DeliveryChannel.name).where(DeliveryChannel.id.in_(ids))).all())


order_service.CHANNEL_NAMES.append(channel_names)


# --- Settlement -------------------------------------------------------------------------------------------


def record_payout(db: Session, actor: User, channel_id: uuid.UUID, data: PayoutIn) -> PayoutOut:
    channel = _channel(db, channel_id)
    payout = ChannelPayout(
        channel_id=channel.id,
        amount_cents=data.amount_cents,
        commission_cents=data.commission_cents,
        reference=(data.reference or "").strip() or None,
        note=(data.note or "").strip() or None,
        received_at=data.received_at or _now(),
        recorded_by_id=actor.id,
    )
    db.add(payout)
    audit.record(
        db,
        action_type="CREATE",
        action="channel.payout",
        target_entity="DeliveryChannel",
        target_entity_id=channel.id,
        user_id=actor.id,
        new_values=data.model_dump(mode="json"),
    )
    db.commit()
    return _payout_out(payout, channel.name)


def _payout_out(payout: ChannelPayout, name: str) -> PayoutOut:
    return PayoutOut(
        id=payout.id,
        channel_id=payout.channel_id,
        channel_name=name,
        amount_cents=payout.amount_cents,
        commission_cents=payout.commission_cents,
        reference=payout.reference,
        note=payout.note,
        received_at=payout.received_at,
    )


def _gross(db: Session, since: datetime | None, until: datetime | None) -> dict[uuid.UUID, tuple[int, int]]:
    """Channel tenders per channel: (orders, amount)."""
    statement = (
        select(OpenOrder.channel_id, func.count(func.distinct(Sale.id)), func.sum(SaleTender.amount_cents))
        .join(Sale, Sale.order_id == OpenOrder.id)
        .join(SaleTender, SaleTender.sale_id == Sale.id)
        .where(
            OpenOrder.channel_id.is_not(None),
            SaleTender.method == "channel",
            Sale.status.in_(POSTED),
            Sale.is_quote_proforma.is_(False),
        )
        .group_by(OpenOrder.channel_id)
    )
    if since is not None:
        statement = statement.where(Sale.created_at >= since)
    if until is not None:
        statement = statement.where(Sale.created_at < until)
    return {row[0]: (int(row[1]), int(row[2] or 0)) for row in db.execute(statement)}


def commission(gross_cents: int, bps: int) -> int:
    return (gross_cents * bps + 5_000) // 10_000


def settlement(db: Session, *, start: date, end: date) -> SettlementReport:
    if end < start or (end - start).days > 400:
        raise ApiError(422, "validation_error", "Pick a period of at most 400 days that ends after it starts.")
    since = datetime.combine(start, time.min, UTC)
    until = datetime.combine(end + timedelta(days=1), time.min, UTC)
    channels = list(db.scalars(select(DeliveryChannel).order_by(DeliveryChannel.name)))
    period = _gross(db, since, until)
    lifetime = _gross(db, None, None)
    payouts = list(
        db.scalars(
            select(ChannelPayout)
            .where(ChannelPayout.received_at >= since, ChannelPayout.received_at < until)
            .order_by(ChannelPayout.received_at.desc())
        )
    )
    paid_all = {
        row[0]: int(row[1] or 0)
        for row in db.execute(
            select(ChannelPayout.channel_id, func.sum(ChannelPayout.amount_cents)).group_by(ChannelPayout.channel_id)
        )
    }
    rows: list[SettlementRow] = []
    for channel in channels:
        orders, gross = period.get(channel.id, (0, 0))
        kept = commission(gross, channel.commission_bps)
        _, all_gross = lifetime.get(channel.id, (0, 0))
        rows.append(
            SettlementRow(
                channel_id=channel.id,
                name=channel.name,
                commission_bps=channel.commission_bps,
                orders=orders,
                gross_cents=gross,
                commission_cents=kept,
                net_cents=gross - kept,
                paid_out_cents=sum(p.amount_cents for p in payouts if p.channel_id == channel.id),
                outstanding_cents=all_gross
                - commission(all_gross, channel.commission_bps)
                - paid_all.get(channel.id, 0),
            )
        )
    names = {channel.id: channel.name for channel in channels}
    return SettlementReport(
        start=start,
        end=end,
        rows=rows,
        payouts=[_payout_out(payout, names.get(payout.channel_id, "Channel")) for payout in payouts],
    )


def payouts_between(db: Session, since: datetime, until: datetime) -> list[ChannelPayout]:
    return list(
        db.scalars(select(ChannelPayout).where(ChannelPayout.received_at >= since, ChannelPayout.received_at < until))
    )
