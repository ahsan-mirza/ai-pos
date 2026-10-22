# Environment must be set before the application settings are imported.
# ruff: noqa: E402
import os

# APP_ENV=test reads .env.test only, so a developer's .env never reaches the tests.
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["CONTROL_DATABASE_URL"] = ""
os.environ["DEFAULT_TENANT"] = ""
os.environ["JWT_SECRET"] = "test-jwt-secret-must-be-32-chars!!"
os.environ["PIN_SALT"] = "test-pin-pepper-16chars"
os.environ["ENCRYPTION_SECRET"] = "test-encryption-secret-32-chars!"
os.environ["API_KEY"] = "test-api-key-value"
os.environ["API_HOST"] = "127.0.0.1"
os.environ["API_PORT"] = "8000"
os.environ["CORS_ORIGINS"] = "http://localhost:5173"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["SYNC_MAX_BATCH_SIZE"] = "100"
os.environ["LOGIN_MAX_ATTEMPTS"] = "3"
os.environ["LOGIN_LOCKOUT_MINUTES"] = "15"
os.environ["SCHEDULER_ENABLED"] = "false"

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.database import build_engine, get_db
from app.core.permissions import CASHIER_ROLE_ID
from app.core.security import hash_pin
from app.main import app
from app.models import Base, User
from app.services.rbac_service import ensure_super_admin, ensure_system_roles
from app.services.settings_service import clear_settings_cache

get_settings.cache_clear()

CASHIER_ID = "00000000-0000-4000-8000-000000000002"
CASHIER_PIN = "1357"
ADMIN_PASSWORD = "root-password-123"
ADMIN_PIN = "2468"


@pytest.fixture()
def session() -> Session:
    clear_settings_cache()
    engine = build_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    settings = get_settings()
    ensure_system_roles(db)
    ensure_super_admin(
        db,
        settings,
        username="admin",
        email="admin@example.com",
        full_name="Root Admin",
        password=ADMIN_PASSWORD,
        pin=ADMIN_PIN,
    )
    db.add(
        User(
            id=uuid.UUID(CASHIER_ID),
            username="cashier",
            email="cashier@example.com",
            full_name="Front Cashier",
            hashed_pin=hash_pin(CASHIER_PIN, settings),
            is_active=True,
            store_id=None,
            role_id=uuid.UUID(CASHIER_ROLE_ID),
            has_pos_access=True,
            has_portal_access=False,
            failed_login_attempts=0,
            token_version=0,
        )
    )
    db.commit()
    yield db
    db.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def client(session: Session):
    def override():
        yield session

    app.dependency_overrides[get_db] = override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
