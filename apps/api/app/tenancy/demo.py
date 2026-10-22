"""One demo store per business type (packages/catalog/demo-businesses.json), each with staff logins and a register.

New stores are built by the signup provisioning steps (onboarded, in practice mode with sample items). Existing ones
are migrated and keep their data; every run adds any missing staff or register and issues a fresh activation key,
because keys work once and expire after a day."""

from __future__ import annotations

import json
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.database import build_engine, create_database
from app.core.deps import Principal
from app.core.security import hash_password, hash_pin
from app.models.device import Device
from app.models.role import Role
from app.models.store import Store
from app.models.user import User
from app.schemas.devices import DeviceCreate
from app.services import device_service
from app.services.rbac_service import SUPER_ADMIN_ID, ensure_system_roles
from app.tenancy import provisioning, registry
from app.tenancy.context import TenantRef, use_tenant


def demo_path() -> Path:
    return Path(__file__).resolve().parents[4] / "packages" / "catalog" / "demo-businesses.json"


@dataclass
class Result:
    slug: str
    name: str
    profile: str
    created: bool
    url: str
    activation_key: str


@contextmanager
def _session(ref: TenantRef) -> Iterator[Session]:
    engine = build_engine(ref.database_url)
    try:
        with sessionmaker(bind=engine, expire_on_commit=False)() as db, use_tenant(ref):
            yield db
    finally:
        engine.dispose()


def _create(spec: dict, demo: dict, settings: Settings) -> None:
    job = provisioning.Job(
        request_id=uuid.uuid4(),
        settings=settings,
        slug=spec["slug"],
        store_name=spec["name"],
        profile=spec["profile"],
        sub_type=spec["sub_type"] or "",
        currency="AED",
        trn=None,
        email=f"owner@{spec['slug']}.demo.ai-pos.local",
        full_name=demo["staff"][0]["full_name"],
        password_hash=hash_password(demo["password"]),
        tenant_id=None,
        owner_username=None,
    )
    url = make_url(job.url)
    if url.get_backend_name() == "postgresql":
        create_database(url.set(database="postgres").render_as_string(hide_password=False), job.database)
    provisioning.step_migrations(job)
    provisioning.step_register(job)
    provisioning.step_settings(job)
    provisioning.step_samples(job)


def _ensure_staff(db: Session, spec: dict, demo: dict, settings: Settings, store: Store) -> User:
    ensure_system_roles(db)
    owner: User | None = None
    for person in demo["staff"]:
        user = db.scalar(select(User).where(User.username == person["username"]))
        if user is None:
            role = db.scalar(select(Role).where(Role.name == person["role"]))
            if role is None:
                sys.exit(f"Role {person['role']} is missing in {spec['slug']}.")
            business_wide = role.id == SUPER_ADMIN_ID
            user = User(
                username=person["username"],
                email=f"{person['username']}@{spec['slug']}.demo.ai-pos.local",
                full_name=person["full_name"],
                hashed_password=hash_password(demo["password"]) if person["portal"] else None,
                hashed_pin=hash_pin(person["pin"], settings),
                is_active=True,
                store_id=None if business_wide else store.id,
                role_id=role.id,
                has_pos_access=True,
                has_portal_access=person["portal"],
                failed_login_attempts=0,
                token_version=0,
            )
            db.add(user)
            db.flush()
        if user.role_id == SUPER_ADMIN_ID and owner is None:
            owner = user
    db.commit()
    if owner is None:
        sys.exit(f"{spec['slug']} has no Super Admin in the demo staff list.")
    return owner


def _activation_key(db: Session, demo: dict, owner: User, store: Store) -> str:
    principal = Principal(kind="user", scope="portal", user=owner, permissions=frozenset(owner.permissions))
    code = demo["register"]["code"]
    device = db.scalar(select(Device).where(Device.store_id == store.id, Device.code == code))
    if device is None:
        created = device_service.create_device(
            db, principal, DeviceCreate(store_id=store.id, code=code, name=demo["register"]["name"])
        )
        device_id = created.device.id
    else:
        device_id = device.id
    return device_service.issue_activation_key(db, principal, device_id).activation_key


def provision_all(settings: Settings, only: set[str] | None = None) -> list[Result]:
    if settings.app_env == "production":
        sys.exit("Demo stores are for development and dev environments only.")
    demo = json.loads(demo_path().read_text(encoding="utf-8"))
    results: list[Result] = []
    for spec in demo["businesses"]:
        if only and spec["slug"] not in only:
            continue
        created = registry.lookup(spec["slug"], settings).tenant is None
        print(f"{spec['slug']}: {'creating' if created else 'updating'}...", flush=True)
        if created:
            _create(spec, demo, settings)
            registry.invalidate(spec["slug"])
        ref = registry.lookup(spec["slug"], settings).tenant
        assert ref is not None
        if not created:
            provisioning.migrate(ref.database_url)
        with _session(ref) as db:
            store = db.scalar(select(Store).where(Store.is_warehouse.is_(False)).order_by(Store.created_at).limit(1))
            if store is None:
                sys.exit(f"{spec['slug']} has no store to put the register in.")
            owner = _ensure_staff(db, spec, demo, settings, store)
            key = _activation_key(db, demo, owner, store)
        results.append(
            Result(
                slug=spec["slug"],
                name=spec["name"],
                profile=spec["profile"],
                created=created,
                url=registry.tenant_public_url(spec["slug"], settings),
                activation_key=key,
            )
        )
    return results


def report(results: list[Result]) -> None:
    demo = json.loads(demo_path().read_text(encoding="utf-8"))
    print()
    print(f"{'Subdomain':<18} {'Business type':<22} {'Portal':<34} POS activation key (one use, 24 h)")
    for item in results:
        print(f"{item.slug:<18} {item.profile:<22} {item.url:<34} {item.activation_key}")
    print()
    print("Same staff in every store:")
    for person in demo["staff"]:
        portal = f"password {demo['password']}" if person["portal"] else "register only"
        print(f"  {person['username']:<8} {person['role']:<14} PIN {person['pin']}  ({portal})")
    print()
    print(f"Register {demo['register']['code']}: open the POS app, enter the subdomain and its key.")
    print("Running locally, each portal is at http://<subdomain>.localhost:5173.")
