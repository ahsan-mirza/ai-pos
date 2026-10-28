"""Who inside a store may use an add-on the store has paid for.

One row per user and module. Grant and revoke update that row. The audit log keeps the history.
The subscription on business settings remains the only record of what the store owns.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique


class UserAddonAccess(TenantScoped, TimestampMixin, Base):
    __tablename__ = "user_addon_access"
    __table_args__ = (
        tenant_unique("user_id", "module_key", name="uq_user_addon_access_user_module"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    # Capability id, the same key billing stores on purchased_capabilities.
    module_key: Mapped[str] = mapped_column(String(64))
    # granted or revoked. A revoked row blocks a role that would otherwise allow the module.
    status: Mapped[str] = mapped_column(String(16), default="granted")
    # Action permissions from this module's catalog. Empty means the module is on with no extra actions.
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    store_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), nullable=True)
    granted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    revoked_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
