"""Laundry intake. Pricing and tax come from the catalog quote. Deposits are held, not a second tender ledger."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, time

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.customer import Customer
from app.models.device import Device
from app.models.laundry import LaundryBranchCapacity, LaundryService
from app.models.laundry_order import (
    PRE_PRODUCTION,
    LaundryBag,
    LaundryDeposit,
    LaundryGarment,
    LaundryOrder,
    LaundryOrderEvent,
    LaundryPhoto,
    LaundryTag,
    LaundryTagEvent,
)
from app.models.store import Store
from app.schemas.laundry_order import DepositPost, GarmentPatch, OrderIn, PhotoIn, QuantityChange
from app.services import audit, laundry_catalog
from app.services.laundry_pricing import LaundryPriceError, net_weight
from app.services.laundry_pricing import quote as price_quote
from app.services.sync_service import SyncContext, register_handler
from app.services.tax import line_tax

_ALLOWED_MIME = {"image/jpeg": (b"\xff\xd8\xff",), "image/png": (b"\x89PNG",), "image/webp": (b"RIFF",)}


def _now() -> datetime:
    return datetime.now(UTC)


def _payment(paid: int, total: int) -> str:
    if total == 0 or paid >= total:
        return "PAID"
    if paid <= 0:
        return "UNPAID"
    return "PARTIAL"


def _event(
    db: Session, order: LaundryOrder, kind: str, reason: str, actor_id: uuid.UUID | None, to_status: str | None = None
) -> None:
    db.add(
        LaundryOrderEvent(
            order_id=order.id,
            kind=kind,
            from_status=order.operational_status,
            to_status=to_status or order.operational_status,
            reason=reason,
            actor_id=actor_id,
        )
    )


def _capacity(db: Session, store_id: uuid.UUID) -> int | None:
    settings = laundry_catalog.settings_row(db)
    branch = db.scalar(select(LaundryBranchCapacity).where(LaundryBranchCapacity.store_id == store_id))
    if branch is not None:
        return branch.express_daily_capacity
    return settings.express_daily_capacity


def _express_full(db: Session, store_id: uuid.UUID) -> bool:
    capacity = _capacity(db, store_id)
    if capacity is None:
        return False
    start = datetime.combine(_now().date(), time.min, tzinfo=UTC)
    used = int(
        db.scalar(
            select(func.count())
            .select_from(LaundryOrder)
            .where(
                LaundryOrder.intake_store_id == store_id,
                LaundryOrder.express.is_(True),
                LaundryOrder.operational_status != "CANCELLED",
                LaundryOrder.created_at >= start,
            )
        )
        or 0
    )
    return used >= capacity


def _device(db: Session, device_id: uuid.UUID | None, store_id: uuid.UUID) -> uuid.UUID | None:
    if device_id is None:
        return None
    device = db.get(Device, device_id)
    if device is None or device.revoked_at is not None or device.store_id != store_id:
        raise ApiError(422, "invalid_device", "That register is not active at this branch.")
    return device.id


def _quote_line(db: Session, order: OrderIn, service_id: uuid.UUID, quantity: int, extras: int, authorized: bool):
    try:
        priced, _used = laundry_catalog.quote_service(
            db,
            service_id,
            quantity=quantity,
            on=_now().date(),
            store_id=order.intake_store_id,
            customer_id=order.customer_id,
            price_list_id=order.price_list_id,
            extras_cents=extras,
            express=order.express,
            same_day=False,
            special=False,
            discount_cents=0,
            discount_authorized=authorized,
        )
    except ApiError:
        raise
    return priced


def create_order(
    db: Session,
    data: OrderIn,
    *,
    actor_id: uuid.UUID | None,
    discount_authorized: bool,
) -> LaundryOrder:
    if not data.garments and not data.bags:
        raise ApiError(422, "empty_order", "Add a garment or a bag before creating the order.")
    found = db.scalar(select(LaundryOrder).where(LaundryOrder.idempotency_key == data.idempotency_key))
    if found is not None:
        return found
    if data.id is not None and db.get(LaundryOrder, data.id) is not None:
        raise ApiError(409, "duplicate_order", "That order id was already used.")
    if db.get(Store, data.intake_store_id) is None:
        raise ApiError(404, "not_found", "The intake branch does not exist.")
    if db.get(Customer, data.customer_id) is None:
        raise ApiError(404, "not_found", "The customer does not exist.")
    if data.express and _express_full(db, data.intake_store_id):
        raise ApiError(422, "express_capacity", "Express service has no remaining capacity.")
    if data.discount_cents and not discount_authorized:
        raise ApiError(403, "discount_forbidden", "This user cannot discount a laundry order.")
    device_id = _device(db, data.device_id, data.intake_store_id)
    store = db.get(Store, data.intake_store_id)
    quotes = []
    garments: list[tuple[object, object]] = []
    bags: list[tuple[object, object]] = []
    for line in data.garments:
        priced = _quote_line(db, data, line.service_id, line.quantity, line.extras_cents, discount_authorized)
        quotes.append(priced)
        garments.append((line, priced))
    for line in data.bags:
        try:
            net = net_weight(line.gross_weight, line.tare_weight)
        except LaundryPriceError as exc:
            raise ApiError(422, exc.code, exc.message) from exc
        priced = _quote_line(db, data, line.service_id, net, line.extras_cents, discount_authorized)
        quotes.append(priced)
        bags.append((line, priced))
    net_cents = sum(item.net_cents for item in quotes)
    if data.discount_cents > net_cents:
        raise ApiError(422, "discount_too_large", "The discount is larger than the order.")
    rates = {item.rate_bps for item in quotes}
    services_inclusive = set()
    for line, _priced in garments + bags:
        service = db.get(laundry_catalog.LaundryService, line.service_id)
        services_inclusive.add(bool(service.price_includes_tax) if service is not None else False)
    if data.discount_cents and (len(rates) != 1 or len(services_inclusive) != 1):
        raise ApiError(422, "discount_mixed", "Discount one tax treatment at a time.")
    if data.discount_cents:
        taxed = line_tax(
            net_cents - data.discount_cents, 1, next(iter(rates)), inclusive=next(iter(services_inclusive))
        )
        tax_cents = taxed.tax_cents
        total_cents = taxed.line_total_cents
    else:
        tax_cents = sum(item.tax_cents for item in quotes)
        total_cents = sum(item.total_cents for item in quotes)
    paid = data.deposit.amount_cents if data.deposit is not None else 0
    if paid > total_cents:
        raise ApiError(422, "deposit_too_large", "The deposit cannot exceed the order total.")
    order = LaundryOrder(
        id=data.id or uuid.uuid4(),
        idempotency_key=data.idempotency_key,
        code="pending",
        intake_store_id=data.intake_store_id,
        plant_store_id=data.plant_store_id,
        customer_id=data.customer_id,
        order_type=data.order_type,
        price_list_id=data.price_list_id,
        currency=store.currency if store is not None else "AED",
        promised_at=data.promised_at,
        express=data.express,
        instructions=data.instructions,
        garment_count=sum(line.quantity for line in data.garments),
        bag_count=len(data.bags),
        measured_weight=sum(net_weight(line.gross_weight, line.tare_weight) for line in data.bags),
        subtotal_cents=sum(item.merchandise_cents for item in quotes),
        discount_cents=data.discount_cents,
        surcharge_cents=sum(item.surcharge_cents for item in quotes),
        tax_cents=tax_cents,
        total_cents=total_cents,
        amount_paid_cents=paid,
        balance_due_cents=total_cents - paid,
        payment_status=_payment(paid, total_cents),
        operational_status="TAGGED",
        collection_status="AT_BRANCH",
        claim_status="NONE",
        pricing_snapshot={"lines": [asdict(item) for item in quotes], "rate_bps": sorted(rates)},
        created_by_id=actor_id,
        device_id=device_id,
    )
    order.code = f"LD-{order.id.hex[:8].upper()}"
    db.add(order)
    db.flush()
    tag_number = 1
    for line, priced in garments:
        service = db.get(LaundryService, line.service_id)
        garment = LaundryGarment(
            order_id=order.id,
            service_id=line.service_id,
            workflow_code=service.workflow_code if service is not None else "",
            stage_entered_at=_now(),
            garment_type=line.garment_type,
            description=line.description,
            brand=line.brand,
            colour=line.colour,
            fabric=line.fabric,
            size=line.size,
            quantity=line.quantity,
            instructions=line.instructions,
            condition=line.condition,
            stains=line.stains,
            pre_existing_damage=line.pre_existing_damage,
            stage="TAGGED",
            location_store_id=data.intake_store_id,
            line_snapshot=asdict(priced),
        )
        db.add(garment)
        db.flush()
        _tag(db, order, tag_number, device_id, garment_id=garment.id)
        tag_number += 1
    for line, priced in bags:
        bag = LaundryBag(
            order_id=order.id,
            service_id=line.service_id,
            bag_type=line.bag_type,
            gross_weight=line.gross_weight,
            tare_weight=line.tare_weight,
            net_weight=net_weight(line.gross_weight, line.tare_weight),
            scale_reference=line.scale_reference,
            location_store_id=data.intake_store_id,
            line_snapshot=asdict(priced),
        )
        db.add(bag)
        db.flush()
        _tag(db, order, tag_number, device_id, bag_id=bag.id)
        tag_number += 1
    if data.deposit is not None:
        db.add(
            LaundryDeposit(
                order_id=order.id,
                store_id=order.intake_store_id,
                amount_cents=data.deposit.amount_cents,
                method=data.deposit.method,
                status="HELD",
                received_by_id=actor_id,
                shift_id=data.deposit.shift_id,
            )
        )
    _event(db, order, "created", "", actor_id, "TAGGED")
    audit.record(
        db,
        action_type="CREATE",
        action="laundry.order",
        target_entity="LaundryOrder",
        target_entity_id=order.id,
        user_id=actor_id,
        details={"total_cents": order.total_cents, "code": order.code},
    )
    return order


def _tag(
    db: Session, order: LaundryOrder, number: int, device_id: uuid.UUID | None, garment_id=None, bag_id=None
) -> LaundryTag:
    tag = LaundryTag(
        code=f"{order.code}-{number:02d}",
        order_id=order.id,
        garment_id=garment_id,
        bag_id=bag_id,
        store_id=order.intake_store_id,
        status="active",
        device_id=device_id,
    )
    db.add(tag)
    db.flush()
    db.add(
        LaundryTagEvent(
            tag_id=tag.id,
            order_id=order.id,
            kind="issued",
            idempotency_key=f"issued:{tag.id}",
            device_id=device_id,
        )
    )
    return tag


def list_orders(db: Session, query: str, store_id: uuid.UUID | None) -> list[LaundryOrder]:
    statement = select(LaundryOrder).order_by(LaundryOrder.created_at.desc())
    if store_id is not None:
        statement = statement.where(LaundryOrder.intake_store_id == store_id)
    if query.strip():
        statement = statement.where(LaundryOrder.code.ilike(f"%{query.strip()}%"))
    return list(db.scalars(statement.limit(100)))


def get_order(db: Session, order_id: uuid.UUID) -> LaundryOrder:
    order = db.get(LaundryOrder, order_id)
    if order is None:
        raise ApiError(404, "not_found", "This laundry order does not exist.")
    return order


def _claim(db: Session, order: LaundryOrder, expected: int) -> None:
    result = db.execute(
        update(LaundryOrder)
        .where(LaundryOrder.id == order.id, LaundryOrder.version == expected)
        .values(version=expected + 1)
    )
    if result.rowcount != 1:
        raise ApiError(409, "order_conflict", "This order was updated by someone else.")
    order.version = expected + 1


def update_garment(
    db: Session, order_id: uuid.UUID, patch: GarmentPatch, *, actor_id: uuid.UUID | None, can_override: bool
) -> LaundryOrder:
    order = get_order(db, order_id)
    if order.operational_status == "CANCELLED":
        raise ApiError(409, "order_closed", "A cancelled order cannot be edited.")
    garment = db.get(LaundryGarment, patch.garment_id)
    if garment is None or garment.order_id != order.id:
        raise ApiError(404, "not_found", "That garment is not on this order.")
    if patch.service_id is not None and patch.service_id != garment.service_id:
        if order.operational_status not in PRE_PRODUCTION and not can_override:
            raise ApiError(403, "override_forbidden", "Changing a production order needs pricing override.")
        if db.get(laundry_catalog.LaundryService, patch.service_id) is None:
            raise ApiError(404, "not_found", "This service is not in the catalog.")
    _claim(db, order, patch.version)
    if patch.service_id is not None and patch.service_id != garment.service_id:
        priced, _used = laundry_catalog.quote_service(
            db,
            patch.service_id,
            quantity=garment.quantity,
            on=_now().date(),
            store_id=order.intake_store_id,
            customer_id=order.customer_id,
            price_list_id=order.price_list_id,
            extras_cents=int(garment.line_snapshot.get("extras_cents", 0)),
            express=order.express,
            same_day=False,
            special=False,
            discount_cents=0,
            discount_authorized=True,
        )
        garment.service_id = patch.service_id
        garment.line_snapshot = asdict(priced)
        _retotal(db, order)
    if patch.description is not None:
        garment.description = patch.description
    if patch.condition is not None:
        garment.condition = patch.condition
    if patch.stains is not None:
        garment.stains = patch.stains
    if patch.instructions is not None:
        garment.instructions = patch.instructions
    _event(db, order, "garment_updated", "", actor_id)
    return order


def post_deposit(db: Session, order_id: uuid.UUID, data: DepositPost, *, actor_id: uuid.UUID | None) -> LaundryOrder:
    existing = db.get(LaundryDeposit, data.id)
    if existing is not None:
        if existing.order_id != order_id:
            raise ApiError(409, "duplicate_payment", "That payment was already recorded on another order.")
        return get_order(db, order_id)
    order = get_order(db, order_id)
    if order.operational_status == "CANCELLED":
        raise ApiError(409, "order_closed", "A cancelled order cannot take a payment.")
    if order.amount_paid_cents + data.amount_cents > order.total_cents:
        raise ApiError(422, "deposit_too_large", "The payment cannot exceed the outstanding balance.")
    _claim(db, order, data.version)
    order.amount_paid_cents += data.amount_cents
    order.balance_due_cents = order.total_cents - order.amount_paid_cents
    order.payment_status = _payment(order.amount_paid_cents, order.total_cents)
    db.add(
        LaundryDeposit(
            id=data.id,
            order_id=order.id,
            store_id=order.intake_store_id,
            amount_cents=data.amount_cents,
            method=data.method,
            status="HELD",
            received_by_id=actor_id,
            shift_id=data.shift_id,
        )
    )
    _event(db, order, "deposit", data.method, actor_id)
    return order


def change_quantity(
    db: Session, order_id: uuid.UUID, change: QuantityChange, *, actor_id: uuid.UUID | None, can_override: bool
) -> LaundryOrder:
    order = get_order(db, order_id)
    if order.version != change.version:
        raise ApiError(409, "order_conflict", "This order was updated by someone else.")
    if order.operational_status == "CANCELLED":
        raise ApiError(409, "order_closed", "A cancelled order cannot be edited.")
    garment = db.get(LaundryGarment, change.garment_id)
    if garment is None or garment.order_id != order.id:
        raise ApiError(404, "not_found", "That garment is not on this order.")
    service = db.get(laundry_catalog.LaundryService, garment.service_id)
    if service is None:
        raise ApiError(404, "not_found", "This service is not in the catalog.")
    if order.operational_status not in PRE_PRODUCTION:
        if not change.reason.strip():
            raise ApiError(422, "reason_required", "A quantity change after production starts needs a reason.")
        if not can_override:
            raise ApiError(403, "override_forbidden", "Changing a production order needs pricing override.")
        unit_price = int(garment.line_snapshot["unit_price_cents"])
        rate_bps = int(garment.line_snapshot["rate_bps"])
    else:
        unit_price = service.base_rate_cents
        rate_bps = int(garment.line_snapshot["rate_bps"])
    priced = price_quote(
        unit=service.pricing_unit,
        quantity=change.quantity,
        precision=service.weight_precision,
        unit_price_cents=unit_price,
        min_charge_cents=service.min_charge_cents,
        min_quantity=service.min_quantity,
        extras_cents=int(garment.line_snapshot.get("extras_cents", 0)),
        express=order.express,
        express_surcharge_cents=service.express_surcharge_cents,
        same_day=False,
        same_day_surcharge_cents=None,
        special=False,
        special_surcharge_cents=None,
        discount_cents=0,
        discount_authorized=True,
        allow_zero_rate=service.allow_zero_rate,
        tax_category=service.tax_category,
        rate_bps=rate_bps,
        price_includes_tax=service.price_includes_tax,
    )
    garment.quantity = change.quantity
    garment.line_snapshot = asdict(priced)
    _retotal(db, order)
    order.version += 1
    _event(db, order, "quantity_changed", change.reason.strip(), actor_id)
    return order


def _retotal(db: Session, order: LaundryOrder) -> None:
    garments = list(db.scalars(select(LaundryGarment).where(LaundryGarment.order_id == order.id)))
    bags = list(db.scalars(select(LaundryBag).where(LaundryBag.order_id == order.id)))
    lines = [item.line_snapshot for item in garments] + [item.line_snapshot for item in bags]
    order.garment_count = sum(item.quantity for item in garments)
    order.subtotal_cents = sum(int(item["merchandise_cents"]) for item in lines)
    order.surcharge_cents = sum(int(item["surcharge_cents"]) for item in lines)
    order.tax_cents = sum(int(item["tax_cents"]) for item in lines)
    order.total_cents = sum(int(item["total_cents"]) for item in lines) - order.discount_cents
    if order.total_cents < 0 or order.total_cents < order.amount_paid_cents:
        raise ApiError(422, "deposit_too_large", "The new total cannot fall below the amount already paid.")
    order.balance_due_cents = order.total_cents - order.amount_paid_cents
    order.payment_status = _payment(order.amount_paid_cents, order.total_cents)
    order.pricing_snapshot = {"lines": lines, "rate_bps": sorted({int(item["rate_bps"]) for item in lines})}


def start_production(db: Session, order_id: uuid.UUID, *, actor_id: uuid.UUID | None, reason: str) -> LaundryOrder:
    order = get_order(db, order_id)
    if order.operational_status not in PRE_PRODUCTION:
        raise ApiError(409, "order_closed", "Production has already started or the order is closed.")
    if not reason.strip():
        raise ApiError(422, "reason_required", "Starting production needs a note.")
    order.operational_status = "IN_PRODUCTION"
    for garment in db.scalars(select(LaundryGarment).where(LaundryGarment.order_id == order.id)):
        garment.stage = "IN_PRODUCTION"
    order.version += 1
    _event(db, order, "production_started", reason.strip(), actor_id, "IN_PRODUCTION")
    return order


def cancel_order(
    db: Session, order_id: uuid.UUID, *, actor_id: uuid.UUID | None, reason: str, version: int
) -> LaundryOrder:
    order = get_order(db, order_id)
    if order.version != version:
        raise ApiError(409, "order_conflict", "This order was updated by someone else.")
    if order.operational_status == "CANCELLED":
        return order
    if not reason.strip():
        raise ApiError(422, "reason_required", "Cancellation needs a reason.")
    previous = order.operational_status
    order.operational_status = "CANCELLED"
    order.version += 1
    db.add(
        LaundryOrderEvent(
            order_id=order.id,
            kind="cancelled",
            from_status=previous,
            to_status="CANCELLED",
            reason=reason.strip(),
            actor_id=actor_id,
        )
    )
    return order


def _tag_by_code(db: Session, code: str) -> LaundryTag:
    tag = db.scalar(select(LaundryTag).where(LaundryTag.code == code.strip()))
    if tag is None:
        raise ApiError(404, "unknown_tag", "That tag is not in this business.")
    if tag.status == "replaced":
        raise ApiError(409, "replaced_tag", "That tag was replaced. Scan the new tag.")
    return tag


def scan_tag(
    db: Session, code: str, *, order_id: uuid.UUID | None, idempotency_key: str, device_id: uuid.UUID | None
) -> LaundryTagEvent:
    existing = db.scalar(select(LaundryTagEvent).where(LaundryTagEvent.idempotency_key == idempotency_key))
    if existing is not None:
        return existing
    tag = _tag_by_code(db, code)
    if order_id is not None and tag.order_id != order_id:
        raise ApiError(422, "wrong_order", "That tag belongs to a different order.")
    event = LaundryTagEvent(
        tag_id=tag.id,
        order_id=tag.order_id,
        kind="scan",
        idempotency_key=idempotency_key,
        device_id=device_id,
    )
    db.add(event)
    return event


def reprint_tag(db: Session, tag_id: uuid.UUID, *, idempotency_key: str, device_id: uuid.UUID | None) -> LaundryTag:
    tag = db.get(LaundryTag, tag_id)
    if tag is None:
        raise ApiError(404, "unknown_tag", "That tag is not in this business.")
    if tag.status == "replaced":
        raise ApiError(409, "replaced_tag", "That tag was replaced. Reprint the new tag.")
    if db.scalar(select(LaundryTagEvent).where(LaundryTagEvent.idempotency_key == idempotency_key)) is None:
        db.add(
            LaundryTagEvent(
                tag_id=tag.id,
                order_id=tag.order_id,
                kind="reprint",
                idempotency_key=idempotency_key,
                device_id=device_id,
            )
        )
    return tag


def replace_tag(db: Session, tag_id: uuid.UUID, *, idempotency_key: str, device_id: uuid.UUID | None) -> LaundryTag:
    existing = db.scalar(select(LaundryTagEvent).where(LaundryTagEvent.idempotency_key == idempotency_key))
    if existing is not None:
        return db.get(LaundryTag, existing.tag_id)
    tag = db.get(LaundryTag, tag_id)
    if tag is None:
        raise ApiError(404, "unknown_tag", "That tag is not in this business.")
    if tag.status == "replaced":
        raise ApiError(409, "replaced_tag", "That tag was already replaced.")
    order = get_order(db, tag.order_id)
    count = int(db.scalar(select(func.count()).select_from(LaundryTag).where(LaundryTag.order_id == order.id)) or 0)
    replacement = LaundryTag(
        code=f"{order.code}-{count + 1:02d}",
        order_id=order.id,
        garment_id=tag.garment_id,
        bag_id=tag.bag_id,
        store_id=tag.store_id,
        status="active",
        device_id=device_id,
    )
    tag.status = "replaced"
    db.add(replacement)
    db.flush()
    db.add(
        LaundryTagEvent(
            tag_id=replacement.id,
            order_id=order.id,
            kind="replace",
            idempotency_key=idempotency_key,
            note=tag.code,
            device_id=device_id,
        )
    )
    return replacement


def add_photo(
    db: Session, order_id: uuid.UUID, photo: PhotoIn, content: bytes, *, actor_id: uuid.UUID | None
) -> LaundryPhoto:
    order = get_order(db, order_id)
    if photo.garment_id is not None:
        garment = db.get(LaundryGarment, photo.garment_id)
        if garment is None or garment.order_id != order.id:
            raise ApiError(422, "wrong_order", "That garment is not on this order.")
    signatures = _ALLOWED_MIME.get(photo.mime)
    if signatures is None or not content.startswith(signatures[0]):
        raise ApiError(422, "invalid_photo", "Upload a JPEG, PNG, or WebP image.")
    if photo.mime == "image/webp" and content[8:12] != b"WEBP":
        raise ApiError(422, "invalid_photo", "Upload a JPEG, PNG, or WebP image.")
    if not content or len(content) > 5_000_000:
        raise ApiError(422, "invalid_photo", "The photo must be under 5 MB.")
    row = LaundryPhoto(
        order_id=order.id,
        garment_id=photo.garment_id,
        mime=photo.mime,
        byte_size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        content=content,
        uploaded_by_id=actor_id,
    )
    db.add(row)
    return row


def apply_laundry_order(db: Session, _settings: object, payload: dict[str, object], ctx: SyncContext) -> uuid.UUID:
    data = OrderIn.model_validate(payload)
    if data.express or data.deposit is not None:
        raise ApiError(422, "offline_unsafe", "Express capacity and deposits need the server.")
    device_id = ctx.device.id if ctx.device is not None else data.device_id
    order = create_order(
        db,
        data.model_copy(update={"device_id": device_id, "express": False, "deposit": None}),
        actor_id=None,
        discount_authorized=False,
    )
    return order.id


register_handler("laundry_order", apply_laundry_order)
