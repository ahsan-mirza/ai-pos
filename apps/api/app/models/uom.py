from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UnitOfMeasure(TimestampMixin, Base):
    """A pack a product can be sold in, as a whole number of base units (pieces). Stock and sale quantities stay in
    base units; a sale line records the pack code and its factor. PIECE, BOX_10 and CARTON_100 are built in
    (app.services.uom_service.SYSTEM_UNITS); this table holds the ones a business adds, e.g. CASE_24."""

    __tablename__ = "units_of_measure"
    __table_args__ = (CheckConstraint("factor >= 2", name="uom_factor_at_least_two"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(60))
    short_name: Mapped[str] = mapped_column(String(16))
    # Base units in one pack. Fixed once created: sale lines and register carts depend on it.
    factor: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
