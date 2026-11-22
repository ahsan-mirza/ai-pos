"""Prepare the disposable grocery register for native checkout.

Opens only 127.0.0.1:55944 / axizpos_o84act. Adds the register permission the
cashier fixture was missing, keeps a separate recovery cashier, and issues the
40/35 allocation through the allocation service. Prints counts only.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PORT = 55944
DB = "axizpos_o84act"
TEMP = Path(os.environ["TEMP"])
os.environ["APP_ENV"] = "acceptance"
os.environ["DATABASE_URL"] = f"postgresql+psycopg://ai_pos_app:o84-act-app-password@127.0.0.1:{PORT}/{DB}"
os.environ["CONTROL_DATABASE_URL"] = ""
os.environ["JWT_SECRET"] = "o84-act-jwt-secret-32-characters!!"
os.environ["PIN_SALT"] = "o84-act-pin-pepper"
os.environ["ENCRYPTION_SECRET"] = "o84-act-encryption-secret-32chars!"
os.environ["API_KEY"] = "o84-act-api-key!!"
os.environ["CORS_ORIGINS"] = "http://127.0.0.1:18084"
os.environ["PUBLIC_BASE_URL"] = "http://127.0.0.1:18084"
os.environ["TENANT_PUBLIC_URL_TEMPLATE"] = "http://127.0.0.1:18084"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["DEFAULT_TENANT"] = ""
os.environ["ENTITLEMENT_SIGNING_KEY_ID"] = "o84-accept-1"
os.environ["ENTITLEMENT_SIGNING_SEED"] = (TEMP / "o84-accept-seed.txt").read_text(encoding="ascii").strip()

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.deps import Principal
from app.core.security import hash_pin
from app.models.device import Device
from app.models.inventory import InventoryLevel
from app.models.product import Product
from app.models.role import Role
from app.models.store import Store
from app.models.terminal_allocation import TerminalAllocation
from app.models.user import User
from app.services import allocation_service
from app.tenancy.scoping import install

install()
settings = get_settings()
url = make_url(settings.database_url)
if url.host != "127.0.0.1" or url.port != PORT or url.database != DB or url.username != "ai_pos_app":
    raise SystemExit("Refusing a database that is not the disposable acceptance database.")

engine = create_engine(settings.database_url)
with engine.connect() as probe:
    probe.execute(text("SELECT set_config('app.tenant_id', '00000000-0000-4000-8000-0000000000a1', false)"))
    role = probe.execute(
        text("SELECT current_user, current_database(), inet_server_port(), rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname = current_user")
    ).one()
    if role[0] != "ai_pos_app" or role[1] != DB or role[2] != PORT or role[3] or role[4] or not role[5]:
        raise SystemExit("Application role is not the constrained disposable role.")

factory = sessionmaker(bind=engine, expire_on_commit=False)
with factory() as db:
    role_row = db.scalar(select(Role).where(Role.name == "Acceptance manager"))
    if role_row is None:
        raise SystemExit("Acceptance role is missing.")
    role_row.set_permissions(set(role_row.permissions) | {"pos:access"})
    cashier = db.scalar(select(User).where(User.username == "cashier"))
    if cashier is None or not cashier.is_active or cashier.hashed_pin is None:
        raise SystemExit("Acceptance cashier fixture is missing.")
    store = db.get(Store, cashier.store_id)
    if store is None or store.code != "MAIN":
        raise SystemExit("Cashier is not on the grocery branch.")
    recover = db.scalar(select(User).where(User.username == "recover"))
    if recover is None:
        recover = User(
            username="recover",
            email="recover@o84.test",
            full_name="Acceptance Recovery",
            hashed_password="not-used",
            hashed_pin=hash_pin("1357", settings),
            is_active=True,
            role_id=role_row.id,
            store_id=store.id,
            has_pos_access=True,
            has_portal_access=False,
            token_version=0,
        )
        db.add(recover)
    product = db.scalar(select(Product).where(Product.sku == "O84-APPLE"))
    if product is None:
        raise SystemExit("Acceptance product is missing.")
    till_a = db.scalar(select(Device).where(Device.code == "TILLA"))
    till_b = db.scalar(select(Device).where(Device.code == "TILLB"))
    if till_a is None or till_b is None:
        raise SystemExit("Acceptance terminals are missing.")
    if not till_a.device_public_key_thumbprint:
        raise SystemExit("Till A has no device binding, so an allocation cannot be signed.")
    db.commit()

    def holding(device_id: uuid.UUID) -> int:
        rows = db.scalars(
            select(TerminalAllocation).where(
                TerminalAllocation.device_id == device_id,
                TerminalAllocation.product_id == product.id,
                TerminalAllocation.status == "ACTIVE",
            )
        ).all()
        return sum(row.quantity_allocated - row.quantity_consumed for row in rows)

    manager = db.scalar(select(User).where(User.username == "manager"))
    if manager is None:
        raise SystemExit("Acceptance manager is missing.")
    principal = Principal(
        kind="user",
        scope="portal",
        user=manager,
        permissions=frozenset(manager.permissions),
    )
    if holding(till_a.id) == 0:
        allocation_service.issue_allocation(
            db, principal, store_id=store.id, device_id=till_a.id, product_id=product.id, quantity=40
        )
        db.commit()
    if holding(till_b.id) == 0:
        allocation_service.issue_allocation(
            db, principal, store_id=store.id, device_id=till_b.id, product_id=product.id, quantity=35
        )
        db.commit()
    level = db.scalar(
        select(InventoryLevel).where(InventoryLevel.product_id == product.id, InventoryLevel.store_id == store.id)
    )
    print("pos_access", "pos:access" in role_row.permissions)
    print("cashier_active", cashier.is_active)
    print("cashier_store", store.code)
    print("recover_present", recover.username == "recover" and recover.is_active)
    print("on_hand", None if level is None else level.quantity_on_hand)
    print("reserved", None if level is None else level.quantity_reserved)
    print("till_a_remaining", holding(till_a.id))
    print("till_b_remaining", holding(till_b.id))
    print("profile_ready", True)
