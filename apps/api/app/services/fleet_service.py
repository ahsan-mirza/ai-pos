"""Delivery scheduling and manual dispatch on the existing sales order.

A confirmed plan records the vehicle, the driver, and the capacity decision.
It does not invoice the order, take payment, or create a delivery note.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import exists, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import Principal
from app.core.errors import ApiError
from app.core.pagination import count_rows
from app.core.permissions import Permission
from app.models.attribute import ProductAttributeDefinition, ProductAttributeValue
from app.models.business_settings import BusinessSettings
from app.models.customer import Customer
from app.models.fleet import (
    DeliveryZone,
    DeliveryZoneSlot,
    DispatchAssignment,
    DispatchPlan,
    DriverProfile,
    FleetVehicle,
)
from app.models.product import Product
from app.models.sales_order import DeliveryNote, SalesOrder
from app.models.store import Store
from app.models.user import User
from app.schemas.fleet import (
    AssignIn,
    AssignmentOut,
    CapacityOut,
    ConfirmIn,
    DriverIn,
    DriverOut,
    DriverUpdate,
    FleetOrderRow,
    PlanIn,
    PlanOut,
    PlanUpdate,
    PolicyOut,
    ScheduleIn,
    SlotIn,
    SlotOut,
    VehicleIn,
    VehicleOut,
    VehicleUpdate,
    ZoneIn,
    ZoneOut,
    ZoneUpdate,
)
from app.services import audit
from app.services.business_time import reporting_timezone
from app.services.numbering import next_server_number
from app.services.sales_order_service import _event

_CODE = re.compile(r"[A-Z0-9-]{1,16}")
_SCHEDULABLE = ("DRAFT", "CONFIRMED", "PICKING", "PARTIALLY_DELIVERED")
_ASSIGNABLE = ("CONFIRMED", "PICKING", "PARTIALLY_DELIVERED")
_ACTIVE_PLANS = ("DRAFT", "CONFIRMED")
_WEIGHT = {"g": 1, "kg": 1000}
_VOLUME = {"cm3": 1, "ml": 1, "l": 1000, "m3": 1_000_000}
_MEASURE_CAP = 2_000_000_000
_WEIGHT_KEYS = {"weight", "shipping_weight"}
_VOLUME_KEYS = {"volume", "shipping_volume"}


@dataclass(frozen=True)
class Cargo:
    weight_grams: int
    volume_cm3: int
    weight_incomplete: bool
    volume_incomplete: bool


def judge_capacity(
    cargo: Cargo,
    vehicle_weight: int | None,
    vehicle_volume: int | None,
    *,
    policy: str = "block",
) -> CapacityOut:
    """Null vehicle capacity is unknown. It is not zero and it is not unlimited."""
    weight_over = (
        vehicle_weight is not None and not cargo.weight_incomplete and cargo.weight_grams > vehicle_weight
    )
    volume_over = (
        vehicle_volume is not None and not cargo.volume_incomplete and cargo.volume_cm3 > vehicle_volume
    )
    remaining_weight = (
        vehicle_weight - cargo.weight_grams
        if vehicle_weight is not None and not cargo.weight_incomplete
        else None
    )
    remaining_volume = (
        vehicle_volume - cargo.volume_cm3
        if vehicle_volume is not None and not cargo.volume_incomplete
        else None
    )
    blocked = (
        vehicle_weight is None
        or vehicle_volume is None
        or cargo.weight_incomplete
        or cargo.volume_incomplete
        or weight_over
        or volume_over
    )
    return CapacityOut(
        cargo_weight_grams=cargo.weight_grams,
        cargo_volume_cm3=cargo.volume_cm3,
        cargo_weight_incomplete=cargo.weight_incomplete,
        cargo_volume_incomplete=cargo.volume_incomplete,
        vehicle_weight_grams=vehicle_weight,
        vehicle_volume_cm3=vehicle_volume,
        remaining_weight_grams=remaining_weight,
        remaining_volume_cm3=remaining_volume,
        weight_over=weight_over,
        volume_over=volume_over,
        blocked=blocked,
        policy="block" if policy != "block" else policy,
    )


def _now() -> datetime:
    return datetime.now(UTC)


def _actor(principal: Principal) -> User:
    if principal.user is None:
        raise ApiError(403, "forbidden", "This action requires a signed-in user.")
    return principal.user


def _scope(principal: Principal, store_id: uuid.UUID) -> None:
    if principal.store_id is not None and principal.store_id != store_id:
        raise ApiError(404, "not_found", "Sales order was not found.")


def _order(db: Session, principal: Principal, order_id: uuid.UUID, *, lock: bool = False) -> SalesOrder:
    order = db.get(SalesOrder, order_id, with_for_update=lock)
    if order is None:
        raise ApiError(404, "not_found", "Sales order was not found.")
    _scope(principal, order.store_id)
    return order


def _code(value: str) -> str:
    cleaned = value.strip().upper()
    if _CODE.fullmatch(cleaned) is None:
        raise ApiError(422, "invalid_code", "Use letters, numbers, and dashes.")
    return cleaned


def _scaled(amount: Decimal, factor: int) -> int:
    scaled = (amount * factor).to_integral_value(rounding=ROUND_HALF_UP)
    if scaled < 0 or scaled > _MEASURE_CAP:
        raise ApiError(422, "invalid_measure", "That capacity is out of range.")
    return int(scaled)


def _grams(amount: Decimal | None, unit: str) -> int | None:
    if amount is None:
        return None
    factor = _WEIGHT.get(unit)
    if factor is None:
        raise ApiError(422, "invalid_unit", "Weight is in g or kg.")
    return _scaled(amount, factor)


def _cm3(amount: Decimal | None, unit: str) -> int | None:
    if amount is None:
        return None
    factor = _VOLUME.get(unit)
    if factor is None:
        raise ApiError(422, "invalid_unit", "Volume is in cm3, l, or m3.")
    return _scaled(amount, factor)


def _amount(stored: int | None, unit: str, table: dict[str, int]) -> str | None:
    if stored is None:
        return None
    factor = table.get(unit) or 1
    value = (Decimal(stored) / factor).normalize()
    return format(value, "f")


def _policy(db: Session) -> str:
    stored = db.scalar(select(BusinessSettings.fleet_capacity_policy).limit(1))
    return "block" if stored == "block" else "block"


def _clock(day: date, value: time, zone: ZoneInfo) -> None:
    local = datetime.combine(day, value.replace(tzinfo=None), tzinfo=zone)
    back = local.astimezone(UTC).astimezone(zone)
    if (back.hour, back.minute, back.second) != (value.hour, value.minute, value.second):
        raise ApiError(
            422,
            "invalid_window",
            "That time does not exist on this date in the business timezone.",
        )


def _window(start: time | None, end: time | None) -> None:
    if (start is None) != (end is None):
        raise ApiError(422, "invalid_window", "A delivery window needs a start and an end.")
    if start is not None and end is not None and start >= end:
        raise ApiError(422, "invalid_window", "The window ends at or before it starts.")


def _save(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "duplicate", "That code or driver is already in use.") from None


def read_policy(db: Session) -> PolicyOut:
    return PolicyOut(policy="block", timezone=str(reporting_timezone(db)))


def set_policy(db: Session, principal: Principal, policy: str) -> PolicyOut:
    if principal.user is None or principal.store_id is not None:
        raise ApiError(403, "forbidden", "Only a business-wide administrator can change the capacity policy.")
    if policy != "block":
        raise ApiError(
            422,
            "invalid_policy",
            "The only capacity policy is block. Missing weight or volume is never zero or unlimited.",
        )
    row = db.scalar(select(BusinessSettings).limit(1))
    if row is None:
        raise ApiError(404, "not_found", "Business settings were not found.")
    row.fleet_capacity_policy = "block"
    _save(db)
    return read_policy(db)


def _measures(db: Session, product_ids: set[uuid.UUID]) -> dict[uuid.UUID, tuple[int | None, int | None, bool]]:
    if not product_ids:
        return {}
    products = {row.id: row for row in db.scalars(select(Product).where(Product.id.in_(product_ids)))}
    found: dict[uuid.UUID, tuple[int | None, int | None, bool]] = {
        product_id: (None, None, bool(product.sold_by_weight)) for product_id, product in products.items()
    }
    rows = db.execute(
        select(ProductAttributeValue, ProductAttributeDefinition)
        .join(ProductAttributeDefinition, ProductAttributeDefinition.id == ProductAttributeValue.definition_id)
        .where(ProductAttributeValue.product_id.in_(product_ids))
    ).all()
    for value, definition in rows:
        if value.number_value is None:
            continue
        key = definition.key.strip().lower()
        unit = (value.unit or definition.unit or "").strip().lower()
        weight, volume, weighed = found.get(value.product_id, (None, None, False))
        if key in _WEIGHT_KEYS:
            factor = _WEIGHT.get(unit)
            weight = _scaled(value.number_value, factor) if factor is not None else None
        elif key in _VOLUME_KEYS:
            factor = _VOLUME.get(unit)
            volume = _scaled(value.number_value, factor) if factor is not None else None
        found[value.product_id] = (weight, volume, weighed)
    return found


def cargo_for(db: Session, order: SalesOrder) -> Cargo:
    measures = _measures(db, {line.product_id for line in order.lines})
    return _cargo(order, measures)


def _cargo(order: SalesOrder, measures: dict[uuid.UUID, tuple[int | None, int | None, bool]]) -> Cargo:
    weight = 0
    volume = 0
    weight_missing = False
    volume_missing = False
    live = False
    for line in order.lines:
        qty = line.outstanding
        if qty <= 0:
            continue
        live = True
        per_weight, per_volume, weighed = measures.get(line.product_id, (None, None, False))
        if weighed:
            gained = qty if qty <= _MEASURE_CAP else None
            if gained is None:
                weight_missing = True
            else:
                weight += gained
        elif per_weight is None or per_weight * qty > _MEASURE_CAP:
            weight_missing = True
        else:
            weight += per_weight * qty
        if weighed or per_volume is None or per_volume * qty > _MEASURE_CAP:
            volume_missing = True
        else:
            volume += per_volume * qty
    if not live:
        return Cargo(0, 0, False, False)
    return Cargo(weight, volume, weight_missing, volume_missing)


def _slots(db: Session, zone_id: uuid.UUID) -> list[DeliveryZoneSlot]:
    return list(
        db.scalars(
            select(DeliveryZoneSlot)
            .where(DeliveryZoneSlot.zone_id == zone_id)
            .order_by(DeliveryZoneSlot.weekday, DeliveryZoneSlot.start_time)
        ).all()
    )


def _fit_slot(db: Session, order: SalesOrder) -> None:
    if order.delivery_zone_id is None or order.promised_on is None:
        return
    slots = [slot for slot in _slots(db, order.delivery_zone_id) if slot.is_active]
    if not slots:
        return
    if order.window_start is None or order.window_end is None:
        raise ApiError(422, "window_required", "This zone has time slots, so the delivery needs a window.")
    day = [slot for slot in slots if slot.weekday == order.promised_on.weekday()]
    fits = any(
        slot.start_time <= order.window_start and order.window_end <= slot.end_time for slot in day
    )
    if not fits:
        raise ApiError(422, "outside_window", "That window is outside this zone's time slots.")


def _audit(db: Session, principal: Principal, order: SalesOrder, action: str, values: dict[str, object]) -> None:
    actor = _actor(principal)
    audit.record(
        db,
        action_type="UPDATE",
        action=action,
        target_entity="SalesOrder",
        target_entity_id=order.id,
        store_id=order.store_id,
        user_id=actor.id,
        new_values=values,
    )


def schedule_order(db: Session, principal: Principal, order_id: uuid.UUID, data: ScheduleIn) -> SalesOrder:
    order = _order(db, principal, order_id, lock=True)
    if order.status not in _SCHEDULABLE:
        raise ApiError(422, "not_schedulable", "This order can no longer be scheduled.")
    before = (
        order.scheduling_status,
        order.promised_on,
        order.window_start,
        order.window_end,
        order.delivery_zone_id,
        order.delivery_address,
        order.delivery_instructions,
        order.requested_date,
    )
    sent = data.model_fields_set
    if "requested_date" in sent:
        order.requested_date = data.requested_date
    if "delivery_address" in sent:
        order.delivery_address = (data.delivery_address or "").strip() or None
    if "delivery_instructions" in sent:
        order.delivery_instructions = (data.delivery_instructions or "").strip()
    if "promised_on" in sent:
        if data.promised_on is None and order.scheduling_status == "SCHEDULED":
            raise ApiError(422, "promised_required", "Cancel the schedule to clear the promised date.")
        order.promised_on = data.promised_on
    if "window_start" in sent or "window_end" in sent:
        order.window_start = data.window_start if "window_start" in sent else order.window_start
        order.window_end = data.window_end if "window_end" in sent else order.window_end
    _window(order.window_start, order.window_end)
    if "delivery_zone_id" in sent and data.delivery_zone_id != order.delivery_zone_id:
        if data.delivery_zone_id is None:
            order.delivery_zone_id = None
        else:
            zone = db.get(DeliveryZone, data.delivery_zone_id)
            if zone is None or zone.store_id != order.store_id:
                raise ApiError(404, "not_found", "Delivery zone was not found.")
            if not zone.is_active:
                raise ApiError(422, "zone_inactive", "That delivery zone is inactive.")
            order.delivery_zone_id = zone.id
    if order.promised_on is not None:
        zone = reporting_timezone(db)
        if order.window_start is not None and order.window_end is not None:
            _clock(order.promised_on, order.window_start, zone)
            _clock(order.promised_on, order.window_end, zone)
        _fit_slot(db, order)
        if _on_other_plan(db, order.id, None) and _plan_date(db, order.id) not in (None, order.promised_on):
            raise ApiError(409, "plan_date", "Remove this order from its dispatch plan before changing the date.")
        order.scheduling_status = "SCHEDULED"
    elif order.scheduling_status != "CANCELLED":
        order.scheduling_status = "UNSCHEDULED"
    after = (
        order.scheduling_status,
        order.promised_on,
        order.window_start,
        order.window_end,
        order.delivery_zone_id,
        order.delivery_address,
        order.delivery_instructions,
        order.requested_date,
    )
    if after != before and order.scheduling_status == "SCHEDULED":
        kind = "rescheduled" if before[0] == "SCHEDULED" else "scheduled"
        _event(db, order, kind, f"Delivery promised for {order.promised_on}.", _actor(principal).id)
        _audit(
            db,
            principal,
            order,
            "sales_order.reschedule" if kind == "rescheduled" else "sales_order.schedule",
            {"promised_on": str(order.promised_on) if order.promised_on else None},
        )
    db.flush()
    _save(db)
    return order


def cancel_schedule(db: Session, principal: Principal, order_id: uuid.UUID) -> SalesOrder:
    order = _order(db, principal, order_id, lock=True)
    if order.scheduling_status != "SCHEDULED":
        raise ApiError(422, "not_scheduled", "This order has no promised delivery to cancel.")
    if _on_confirmed_plan(db, order.id):
        raise ApiError(409, "on_dispatch_plan", "Remove this order from its confirmed dispatch plan first.")
    _release_drafts(db, principal, order)
    order.scheduling_status = "CANCELLED"
    _event(db, order, "schedule_cancelled", "The promised delivery was cancelled.", _actor(principal).id)
    _audit(db, principal, order, "sales_order.schedule_cancel", {"scheduling_status": "CANCELLED"})
    db.flush()
    _save(db)
    return order


def _plan_date(db: Session, order_id: uuid.UUID) -> date | None:
    return db.scalar(
        select(DispatchPlan.service_date)
        .join(DispatchAssignment, DispatchAssignment.plan_id == DispatchPlan.id)
        .where(DispatchAssignment.order_id == order_id, DispatchPlan.status.in_(_ACTIVE_PLANS))
        .limit(1)
    )


def _on_other_plan(db: Session, order_id: uuid.UUID, plan_id: uuid.UUID | None) -> bool:
    statement = (
        select(DispatchAssignment.id)
        .join(DispatchPlan, DispatchPlan.id == DispatchAssignment.plan_id)
        .where(DispatchAssignment.order_id == order_id, DispatchPlan.status.in_(_ACTIVE_PLANS))
    )
    if plan_id is not None:
        statement = statement.where(DispatchAssignment.plan_id != plan_id)
    return db.scalar(statement.limit(1)) is not None


def _on_confirmed_plan(db: Session, order_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(DispatchAssignment.id)
            .join(DispatchPlan, DispatchPlan.id == DispatchAssignment.plan_id)
            .where(DispatchAssignment.order_id == order_id, DispatchPlan.status == "CONFIRMED")
            .limit(1)
        )
        is not None
    )


def _release_drafts(db: Session, principal: Principal, order: SalesOrder) -> None:
    rows = db.execute(
        select(DispatchAssignment, DispatchPlan)
        .join(DispatchPlan, DispatchPlan.id == DispatchAssignment.plan_id)
        .where(DispatchAssignment.order_id == order.id, DispatchPlan.status == "DRAFT")
    ).all()
    for assignment, plan in rows:
        db.delete(assignment)
        _event(db, order, "plan_removed", f"Removed from dispatch plan {plan.number}.", _actor(principal).id)


def _left(db: Session, order_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(DeliveryNote.id)
            .where(DeliveryNote.order_id == order_id, DeliveryNote.status.in_(("DISPATCHED", "DELIVERED")))
            .limit(1)
        )
        is not None
    )


def _zone_out(db: Session, zone: DeliveryZone) -> ZoneOut:
    return ZoneOut(
        id=zone.id,
        store_id=zone.store_id,
        code=zone.code,
        name=zone.name,
        description=zone.description,
        is_active=zone.is_active,
        fee_cents=zone.fee_cents,
        slots=[
            SlotOut(
                id=slot.id,
                weekday=slot.weekday,
                start_time=slot.start_time,
                end_time=slot.end_time,
                is_active=slot.is_active,
            )
            for slot in _slots(db, zone.id)
        ],
    )


def list_zones(db: Session, principal: Principal, store_id: uuid.UUID | None) -> list[ZoneOut]:
    scope = principal.store_id or store_id
    statement = select(DeliveryZone).order_by(DeliveryZone.name)
    if scope is not None:
        statement = statement.where(DeliveryZone.store_id == scope)
    return [_zone_out(db, zone) for zone in db.scalars(statement).all()]


def create_zone(db: Session, principal: Principal, data: ZoneIn) -> ZoneOut:
    _scope(principal, data.store_id)
    if db.get(Store, data.store_id) is None:
        raise ApiError(404, "not_found", "Store was not found.")
    zone = DeliveryZone(
        store_id=data.store_id,
        code=_code(data.code),
        name=data.name.strip(),
        description=data.description.strip(),
        is_active=data.is_active,
        fee_cents=data.fee_cents,
    )
    db.add(zone)
    db.flush()
    payload = _zone_out(db, zone)
    _save(db)
    return payload


def update_zone(db: Session, principal: Principal, zone_id: uuid.UUID, data: ZoneUpdate) -> ZoneOut:
    zone = db.get(DeliveryZone, zone_id)
    if zone is None:
        raise ApiError(404, "not_found", "Delivery zone was not found.")
    _scope(principal, zone.store_id)
    if data.name is not None:
        zone.name = data.name.strip()
    if data.description is not None:
        zone.description = data.description.strip()
    if data.is_active is not None:
        zone.is_active = data.is_active
    if data.clear_fee:
        zone.fee_cents = None
    elif "fee_cents" in data.model_fields_set:
        zone.fee_cents = data.fee_cents
    db.flush()
    payload = _zone_out(db, zone)
    _save(db)
    return payload


def add_slot(db: Session, principal: Principal, zone_id: uuid.UUID, data: SlotIn) -> ZoneOut:
    zone = db.get(DeliveryZone, zone_id)
    if zone is None:
        raise ApiError(404, "not_found", "Delivery zone was not found.")
    _scope(principal, zone.store_id)
    _window(data.start_time, data.end_time)
    db.add(
        DeliveryZoneSlot(
            zone_id=zone.id,
            weekday=data.weekday,
            start_time=data.start_time,
            end_time=data.end_time,
            is_active=data.is_active,
        )
    )
    db.flush()
    payload = _zone_out(db, zone)
    _save(db)
    return payload


def delete_slot(db: Session, principal: Principal, zone_id: uuid.UUID, slot_id: uuid.UUID) -> ZoneOut:
    zone = db.get(DeliveryZone, zone_id)
    slot = db.get(DeliveryZoneSlot, slot_id)
    if zone is None or slot is None or slot.zone_id != zone.id:
        raise ApiError(404, "not_found", "Delivery zone was not found.")
    _scope(principal, zone.store_id)
    db.delete(slot)
    db.flush()
    payload = _zone_out(db, zone)
    _save(db)
    return payload


def _vehicle_out(row: FleetVehicle) -> VehicleOut:
    return VehicleOut(
        id=row.id,
        store_id=row.store_id,
        code=row.code,
        registration=row.registration,
        vehicle_type=row.vehicle_type,
        max_weight_grams=row.max_weight_grams,
        weight_unit=row.weight_unit,
        weight_amount=_amount(row.max_weight_grams, row.weight_unit, _WEIGHT),
        max_volume_cm3=row.max_volume_cm3,
        volume_unit=row.volume_unit,
        volume_amount=_amount(row.max_volume_cm3, row.volume_unit, _VOLUME),
        availability=row.availability,
        maintenance_status=row.maintenance_status,
        is_active=row.is_active,
        notes=row.notes,
    )


def list_vehicles(db: Session, principal: Principal, store_id: uuid.UUID | None) -> list[VehicleOut]:
    scope = principal.store_id or store_id
    statement = select(FleetVehicle).order_by(FleetVehicle.code)
    if scope is not None:
        statement = statement.where(FleetVehicle.store_id == scope)
    return [_vehicle_out(row) for row in db.scalars(statement).all()]


def create_vehicle(db: Session, principal: Principal, data: VehicleIn) -> VehicleOut:
    _scope(principal, data.store_id)
    if db.get(Store, data.store_id) is None:
        raise ApiError(404, "not_found", "Store was not found.")
    row = FleetVehicle(
        store_id=data.store_id,
        code=_code(data.code),
        registration=data.registration.strip().upper(),
        vehicle_type=data.vehicle_type.strip(),
        max_weight_grams=_grams(data.weight_amount, data.weight_unit),
        weight_unit=data.weight_unit,
        max_volume_cm3=_cm3(data.volume_amount, data.volume_unit),
        volume_unit=data.volume_unit,
        availability=data.availability,
        maintenance_status=data.maintenance_status,
        is_active=data.is_active,
        notes=data.notes.strip(),
    )
    db.add(row)
    db.flush()
    payload = _vehicle_out(row)
    _save(db)
    return payload


def update_vehicle(db: Session, principal: Principal, vehicle_id: uuid.UUID, data: VehicleUpdate) -> VehicleOut:
    row = db.get(FleetVehicle, vehicle_id)
    if row is None:
        raise ApiError(404, "not_found", "Vehicle was not found.")
    _scope(principal, row.store_id)
    if data.registration is not None:
        row.registration = data.registration.strip().upper()
    if data.vehicle_type is not None:
        row.vehicle_type = data.vehicle_type.strip()
    if data.availability is not None:
        row.availability = data.availability
    if data.maintenance_status is not None:
        row.maintenance_status = data.maintenance_status
    if data.is_active is not None:
        row.is_active = data.is_active
    if data.notes is not None:
        row.notes = data.notes.strip()
    unit = data.weight_unit or row.weight_unit
    if data.clear_weight:
        row.max_weight_grams = None
    elif "weight_amount" in data.model_fields_set:
        row.max_weight_grams = _grams(data.weight_amount, unit)
    if data.weight_unit is not None:
        row.weight_unit = data.weight_unit
    volume_unit = data.volume_unit or row.volume_unit
    if data.clear_volume:
        row.max_volume_cm3 = None
    elif "volume_amount" in data.model_fields_set:
        row.max_volume_cm3 = _cm3(data.volume_amount, volume_unit)
    if data.volume_unit is not None:
        row.volume_unit = data.volume_unit
    db.flush()
    payload = _vehicle_out(row)
    _save(db)
    return payload


def _sees_license(principal: Principal) -> bool:
    return principal.has(Permission.STAFF_MANAGE) or principal.has(Permission.SALES_DISPATCH_OVERRIDE)


def _driver_out(principal: Principal, row: DriverProfile, user: User) -> DriverOut:
    reveal = _sees_license(principal)
    return DriverOut(
        id=row.id,
        user_id=row.user_id,
        name=user.full_name,
        store_id=row.store_id,
        phone=row.phone,
        license_number=row.license_number if reveal and row.license_number else None,
        license_on_file=bool(row.license_number),
        license_expiry=row.license_expiry,
        availability=row.availability,
        is_active=row.is_active,
    )


def list_drivers(db: Session, principal: Principal, store_id: uuid.UUID | None) -> list[DriverOut]:
    scope = principal.store_id or store_id
    statement = select(DriverProfile, User).join(User, User.id == DriverProfile.user_id).order_by(User.full_name)
    if scope is not None:
        statement = statement.where(DriverProfile.store_id == scope)
    return [_driver_out(principal, row, user) for row, user in db.execute(statement).all()]


def create_driver(db: Session, principal: Principal, data: DriverIn) -> DriverOut:
    _scope(principal, data.store_id)
    user = db.get(User, data.user_id)
    if user is None or db.get(Store, data.store_id) is None:
        raise ApiError(404, "not_found", "User or store was not found.")
    if not user.is_active:
        raise ApiError(422, "driver_inactive", "That user is inactive.")
    if user.store_id is not None and user.store_id != data.store_id:
        raise ApiError(422, "driver_branch", "That user belongs to another branch.")
    row = DriverProfile(
        user_id=user.id,
        store_id=data.store_id,
        phone=data.phone.strip(),
        license_number=data.license_number.strip(),
        license_expiry=data.license_expiry,
        availability=data.availability,
        is_active=data.is_active,
    )
    db.add(row)
    db.flush()
    payload = _driver_out(principal, row, user)
    _save(db)
    return payload


def update_driver(db: Session, principal: Principal, driver_id: uuid.UUID, data: DriverUpdate) -> DriverOut:
    row = db.get(DriverProfile, driver_id)
    if row is None:
        raise ApiError(404, "not_found", "Driver was not found.")
    _scope(principal, row.store_id)
    user = db.get(User, row.user_id)
    if user is None:
        raise ApiError(404, "not_found", "Driver was not found.")
    if data.phone is not None:
        row.phone = data.phone.strip()
    if data.license_number is not None and _sees_license(principal):
        row.license_number = data.license_number.strip()
    elif data.license_number is not None:
        raise ApiError(403, "forbidden", "You cannot change a driver's license.")
    if data.clear_license_expiry:
        row.license_expiry = None
    elif "license_expiry" in data.model_fields_set:
        row.license_expiry = data.license_expiry
    if data.availability is not None:
        row.availability = data.availability
    if data.is_active is not None:
        row.is_active = data.is_active
    db.flush()
    payload = _driver_out(principal, row, user)
    _save(db)
    return payload


def _assignments(db: Session, plan_id: uuid.UUID) -> list[tuple[DispatchAssignment, SalesOrder, str]]:
    rows = db.execute(
        select(DispatchAssignment, SalesOrder, Customer.name)
        .join(SalesOrder, SalesOrder.id == DispatchAssignment.order_id)
        .join(Customer, Customer.id == SalesOrder.customer_id)
        .where(DispatchAssignment.plan_id == plan_id)
        .order_by(DispatchAssignment.position)
    ).all()
    return [(assignment, order, name) for assignment, order, name in rows]


def _plan_capacity(db: Session, plan: DispatchPlan) -> tuple[CapacityOut, list[AssignmentOut]]:
    vehicle = db.get(FleetVehicle, plan.vehicle_id)
    rows = _assignments(db, plan.id)
    measures = _measures(db, {line.product_id for _, order, _ in rows for line in order.lines})
    weight = 0
    volume = 0
    weight_missing = False
    volume_missing = False
    assigned: list[AssignmentOut] = []
    for assignment, order, name in rows:
        cargo = _cargo(order, measures)
        weight += cargo.weight_grams
        volume += cargo.volume_cm3
        weight_missing = weight_missing or cargo.weight_incomplete
        volume_missing = volume_missing or cargo.volume_incomplete
        assigned.append(
            AssignmentOut(
                order_id=order.id,
                order_number=order.number,
                customer_name=name,
                position=assignment.position,
                cargo_weight_grams=cargo.weight_grams,
                cargo_volume_cm3=cargo.volume_cm3,
                cargo_weight_incomplete=cargo.weight_incomplete,
                cargo_volume_incomplete=cargo.volume_incomplete,
            )
        )
    cargo = Cargo(weight, volume, weight_missing, volume_missing)
    capacity = judge_capacity(
        cargo,
        vehicle.max_weight_grams if vehicle else None,
        vehicle.max_volume_cm3 if vehicle else None,
        policy=_policy(db),
    )
    return capacity, assigned


def _plan_out(db: Session, plan: DispatchPlan, principal: Principal) -> PlanOut:
    _scope(principal, plan.store_id)
    vehicle = db.get(FleetVehicle, plan.vehicle_id)
    driver = db.get(User, plan.driver_user_id)
    capacity, assigned = _plan_capacity(db, plan)
    return PlanOut(
        id=plan.id,
        number=plan.number,
        store_id=plan.store_id,
        service_date=plan.service_date,
        vehicle_id=plan.vehicle_id,
        vehicle_code=vehicle.code if vehicle else "",
        driver_user_id=plan.driver_user_id,
        driver_name=driver.full_name if driver else "Driver",
        status=plan.status,
        notes=plan.notes,
        capacity_override_by_id=plan.capacity_override_by_id,
        confirmed_at=plan.confirmed_at,
        timezone=str(reporting_timezone(db)),
        assignments=assigned,
        capacity=capacity,
    )


def list_plans(
    db: Session,
    principal: Principal,
    *,
    store_id: uuid.UUID | None,
    service_date: date | None,
    status: str | None,
) -> list[PlanOut]:
    scope = principal.store_id or store_id
    statement = select(DispatchPlan).order_by(DispatchPlan.service_date.desc(), DispatchPlan.number)
    if scope is not None:
        statement = statement.where(DispatchPlan.store_id == scope)
    if service_date is not None:
        statement = statement.where(DispatchPlan.service_date == service_date)
    if status:
        statement = statement.where(DispatchPlan.status == status)
    return [_plan_out(db, plan, principal) for plan in db.scalars(statement.limit(100)).all()]


def get_plan(db: Session, principal: Principal, plan_id: uuid.UUID) -> PlanOut:
    plan = db.get(DispatchPlan, plan_id)
    if plan is None:
        raise ApiError(404, "not_found", "Dispatch plan was not found.")
    return _plan_out(db, plan, principal)


def _vehicle(db: Session, principal: Principal, vehicle_id: uuid.UUID, store_id: uuid.UUID) -> FleetVehicle:
    row = db.get(FleetVehicle, vehicle_id)
    if row is None or row.store_id != store_id:
        raise ApiError(404, "not_found", "Vehicle was not found.")
    _scope(principal, row.store_id)
    return row


def _driver(db: Session, principal: Principal, user_id: uuid.UUID, store_id: uuid.UUID) -> DriverProfile:
    row = db.scalar(select(DriverProfile).where(DriverProfile.user_id == user_id))
    if row is None or row.store_id != store_id:
        raise ApiError(404, "not_found", "Driver was not found.")
    _scope(principal, row.store_id)
    return row


def _ready(vehicle: FleetVehicle, driver: DriverProfile, user: User | None, service_date: date) -> None:
    if not vehicle.is_active or vehicle.availability != "AVAILABLE" or vehicle.maintenance_status == "IN_SHOP":
        raise ApiError(409, "vehicle_unavailable", "That vehicle is not available.")
    if user is None or not user.is_active or not driver.is_active or driver.availability != "AVAILABLE":
        raise ApiError(409, "driver_unavailable", "That driver is not available.")
    if driver.license_expiry is not None and driver.license_expiry < service_date:
        raise ApiError(409, "license_expired", "That driver's license expires before the delivery date.")


def _crew_free(db: Session, plan: DispatchPlan) -> None:
    clash = db.scalar(
        select(DispatchPlan.id)
        .where(
            DispatchPlan.id != plan.id,
            DispatchPlan.status == "CONFIRMED",
            DispatchPlan.service_date == plan.service_date,
            or_(
                DispatchPlan.vehicle_id == plan.vehicle_id,
                DispatchPlan.driver_user_id == plan.driver_user_id,
            ),
        )
        .limit(1)
    )
    if clash is not None:
        raise ApiError(409, "crew_booked", "That vehicle or driver is already confirmed for this date.")


def _take(db: Session, principal: Principal, plan: DispatchPlan, order_id: uuid.UUID) -> SalesOrder:
    if plan.status not in _ACTIVE_PLANS:
        raise ApiError(409, "plan_closed", "This dispatch plan is closed.")
    order = _order(db, principal, order_id, lock=True)
    if order.store_id != plan.store_id:
        raise ApiError(422, "branch_mismatch", "That order belongs to another branch.")
    if order.status not in _ASSIGNABLE or order.scheduling_status != "SCHEDULED":
        raise ApiError(422, "not_scheduled", "Only a promised open order can go on a dispatch plan.")
    if order.promised_on != plan.service_date:
        raise ApiError(422, "date_mismatch", "The promised date does not match this dispatch plan.")
    if _left(db, order.id):
        raise ApiError(409, "already_dispatched", "This order already has a delivery on the way.")
    if all(line.outstanding <= 0 for line in order.lines):
        raise ApiError(422, "nothing_to_deliver", "This order has nothing left to deliver.")
    if _on_other_plan(db, order.id, plan.id):
        raise ApiError(409, "already_assigned", "This delivery is already on another dispatch plan.")
    return order


def create_plan(db: Session, principal: Principal, data: PlanIn) -> PlanOut:
    _scope(principal, data.store_id)
    if db.get(Store, data.store_id) is None:
        raise ApiError(404, "not_found", "Store was not found.")
    vehicle = _vehicle(db, principal, data.vehicle_id, data.store_id)
    driver = _driver(db, principal, data.driver_user_id, data.store_id)
    plan = DispatchPlan(
        number=next_server_number(db, data.store_id, "DSP"),
        store_id=data.store_id,
        service_date=data.service_date,
        vehicle_id=vehicle.id,
        driver_user_id=driver.user_id,
        status="DRAFT",
        notes=data.notes.strip(),
    )
    db.add(plan)
    db.flush()
    for position, order_id in enumerate(dict.fromkeys(data.order_ids)):
        order = _take(db, principal, plan, order_id)
        db.add(DispatchAssignment(plan_id=plan.id, order_id=order.id, position=position))
        _event(db, order, "plan_assigned", f"Added to dispatch plan {plan.number}.", _actor(principal).id)
    db.flush()
    payload = _plan_out(db, plan, principal)
    _save(db)
    return payload


def update_plan(db: Session, principal: Principal, plan_id: uuid.UUID, data: PlanUpdate) -> PlanOut:
    plan = db.get(DispatchPlan, plan_id, with_for_update=True)
    if plan is None:
        raise ApiError(404, "not_found", "Dispatch plan was not found.")
    _scope(principal, plan.store_id)
    if plan.status != "DRAFT":
        raise ApiError(409, "plan_closed", "Only a draft dispatch plan can be edited.")
    if data.vehicle_id is not None:
        plan.vehicle_id = _vehicle(db, principal, data.vehicle_id, plan.store_id).id
    if data.driver_user_id is not None:
        plan.driver_user_id = _driver(db, principal, data.driver_user_id, plan.store_id).user_id
    if data.notes is not None:
        plan.notes = data.notes.strip()
    db.flush()
    payload = _plan_out(db, plan, principal)
    _save(db)
    return payload


def add_order(db: Session, principal: Principal, plan_id: uuid.UUID, data: AssignIn) -> PlanOut:
    plan = db.get(DispatchPlan, plan_id, with_for_update=True)
    if plan is None:
        raise ApiError(404, "not_found", "Dispatch plan was not found.")
    order = _take(db, principal, plan, data.order_id)
    existing = db.scalar(
        select(DispatchAssignment.id).where(
            DispatchAssignment.plan_id == plan.id, DispatchAssignment.order_id == order.id
        )
    )
    if existing is not None:
        raise ApiError(409, "already_assigned", "This delivery is already on this dispatch plan.")
    position = db.scalar(
        select(DispatchAssignment.position)
        .where(DispatchAssignment.plan_id == plan.id)
        .order_by(DispatchAssignment.position.desc())
        .limit(1)
    )
    db.add(DispatchAssignment(plan_id=plan.id, order_id=order.id, position=(position or 0) + 1))
    _event(db, order, "plan_assigned", f"Added to dispatch plan {plan.number}.", _actor(principal).id)
    _audit(db, principal, order, "dispatch_plan.assign", {"plan": plan.number})
    db.flush()
    payload = _plan_out(db, plan, principal)
    _save(db)
    return payload


def remove_order(db: Session, principal: Principal, plan_id: uuid.UUID, order_id: uuid.UUID) -> PlanOut:
    plan = db.get(DispatchPlan, plan_id, with_for_update=True)
    if plan is None:
        raise ApiError(404, "not_found", "Dispatch plan was not found.")
    _scope(principal, plan.store_id)
    if plan.status not in _ACTIVE_PLANS:
        raise ApiError(409, "plan_closed", "This dispatch plan is closed.")
    assignment = db.scalar(
        select(DispatchAssignment).where(
            DispatchAssignment.plan_id == plan.id, DispatchAssignment.order_id == order_id
        )
    )
    if assignment is None:
        raise ApiError(404, "not_found", "That order is not on this dispatch plan.")
    if _left(db, order_id):
        raise ApiError(409, "already_dispatched", "This order already has a delivery on the way.")
    order = _order(db, principal, order_id)
    db.delete(assignment)
    _event(db, order, "plan_removed", f"Removed from dispatch plan {plan.number}.", _actor(principal).id)
    _audit(db, principal, order, "dispatch_plan.remove", {"plan": plan.number})
    db.flush()
    payload = _plan_out(db, plan, principal)
    _save(db)
    return payload


def confirm_plan(db: Session, principal: Principal, plan_id: uuid.UUID, data: ConfirmIn) -> PlanOut:
    plan = db.get(DispatchPlan, plan_id, with_for_update=True)
    if plan is None:
        raise ApiError(404, "not_found", "Dispatch plan was not found.")
    _scope(principal, plan.store_id)
    if plan.status != "DRAFT":
        raise ApiError(409, "already_confirmed", "This dispatch plan is no longer a draft.")
    rows = _assignments(db, plan.id)
    if not rows:
        raise ApiError(422, "empty_plan", "Add at least one order before confirming.")
    vehicle = _vehicle(db, principal, plan.vehicle_id, plan.store_id)
    driver = _driver(db, principal, plan.driver_user_id, plan.store_id)
    _ready(vehicle, driver, db.get(User, driver.user_id), plan.service_date)
    _crew_free(db, plan)
    for _, order, _ in rows:
        _take(db, principal, plan, order.id)
    capacity, _assigned = _plan_capacity(db, plan)
    if capacity.blocked:
        if not data.override:
            raise ApiError(
                409,
                "capacity_blocked",
                "This plan is over capacity or missing weight or volume. It cannot be confirmed.",
                details={
                    "cargo_weight_incomplete": capacity.cargo_weight_incomplete,
                    "cargo_volume_incomplete": capacity.cargo_volume_incomplete,
                    "weight_over": capacity.weight_over,
                    "volume_over": capacity.volume_over,
                    "vehicle_weight_known": capacity.vehicle_weight_grams is not None,
                    "vehicle_volume_known": capacity.vehicle_volume_cm3 is not None,
                },
            )
        if not principal.has(Permission.SALES_DISPATCH_OVERRIDE):
            raise ApiError(403, "forbidden", "You cannot override capacity.")
        reason = (data.reason or "").strip()
        if len(reason) < 3:
            raise ApiError(422, "reason_required", "An override needs a reason of at least 3 characters.")
        plan.capacity_override_by_id = _actor(principal).id
        for _, order, _ in rows:
            _event(db, order, "capacity_override", reason[:240], _actor(principal).id)
            _audit(db, principal, order, "dispatch_plan.capacity_override", {"reason": reason, "plan": plan.number})
    plan.status = "CONFIRMED"
    plan.confirmed_at = _now()
    for _, order, _ in rows:
        _event(db, order, "plan_confirmed", f"Dispatch plan {plan.number} confirmed.", _actor(principal).id)
        _audit(db, principal, order, "dispatch_plan.confirm", {"plan": plan.number})
    db.flush()
    payload = _plan_out(db, plan, principal)
    _save(db)
    return payload


def cancel_plan(db: Session, principal: Principal, plan_id: uuid.UUID) -> PlanOut:
    plan = db.get(DispatchPlan, plan_id, with_for_update=True)
    if plan is None:
        raise ApiError(404, "not_found", "Dispatch plan was not found.")
    _scope(principal, plan.store_id)
    if plan.status == "CANCELLED":
        raise ApiError(409, "plan_closed", "This dispatch plan is already cancelled.")
    rows = _assignments(db, plan.id)
    for _, order, _ in rows:
        if _left(db, order.id):
            raise ApiError(409, "already_dispatched", "A delivery on this plan is already on the way.")
    plan.status = "CANCELLED"
    for _, order, _ in rows:
        _event(db, order, "plan_removed", f"Dispatch plan {plan.number} was cancelled.", _actor(principal).id)
    db.flush()
    payload = _plan_out(db, plan, principal)
    _save(db)
    return payload


def _active_plan_exists():
    return exists(
        select(DispatchAssignment.id)
        .join(DispatchPlan, DispatchPlan.id == DispatchAssignment.plan_id)
        .where(
            DispatchAssignment.order_id == SalesOrder.id,
            DispatchPlan.status.in_(_ACTIVE_PLANS),
        )
    )


def _note_exists(status: str):
    return exists(
        select(DeliveryNote.id).where(DeliveryNote.order_id == SalesOrder.id, DeliveryNote.status == status)
    )


def list_board(
    db: Session,
    principal: Principal,
    *,
    view: str,
    store_id: uuid.UUID | None,
    promised_on: date | None,
    zone_id: uuid.UUID | None,
    offset: int,
    limit: int,
) -> tuple[list[FleetOrderRow], int]:
    scope = principal.store_id or store_id
    statement = (
        select(SalesOrder, Customer.name, DeliveryZone.name)
        .join(Customer, Customer.id == SalesOrder.customer_id)
        .outerjoin(DeliveryZone, DeliveryZone.id == SalesOrder.delivery_zone_id)
    )
    if scope is not None:
        statement = statement.where(SalesOrder.store_id == scope)
    if promised_on is not None:
        statement = statement.where(SalesOrder.promised_on == promised_on)
    if zone_id is not None:
        statement = statement.where(SalesOrder.delivery_zone_id == zone_id)
    if view == "unscheduled":
        statement = statement.where(
            SalesOrder.scheduling_status == "UNSCHEDULED", SalesOrder.status.in_(_SCHEDULABLE)
        )
    elif view == "scheduled":
        statement = statement.where(
            SalesOrder.scheduling_status == "SCHEDULED",
            SalesOrder.status.notin_(("CANCELLED", "CLOSED")),
        )
    elif view == "unassigned":
        statement = statement.where(
            SalesOrder.scheduling_status == "SCHEDULED",
            SalesOrder.status.notin_(("CANCELLED", "CLOSED")),
            ~_active_plan_exists(),
        )
    elif view == "assigned":
        statement = statement.where(
            _active_plan_exists(),
            SalesOrder.status.notin_(("DELIVERED", "CLOSED", "CANCELLED")),
        )
    elif view == "dispatched":
        statement = statement.where(_note_exists("DISPATCHED"))
    elif view == "delivered":
        statement = statement.where(or_(SalesOrder.status.in_(("DELIVERED", "CLOSED")), _note_exists("DELIVERED")))
    elif view == "exceptions":
        statement = statement.where(
            or_(SalesOrder.scheduling_status == "CANCELLED", SalesOrder.scheduling_status == "SCHEDULED")
        )
    ordering = (SalesOrder.promised_on.asc().nulls_last(), SalesOrder.number.asc(), SalesOrder.id.asc())
    if view == "exceptions":
        rows = db.execute(statement.order_by(*ordering)).all()
    else:
        total_sql = count_rows(db, statement)
        rows = db.execute(statement.order_by(*ordering).offset(offset).limit(limit)).all()
    order_ids = [order.id for order, _, _ in rows]
    plans: dict[uuid.UUID, DispatchPlan] = {}
    if order_ids:
        linked = db.execute(
            select(DispatchAssignment.order_id, DispatchPlan)
            .join(DispatchPlan, DispatchPlan.id == DispatchAssignment.plan_id)
            .where(DispatchAssignment.order_id.in_(order_ids), DispatchPlan.status.in_(_ACTIVE_PLANS))
        ).all()
        plans = {order_id: plan for order_id, plan in linked}
    measures = _measures(db, {line.product_id for order, _, _ in rows for line in order.lines})
    found: list[FleetOrderRow] = []
    for order, customer_name, zone_name in rows:
        plan = plans.get(order.id)
        cargo = _cargo(order, measures)
        blocked = cargo.weight_incomplete or cargo.volume_incomplete
        if view == "exceptions" and order.scheduling_status != "CANCELLED" and not (plan is not None and blocked):
            continue
        found.append(
            FleetOrderRow(
                id=order.id,
                number=order.number,
                customer_name=customer_name,
                status=order.status,
                scheduling_status=order.scheduling_status,
                requested_date=order.requested_date,
                promised_on=order.promised_on,
                window_start=order.window_start,
                window_end=order.window_end,
                delivery_zone_id=order.delivery_zone_id,
                zone_name=zone_name,
                delivery_address=order.delivery_address,
                store_id=order.store_id,
                plan_id=plan.id if plan else None,
                plan_number=plan.number if plan else None,
                plan_status=plan.status if plan else None,
                cargo_weight_incomplete=cargo.weight_incomplete,
                cargo_volume_incomplete=cargo.volume_incomplete,
            )
        )
    if view == "exceptions":
        return found[offset : offset + limit], len(found)
    return found, total_sql
