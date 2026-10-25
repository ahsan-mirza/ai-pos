from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, Uuid, event
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, tenant_unique, utcnow

AUDIT_ACTION_TYPES = (
    "CREATE",
    "UPDATE",
    "DELETE",
    "MANUAL_STOCK_ADJUSTMENT",
    "PRICE_OVERRIDE",
    "CREDIT_LIMIT_OVERRIDE",
    "ROLE_CHANGE",
    "REFUND_PROCESSED",
    "MANAGER_OVERRIDE",
    "LOGIN_PIN",
    "LOGIN_PASSWORD",
    "EXPORT_DATA",
    "DRAWER_OPEN",
    "CASH_DROP",
    "ITEM_VOID",
    "EXPIRED_STOCK_SOLD",
)

SENSITIVE_ACTION_TYPES = (
    "MANUAL_STOCK_ADJUSTMENT",
    "PRICE_OVERRIDE",
    "CREDIT_LIMIT_OVERRIDE",
    "ROLE_CHANGE",
    "REFUND_PROCESSED",
    "MANAGER_OVERRIDE",
    "DRAWER_OPEN",
    "ITEM_VOID",
)

CLIENT_DEVICES = ("web", "desktop", "api", "system")


class AuditLog(TenantScoped, Base):
    """Append-only ledger. Rows are never updated or deleted (enforced here and by a Postgres trigger)."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        tenant_unique("client_event_id", name="uq_audit_logs_client_event_id"),
        Index("ix_audit_logs_action_type_occurred_at", "action_type", "occurred_at"),
        Index("ix_audit_logs_tenant_occurred", "tenant_id", "occurred_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    approver_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    store_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("stores.id"), nullable=True, index=True
    )
    action_type: Mapped[str] = mapped_column(String(32), index=True)
    # Fine-grained event key, e.g. "settings.currency" or "return.override".
    action: Mapped[str] = mapped_column(String(64), index=True)
    target_entity: Mapped[str] = mapped_column(String(40), index=True)
    target_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    old_values: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    new_values: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    reason_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    client_device: Mapped[str] = mapped_column(String(16), default="system")
    request_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Snapshots so the trail stays readable after a user is renamed or a role is edited.
    user_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Desktop events carry their own id so offline batches can be re-sent safely.
    client_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


@event.listens_for(AuditLog, "before_update")
def _block_update(*_: object) -> None:
    raise PermissionError("Audit log entries are immutable.")


@event.listens_for(AuditLog, "before_delete")
def _block_delete(*_: object) -> None:
    raise PermissionError("Audit log entries are immutable.")
