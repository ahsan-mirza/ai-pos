"""Frozen catalogue pages and the product change feed for register bootstrap. Additive. No stock ledger."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, utcnow


class BootstrapSession(TenantScoped, Base):
    __tablename__ = "bootstrap_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    product_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    watermark: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    since_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BootstrapSnapshotItem(TenantScoped, Base):
    __tablename__ = "bootstrap_snapshot_items"

    session_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    # Frozen catalogue row for this session. Later product edits are not written back into it.
    payload: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class BootstrapDatasetItem(TenantScoped, Base):
    """Frozen menu or floor row for one bootstrap session. Products stay on bootstrap_snapshot_items."""

    __tablename__ = "bootstrap_dataset_items"

    session_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    dataset: Mapped[str] = mapped_column(String(16), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class CatalogFeedCounter(TenantScoped, Base):
    """One row per tenant. The sequence increments under a row lock, so a later commit cannot pass an earlier one."""

    __tablename__ = "catalog_feed_counters"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retain_after: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class BootstrapSettingSnapshot(TenantScoped, Base):
    """Currency, tax, and receipt facts frozen with the catalogue session. One row."""

    __tablename__ = "bootstrap_setting_snapshots"

    session_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class CatalogChange(TenantScoped, Base):
    """Ordered product create, update, and delete. Sequence is per database, not a wall clock."""

    __tablename__ = "catalog_changes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seq: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    dataset: Mapped[str] = mapped_column(String(32), nullable=False)
    record_id: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
