"""Pharmacy lot history. Quantity stays on batch_items; this table only records status changes."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, text  # noqa: TID251
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, tenant_unique, utcnow

LOT_STATUSES = (
    "RELEASED",
    "UNRELEASED",
    "QUARANTINED",
    "RECALLED",
    "DAMAGED",
    "SUPPLIER_RETURN",
)
EVENT_ACTIONS = (
    "RECEIVED",
    "RELEASED",
    "QUARANTINED",
    "RECALLED",
    "DAMAGED",
    "TRANSFER_OUT",
    "TRANSFER_IN",
    "RETURNED",
    "SUPPLIER_RETURN",
)

_STATUS_LIST = ", ".join(f"'{status}'" for status in LOT_STATUSES)
_ACTION_LIST = ", ".join(f"'{action}'" for action in EVENT_ACTIONS)


class BatchItemEvent(TenantScoped, Base):
    """Append-only. Current status lives on batch_items so a draw can filter without replaying these rows."""

    __tablename__ = "batch_item_events"
    __table_args__ = (
        CheckConstraint(f"action IN ({_ACTION_LIST})", name="ck_batch_item_events_action"),
        CheckConstraint(
            f"from_status IS NULL OR from_status IN ({_STATUS_LIST})",
            name="ck_batch_item_events_from_status",
        ),
        CheckConstraint(
            f"to_status IS NULL OR to_status IN ({_STATUS_LIST})",
            name="ck_batch_item_events_to_status",
        ),
        Index("ix_batch_item_events_item", "tenant_id", "batch_item_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("batch_items.id", ondelete="CASCADE", name="fk_batch_item_events_batch_item_id_batch_items"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(16))
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    recall_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("pharmacy_recalls.id", ondelete="RESTRICT", name="fk_batch_item_events_recall_id_pharmacy_recalls"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_batch_item_events_user_id_users"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PharmacistAuthorization(TenantScoped, Base):
    """Explicit appointment to release medicine lots. A role name does not create this row.

    A new row stays PENDING until a different governance officer approves it.
    LEGACY marks a row written before two-person approval existed. The API does not create those.
    """

    __tablename__ = "pharmacist_authorizations"
    __table_args__ = (
        CheckConstraint("user_id <> granted_by_id", name="ck_pharmacist_authorizations_not_self"),
        CheckConstraint("user_id <> requested_by_id", name="ck_pharmacist_authorizations_not_requester"),
        CheckConstraint(
            "approved_by_id IS NULL OR approved_by_id <> user_id",
            name="ck_pharmacist_authorizations_approver_not_target",
        ),
        CheckConstraint(
            "approved_by_id IS NULL OR approved_by_id <> requested_by_id OR approval_basis = 'LEGACY'",
            name="ck_pharmacist_authorizations_two_person",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'ACTIVE', 'REJECTED', 'REVOKED')",
            name="ck_pharmacist_authorizations_status",
        ),
        CheckConstraint(
            "approval_basis IN ('TWO_PERSON', 'LEGACY')",
            name="ck_pharmacist_authorizations_basis",
        ),
        CheckConstraint(
            "status <> 'ACTIVE' OR approved_by_id IS NOT NULL",
            name="ck_pharmacist_authorizations_active_approver",
        ),
        CheckConstraint(
            "status <> 'PENDING' OR approved_by_id IS NULL",
            name="ck_pharmacist_authorizations_pending_open",
        ),
        CheckConstraint(
            "status <> 'REVOKED' OR (revoked_at IS NOT NULL AND revoked_by_id IS NOT NULL)",
            name="ck_pharmacist_authorizations_revoked",
        ),
        CheckConstraint(
            "status <> 'REJECTED' OR (rejected_at IS NOT NULL AND rejected_by_id IS NOT NULL)",
            name="ck_pharmacist_authorizations_rejected",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_by_id IS NOT NULL",
            name="ck_pharmacist_authorizations_revoker",
        ),
        Index(
            "uq_pharmacist_authorizations_active",
            "tenant_id",
            "user_id",
            unique=True,
            sqlite_where=text("status IN ('PENDING', 'ACTIVE')"),
            postgresql_where=text("status IN ('PENDING', 'ACTIVE')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_pharmacist_authorizations_user_id_users"),
        nullable=False,
    )
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_pharmacist_authorizations_requested_by_id_users"),
        nullable=False,
    )
    granted_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_pharmacist_authorizations_granted_by_id_users"),
        nullable=False,
    )
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_pharmacist_authorizations_approved_by_id_users"),
        nullable=True,
    )
    rejected_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_pharmacist_authorizations_rejected_by_id_users"),
        nullable=True,
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    approval_basis: Mapped[str] = mapped_column(String(16), default="TWO_PERSON")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_pharmacist_authorizations_revoked_by_id_users"),
        nullable=True,
    )
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class PharmacyGovernanceOfficer(TenantScoped, Base):
    """A person who may request or approve pharmacist appointments. The Super Admin role does not create this row."""

    __tablename__ = "pharmacy_governance_officers"
    __table_args__ = (
        CheckConstraint("user_id <> requested_by_id", name="ck_pharmacy_governance_officers_not_requester"),
        CheckConstraint(
            "approved_by_id IS NULL OR (approved_by_id <> user_id AND approved_by_id <> requested_by_id)",
            name="ck_pharmacy_governance_officers_two_person",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'ACTIVE', 'REJECTED', 'REVOKED')",
            name="ck_pharmacy_governance_officers_status",
        ),
        CheckConstraint(
            "status <> 'ACTIVE' OR approved_by_id IS NOT NULL",
            name="ck_pharmacy_governance_officers_active_approver",
        ),
        CheckConstraint(
            "status <> 'PENDING' OR approved_by_id IS NULL",
            name="ck_pharmacy_governance_officers_pending_open",
        ),
        CheckConstraint(
            "status <> 'REVOKED' OR (revoked_at IS NOT NULL AND revoked_by_id IS NOT NULL)",
            name="ck_pharmacy_governance_officers_revoked",
        ),
        Index(
            "uq_pharmacy_governance_officers_open",
            "tenant_id",
            "user_id",
            unique=True,
            sqlite_where=text("status IN ('PENDING', 'ACTIVE')"),
            postgresql_where=text("status IN ('PENDING', 'ACTIVE')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_pharmacy_governance_officers_user_id_users"),
        nullable=False,
    )
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_pharmacy_governance_officers_requested_by_id_users"),
        nullable=False,
    )
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_pharmacy_governance_officers_approved_by_id_users"),
        nullable=True,
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_pharmacy_governance_officers_revoked_by_id_users"),
        nullable=True,
    )
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


RECALL_STATUSES = ("OPEN", "CONTAINED", "CLOSED")


class PharmacyRecall(TenantScoped, Base):
    """A tenant recall. Closing it does not release stock and does not notify a regulator."""

    __tablename__ = "pharmacy_recalls"
    __table_args__ = (
        tenant_unique("reference", name="uq_pharmacy_recalls_reference"),
        CheckConstraint(
            "status IN ('OPEN', 'CONTAINED', 'CLOSED')",
            name="ck_pharmacy_recalls_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference: Mapped[str] = mapped_column(String(64))
    source_text: Mapped[str] = mapped_column(Text)
    # Length only. The architecture report does not define a severity vocabulary.
    severity: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="OPEN")
    opened_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_pharmacy_recalls_opened_by_id_users"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PharmacyRecallLot(TenantScoped, Base):
    """One manufacturer lot, and optionally one stock layer, covered by a recall."""

    __tablename__ = "pharmacy_recall_lots"
    __table_args__ = (
        CheckConstraint(
            "length(manufacturer_lot) >= 1 AND length(manufacturer_lot) <= 64",
            name="ck_pharmacy_recall_lots_manufacturer_lot",
        ),
        Index("ix_pharmacy_recall_lots_recall", "tenant_id", "recall_id"),
        Index("ix_pharmacy_recall_lots_lot", "tenant_id", "product_id", "manufacturer_lot"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recall_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "pharmacy_recalls.id",
            ondelete="CASCADE",
            name="fk_pharmacy_recall_lots_recall_id_pharmacy_recalls",
        ),
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", name="fk_pharmacy_recall_lots_product_id_products"),
    )
    manufacturer_lot: Mapped[str] = mapped_column(String(64))
    batch_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "batch_items.id",
            ondelete="SET NULL",
            name="fk_pharmacy_recall_lots_batch_item_id_batch_items",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PharmacySupplierReturn(TenantScoped, Base):
    """A supplier-return document. On-hand quantity stays on inventory_levels."""

    __tablename__ = "pharmacy_supplier_returns"
    __table_args__ = (tenant_unique("reference", name="uq_pharmacy_supplier_returns_reference"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_pharmacy_supplier_returns_created_by_id_users"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PharmacySupplierReturnLine(TenantScoped, Base):
    __tablename__ = "pharmacy_supplier_return_lines"
    __table_args__ = (CheckConstraint("quantity >= 1", name="ck_pharmacy_supplier_return_lines_quantity"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    return_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "pharmacy_supplier_returns.id",
            ondelete="CASCADE",
            name="fk_supplier_return_lines_return_id",
        ),
    )
    batch_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "batch_items.id",
            name="fk_pharmacy_supplier_return_lines_batch_item_id_batch_items",
        ),
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", name="fk_pharmacy_supplier_return_lines_product_id_products"),
    )
    quantity: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
