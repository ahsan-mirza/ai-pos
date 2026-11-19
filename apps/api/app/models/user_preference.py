"""One cashier's personal register preference.

This is not a general settings table. The only key the API accepts is the product
catalogue view. Uniqueness is tenant + user + key, so two cashiers on one register
keep separate choices and one tenant cannot see another's row.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique

CATALOGUE_VIEW_KEY = "product_catalogue_view"
CATALOGUE_VIEWS = ("grid", "list", "compact")


class UserPreference(TenantScoped, TimestampMixin, Base):
    __tablename__ = "user_preferences"
    __table_args__ = (
        tenant_unique("user_id", "preference_key", name="uq_user_preferences_user_key"),
        CheckConstraint(
            "preference_key = 'product_catalogue_view'",
            name="ck_user_preferences_catalogue_key",
        ),
        CheckConstraint(
            "preference_value IN ('grid', 'list', 'compact')",
            name="ck_user_preferences_catalogue_value",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_user_preferences_user_id_users"),
        index=True,
    )
    preference_key: Mapped[str] = mapped_column(String(64))
    preference_value: Mapped[str] = mapped_column(String(16))
    # Increments on each accepted write so a sync can tell two saves apart.
    revision: Mapped[int] = mapped_column(Integer, default=1)
