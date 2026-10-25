"""Builds a store for a signup, one recorded step at a time, so the signup screen shows real progress.

Steps already done are skipped on retry. Each store gets its own database, exactly as `app.tenancy.cli create`
does, then the owner account, business settings and a few sample products to practise with."""

from __future__ import annotations

import logging
import re
import secrets
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core import capabilities as capability_catalog
from app.core.config import Settings
from app.core.database import build_engine, create_database
from app.models.store import Store
from app.models.user import User
from app.services import sample_data
from app.services.rbac_service import super_admin_role_id
from app.services.settings_service import load_settings
from app.services.taxonomy_service import ensure_taxonomy
from app.tenancy import cli, registry
from app.tenancy.context import TenantRef, use_tenant
from app.tenancy.models import SignupRequest, Tenant

logger = logging.getLogger("ai_pos.provisioning")

# Tests swap this for metadata.create_all; the migration chain targets Postgres.
migrate: Callable[[str], None] = cli.upgrade_tenant


@dataclass
class Job:
    request_id: uuid.UUID
    settings: Settings
    slug: str
    store_name: str
    profile: str
    sub_type: str
    currency: str
    trn: str | None
    email: str
    full_name: str
    password_hash: str
    tenant_id: uuid.UUID | None
    owner_username: str | None

    @property
    def database(self) -> str:
        return f"qios_{self.slug.replace('-', '_')}"

    @property
    def url(self) -> str:
        return registry.tenant_database_url(self.database, self.settings)


def _mark(settings: Settings, request_id: uuid.UUID, key: str, state: str, **fields: object) -> None:
    with registry.control_session(settings) as db:
        row = db.get(SignupRequest, request_id)
        if row is None:
            return
        row.steps = [{**step, "state": state} if step["key"] == key else step for step in (row.steps or [])]
        for name, value in fields.items():
            setattr(row, name, value)
        db.commit()


@contextmanager
def _tenant_session(job: Job) -> Iterator[Session]:
    engine = build_engine(job.url)
    ref = TenantRef(id=str(job.tenant_id), slug=job.slug, name=job.store_name, database_url=job.url)
    try:
        with sessionmaker(bind=engine, expire_on_commit=False)() as db, use_tenant(ref):
            yield db
    finally:
        engine.dispose()


def step_database(job: Job) -> None:
    url = make_url(job.url)
    if url.get_backend_name() != "postgresql":
        return
    server = url.set(database="postgres").render_as_string(hide_password=False)
    try:
        created = create_database(server, job.database)
    except Exception as error:
        if "permission denied to create database" in str(error).lower():
            user = url.username or "the database user"
            raise RuntimeError(
                f"permission denied to create database. On the server run: ALTER ROLE {user} CREATEDB;"
            ) from error
        raise
    if not created:
        raise RuntimeError(f"A database named {job.database} already exists; choose another store address.")


def step_migrations(job: Job) -> None:
    migrate(job.url)


def step_register(job: Job) -> None:
    with registry.control_session(job.settings) as db:
        existing = db.scalar(select(Tenant).where(Tenant.slug == job.slug))
        if existing is None:
            existing = Tenant(
                slug=job.slug,
                name=job.store_name,
                status="active",
                profile=job.profile,
                database_url_encrypted=registry.encrypt_database_url(job.url, job.settings),
            )
            db.add(existing)
            db.flush()
            from app.console.billing import start_trial

            start_trial(db, existing)
            db.commit()
        job.tenant_id = existing.id
    registry.invalidate(job.slug)
    with registry.control_session(job.settings) as db:
        row = db.get(SignupRequest, job.request_id)
        if row is not None:
            row.tenant_id = job.tenant_id
            db.commit()


def _username(db: Session, email: str) -> str:
    stem = re.sub(r"[^a-z0-9._-]", "", email.split("@", 1)[0].lower())[:28] or "owner"
    candidate = stem
    for index in range(2, 100):
        if db.scalar(select(User.id).where(User.username == candidate)) is None:
            return candidate
        candidate = f"{stem}{index}"
    return f"owner{secrets.randbelow(10_000)}"


def step_owner(job: Job) -> None:
    with _tenant_session(job) as db:
        role_id = super_admin_role_id(db)
        owner = db.scalar(select(User).where(User.email == job.email, User.role_id == role_id))
        if owner is None:
            owner = User(
                username=_username(db, job.email),
                email=job.email,
                full_name=job.full_name,
                hashed_password=job.password_hash,
                hashed_pin=None,
                is_active=True,
                store_id=None,
                role_id=role_id,
                has_pos_access=False,
                has_portal_access=True,
                failed_login_attempts=0,
                token_version=0,
            )
            db.add(owner)
        db.commit()
        job.owner_username = owner.username
    _mark(job.settings, job.request_id, "owner", "running", owner_username=job.owner_username)


def step_settings(job: Job) -> None:
    with _tenant_session(job) as db:
        row = load_settings(db, lock=True)
        row.business_profile = job.profile
        modules = capability_catalog.SUB_TYPES.get(job.profile, {}).get(
            job.sub_type, capability_catalog.PROFILES[job.profile]
        )
        row.capabilities = [capability.value for capability in modules]
        row.currency = job.currency
        row.legal_name = job.store_name
        row.trn = job.trn
        row.vat_registered = job.trn is not None
        row.onboarded_at = datetime.now(UTC)
        row.live_at = None
        if db.scalar(select(Store.id).limit(1)) is None:
            db.add(Store(code="MAIN", name=job.store_name, currency=job.currency, is_warehouse=False, is_active=True))
        ensure_taxonomy(db, job.profile)
        db.commit()


def step_samples(job: Job) -> None:
    with _tenant_session(job) as db:
        sample_data.load(db, job.settings, profile=job.profile, sub_type=job.sub_type)


def step_ready(job: Job) -> None:
    _mark(
        job.settings,
        job.request_id,
        "ready",
        "done",
        status="READY",
        handoff_jti=secrets.token_hex(16),
        owner_username=job.owner_username,
    )


STEP_FUNCTIONS: dict[str, Callable[[Job], None]] = {
    "database": step_database,
    "migrations": step_migrations,
    "register": step_register,
    "owner": step_owner,
    "settings": step_settings,
    "samples": step_samples,
    "ready": step_ready,
}


def provision(request_id: uuid.UUID, settings: Settings) -> None:
    with registry.control_session(settings) as db:
        row = db.get(SignupRequest, request_id)
        if row is None or row.status != "PROVISIONING":
            return
        job = Job(
            request_id=row.id,
            settings=settings,
            slug=row.slug or "",
            store_name=row.store_name or "",
            profile=row.profile or capability_catalog.DEFAULT_PROFILE,
            sub_type=row.sub_type or "",
            currency=row.currency or "AED",
            trn=row.trn,
            email=row.email,
            full_name=row.full_name,
            password_hash=row.password_hash,
            tenant_id=row.tenant_id,
            owner_username=row.owner_username,
        )
        steps = [(step["key"], step["state"]) for step in (row.steps or [])]
    for key, state in steps:
        if state == "done" and key not in ("owner",):
            continue
        _mark(settings, request_id, key, "running")
        try:
            STEP_FUNCTIONS[key](job)
        except Exception as error:
            logger.exception("Provisioning %s failed at %s", job.slug, key)
            _mark(settings, request_id, key, "failed", status="FAILED", error=f"{key}: {error}"[:500])
            return
        if key != "ready":
            _mark(settings, request_id, key, "done")
