"""Laundry intake orders. Garments in process are work items, not saleable stock."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, LargeBinary, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique, utcnow

ORDER_TYPES = ("WALK_IN", "DROP_OFF", "PICKUP")
OPERATIONAL_STATUSES = (
    "RECEIVED",
    "TAGGED",
    "IN_PRODUCTION",
    "READY",
    "READY_FOR_COLLECTION",
    "COLLECTED",
    "CANCELLED",
)
GARMENT_STAGES = (
    "RECEIVED",
    "TAGGED",
    "SORTING",
    "WASHING",
    "DRYING",
    "FOLDING",
    "PRE_TREATMENT",
    "DRY_CLEANING",
    "FINISHING",
    "IRONING",
    "QUALITY_CHECK",
    "PACKING",
    "IN_PRODUCTION",
    "READY",
    "COLLECTED",
    "EXCEPTION",
)
PAYMENT_STATUSES = ("UNPAID", "PARTIAL", "PAID", "REFUNDED")
COLLECTION_STATUSES = ("AT_BRANCH", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED", "COLLECTED")
CLAIM_STATUSES = ("NONE", "OPEN", "RESOLVED")
PRE_PRODUCTION = ("RECEIVED", "TAGGED")


class LaundryOrder(TenantScoped, TimestampMixin, Base):
    __tablename__ = "laundry_orders"
    __table_args__ = (
        tenant_unique("idempotency_key", name="uq_laundry_orders_idempotency"),
        CheckConstraint("subtotal_cents >= 0", name="ck_laundry_orders_subtotal"),
        CheckConstraint("discount_cents >= 0", name="ck_laundry_orders_discount"),
        CheckConstraint("surcharge_cents >= 0", name="ck_laundry_orders_surcharge"),
        CheckConstraint("tax_cents >= 0", name="ck_laundry_orders_tax"),
        CheckConstraint("total_cents >= 0", name="ck_laundry_orders_total"),
        CheckConstraint("amount_paid_cents >= 0", name="ck_laundry_orders_paid"),
        CheckConstraint("balance_due_cents >= 0", name="ck_laundry_orders_due"),
        CheckConstraint("amount_paid_cents + balance_due_cents = total_cents", name="ck_laundry_orders_balance"),
        CheckConstraint("garment_count >= 0 AND bag_count >= 0", name="ck_laundry_orders_counts"),
        CheckConstraint("version >= 1", name="ck_laundry_orders_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(80))
    code: Mapped[str] = mapped_column(String(24))
    intake_store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    plant_store_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), nullable=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"), index=True)
    order_type: Mapped[str] = mapped_column(String(16))
    price_list_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("laundry_price_lists.id"), nullable=True
    )
    currency: Mapped[str] = mapped_column(String(3))
    promised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    express: Mapped[bool] = mapped_column(Boolean, default=False)
    instructions: Mapped[str] = mapped_column(Text, default="")
    garment_count: Mapped[int] = mapped_column(Integer, default=0)
    bag_count: Mapped[int] = mapped_column(Integer, default=0)
    measured_weight: Mapped[int] = mapped_column(Integer, default=0)
    subtotal_cents: Mapped[int] = mapped_column(Integer)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0)
    surcharge_cents: Mapped[int] = mapped_column(Integer, default=0)
    tax_cents: Mapped[int] = mapped_column(Integer, default=0)
    total_cents: Mapped[int] = mapped_column(Integer)
    amount_paid_cents: Mapped[int] = mapped_column(Integer, default=0)
    balance_due_cents: Mapped[int] = mapped_column(Integer)
    payment_status: Mapped[str] = mapped_column(String(16), default="UNPAID", index=True)
    operational_status: Mapped[str] = mapped_column(String(32), default="RECEIVED", index=True)
    collection_status: Mapped[str] = mapped_column(String(20), default="AT_BRANCH")
    claim_status: Mapped[str] = mapped_column(String(16), default="NONE")
    pricing_snapshot: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("devices.id"), nullable=True)


class LaundryGarment(TenantScoped, TimestampMixin, Base):
    __tablename__ = "laundry_garments"
    __table_args__ = (CheckConstraint("quantity >= 1", name="ck_laundry_garments_quantity"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_orders.id"), index=True)
    service_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_services.id"), index=True)
    garment_type: Mapped[str] = mapped_column(String(40), default="")
    description: Mapped[str] = mapped_column(String(160), default="")
    brand: Mapped[str] = mapped_column(String(80), default="")
    colour: Mapped[str] = mapped_column(String(40), default="")
    fabric: Mapped[str] = mapped_column(String(40), default="")
    size: Mapped[str] = mapped_column(String(20), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    instructions: Mapped[str] = mapped_column(String(500), default="")
    condition: Mapped[str] = mapped_column(String(80), default="")
    stains: Mapped[str] = mapped_column(String(255), default="")
    pre_existing_damage: Mapped[str] = mapped_column(String(255), default="")
    stage: Mapped[str] = mapped_column(String(32), default="RECEIVED", index=True)
    location_store_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("stores.id"), nullable=True
    )
    exception_state: Mapped[str] = mapped_column(String(20), default="NONE")
    line_snapshot: Mapped[dict] = mapped_column(JSON)
    workflow_code: Mapped[str] = mapped_column(String(40), default="")
    sorting_category: Mapped[str] = mapped_column(String(40), default="")
    station: Mapped[str] = mapped_column(String(40), default="")
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    current_batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    stage_entered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rework_count: Mapped[int] = mapped_column(Integer, default=0)
    qc_result: Mapped[str] = mapped_column(String(20), default="")
    hold: Mapped[bool] = mapped_column(Boolean, default=False)
    location_label: Mapped[str] = mapped_column(String(80), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)


class LaundryBag(TenantScoped, TimestampMixin, Base):
    __tablename__ = "laundry_bags"
    __table_args__ = (
        CheckConstraint("gross_weight > tare_weight", name="ck_laundry_bags_net"),
        CheckConstraint("tare_weight >= 0", name="ck_laundry_bags_tare"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_orders.id"), index=True)
    service_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_services.id"), index=True)
    bag_type: Mapped[str] = mapped_column(String(40), default="MIXED")
    gross_weight: Mapped[int] = mapped_column(Integer)
    tare_weight: Mapped[int] = mapped_column(Integer, default=0)
    net_weight: Mapped[int] = mapped_column(Integer)
    scale_reference: Mapped[str] = mapped_column(String(80), default="")
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    location_store_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("stores.id"), nullable=True
    )
    contents: Mapped[list] = mapped_column(JSON, default=list)
    line_snapshot: Mapped[dict] = mapped_column(JSON)


class LaundryTag(TenantScoped, Base):
    __tablename__ = "laundry_tags"
    __table_args__ = (tenant_unique("code", name="uq_laundry_tags_code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(40))
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_orders.id"), index=True)
    garment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("laundry_garments.id"), nullable=True
    )
    bag_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_bags.id"), nullable=True)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("devices.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LaundryTagEvent(TenantScoped, Base):
    __tablename__ = "laundry_tag_events"
    __table_args__ = (tenant_unique("idempotency_key", name="uq_laundry_tag_events_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tag_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_tags.id"), index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_orders.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    idempotency_key: Mapped[str] = mapped_column(String(80))
    note: Mapped[str] = mapped_column(String(255), default="")
    device_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("devices.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LaundryPhoto(TenantScoped, Base):
    __tablename__ = "laundry_photos"
    __table_args__ = (CheckConstraint("byte_size > 0 AND byte_size <= 5000000", name="ck_laundry_photos_size"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_orders.id"), index=True)
    garment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("laundry_garments.id"), nullable=True
    )
    mime: Mapped[str] = mapped_column(String(40))
    byte_size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LaundryOrderEvent(TenantScoped, Base):
    __tablename__ = "laundry_order_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_orders.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reason: Mapped[str] = mapped_column(String(500), default="")
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LaundryDeposit(TenantScoped, Base):
    """Held intake money. The drawer counts cash the same way it counts a repair deposit."""

    __tablename__ = "laundry_deposits"
    __table_args__ = (CheckConstraint("amount_cents > 0", name="ck_laundry_deposits_amount"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_orders.id"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(10), default="HELD", index=True)
    received_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    shift_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    refund_shift_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
