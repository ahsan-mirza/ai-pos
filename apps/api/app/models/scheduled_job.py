from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, PrimaryKeyConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped


class ScheduledJob(TenantScoped, Base):
    """One lease per store. The name is unique inside the tenant, so two stores can run the same job."""

    __tablename__ = "scheduled_jobs"
    __table_args__ = (PrimaryKeyConstraint("tenant_id", "name", name="pk_scheduled_jobs"),)

    name: Mapped[str] = mapped_column(String(64))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(12), nullable=True)
    last_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
