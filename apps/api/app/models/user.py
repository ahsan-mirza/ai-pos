from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.permissions import Permission
from app.models.base import Base, TimestampMixin
from app.models.role import Role


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hashed_pin: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    store_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("stores.id"),
        nullable=True,
        index=True,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("roles.id"), index=True)
    has_pos_access: Mapped[bool] = mapped_column(Boolean, default=False)
    has_portal_access: Mapped[bool] = mapped_column(Boolean, default=False)
    # Extra grant for typing a price on open-price items. The role may already include it.
    can_sell_open_price: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reset_code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reset_code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reset_code_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reset_code_attempts: Mapped[int] = mapped_column(Integer, default=0)
    role: Mapped[Role] = relationship("Role", lazy="joined")

    @property
    def permissions(self) -> set[str]:
        granted = set(self.role.permissions)
        if self.can_sell_open_price:
            granted.add(Permission.POS_OPEN_PRICE.value)
        return granted
