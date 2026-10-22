from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Role(TimestampMixin, Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    # Largest discount (basis points of the line) a holder of pos:discount gives without a manager; None uses the
    # business default in pos_policy.
    max_discount_bps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    permission_rows: Mapped[list[RolePermission]] = relationship(
        "RolePermission",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def permissions(self) -> set[str]:
        return {row.permission for row in self.permission_rows}

    def set_permissions(self, permissions: set[str]) -> None:
        current = {row.permission: row for row in self.permission_rows}
        for name, row in current.items():
            if name not in permissions:
                self.permission_rows.remove(row)
        for name in sorted(permissions - current.keys()):
            self.permission_rows.append(RolePermission(permission=name))


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission: Mapped[str] = mapped_column(String(64), primary_key=True)
