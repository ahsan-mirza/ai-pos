"""The signed-in cashier's catalogue view. The user id comes from the token."""

import importlib.util
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from tests.test_auth import API_KEY, CASHIER_PIN, admin_token, bearer

from app.core.permissions import CASHIER_ROLE_ID
from app.models.user_preference import CATALOGUE_VIEW_KEY, UserPreference
from app.tenancy.context import TenantRef, use_tenant

CASHIER_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")

PATH = "/api/v1/users/me/preferences"
WRITE = "/api/v1/users/me/preferences/product-catalogue-view"


def cashier_token(client) -> str:
    response = client.post(
        "/api/v1/auth/login-pin",
        json={"username": "cashier", "pin": CASHIER_PIN},
        headers={"X-Api-Key": API_KEY},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_missing_preference_is_grid_and_requires_a_signed_in_cashier(client) -> None:
    assert client.get(PATH).status_code == 401
    assert client.put(WRITE, json={"product_catalogue_view": "list"}).status_code == 401
    device = client.get(PATH, headers={"X-Api-Key": API_KEY})
    assert device.status_code == 403
    token = cashier_token(client)
    current = client.get(PATH, headers=bearer(token))
    assert current.status_code == 200, current.text
    assert current.json() == {"product_catalogue_view": "grid", "updated_at": None, "revision": 0}


def test_cashier_saves_and_reads_only_their_own_view(client, session) -> None:
    token = admin_token(client)
    created = client.post(
        "/api/v1/users",
        headers=bearer(token),
        json={
            "username": "cashier.two",
            "email": "cashier.two@example.com",
            "full_name": "Second Cashier",
            "role_id": CASHIER_ROLE_ID,
            "pin": "9753",
            "has_pos_access": True,
            "has_portal_access": False,
        },
    )
    assert created.status_code == 201, created.text
    first = cashier_token(client)
    second = client.post(
        "/api/v1/auth/login-pin",
        json={"username": "cashier.two", "pin": "9753"},
        headers={"X-Api-Key": API_KEY},
    )
    assert second.status_code == 200, second.text
    second_token = second.json()["access_token"]

    saved = client.put(WRITE, headers=bearer(first), json={"product_catalogue_view": "grid"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["product_catalogue_view"] == "grid"
    assert saved.json()["revision"] == 1
    other = client.put(WRITE, headers=bearer(second_token), json={"product_catalogue_view": "list"})
    assert other.status_code == 200, other.text

    probed = client.get(f"{PATH}?user_id={created.json()['id']}", headers=bearer(first))
    assert probed.status_code == 200
    assert probed.json()["product_catalogue_view"] == "grid"
    assert client.get(PATH, headers=bearer(second_token)).json()["product_catalogue_view"] == "list"
    rejected = client.put(
        WRITE,
        headers=bearer(first),
        json={"product_catalogue_view": "list", "user_id": created.json()["id"]},
    )
    assert rejected.status_code == 422
    invalid = client.put(WRITE, headers=bearer(first), json={"product_catalogue_view": "tiles"})
    assert invalid.status_code == 422

    rows = session.scalars(select(UserPreference).where(UserPreference.preference_key == CATALOGUE_VIEW_KEY)).all()
    assert len(rows) == 2
    assert {row.preference_value for row in rows} == {"grid", "list"}


def test_an_older_update_does_not_replace_a_newer_view(client, session) -> None:
    token = cashier_token(client)
    now = datetime.now(UTC)
    earlier = (now - timedelta(hours=2)).isoformat()
    later = (now + timedelta(minutes=1)).isoformat()
    first = client.put(
        WRITE,
        headers=bearer(token),
        json={"product_catalogue_view": "list", "updated_at": earlier},
    )
    assert first.status_code == 200, first.text
    stale = client.put(
        WRITE,
        headers=bearer(token),
        json={"product_catalogue_view": "compact", "updated_at": earlier},
    )
    assert stale.status_code == 200, stale.text
    assert stale.json()["product_catalogue_view"] == "list"
    fresh = client.put(
        WRITE,
        headers=bearer(token),
        json={"product_catalogue_view": "compact", "updated_at": later},
    )
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["product_catalogue_view"] == "compact"
    assert fresh.json()["revision"] == 2
    rows = session.scalars(select(UserPreference)).all()
    assert len(rows) == 1
    assert rows[0].preference_value == "compact"


def test_one_cashier_keeps_a_different_view_in_each_tenant(session) -> None:
    alpha = TenantRef(id=str(uuid.uuid4()), slug="alpha", name="Alpha", database_url="sqlite://")
    bravo = TenantRef(id=str(uuid.uuid4()), slug="bravo", name="Bravo", database_url="sqlite://")
    with use_tenant(alpha):
        session.add(
            UserPreference(
                id=uuid.uuid4(),
                user_id=CASHIER_ID,
                preference_key=CATALOGUE_VIEW_KEY,
                preference_value="list",
                revision=1,
            )
        )
        session.commit()
    with use_tenant(bravo):
        session.add(
            UserPreference(
                id=uuid.uuid4(),
                user_id=CASHIER_ID,
                preference_key=CATALOGUE_VIEW_KEY,
                preference_value="compact",
                revision=1,
            )
        )
        session.commit()
    with use_tenant(alpha):
        visible = session.scalars(select(UserPreference)).all()
        assert [row.preference_value for row in visible] == ["list"]
    with use_tenant(bravo):
        visible = session.scalars(select(UserPreference)).all()
        assert [row.preference_value for row in visible] == ["compact"]


def test_check_constraint_rejects_an_unknown_view(session) -> None:
    session.add(
        UserPreference(
            id=uuid.uuid4(),
            user_id=uuid.UUID("00000000-0000-4000-8000-000000000002"),
            preference_key=CATALOGUE_VIEW_KEY,
            preference_value="tiles",
            revision=1,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_migration_creates_the_preference_table_on_a_disposable_database(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{(tmp_path / 'preferences.db').as_posix()}")
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20261119_0120_user_preferences.py"
    spec = importlib.util.spec_from_file_location("user_preferences_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            module.upgrade()
        tables = inspect(connection).get_table_names()
        assert "user_preferences" in tables
        unique = {item["name"] for item in inspect(connection).get_unique_constraints("user_preferences")}
        assert "uq_user_preferences_user_key" in unique
        with Operations.context(MigrationContext.configure(connection)):
            module.downgrade()
        assert "user_preferences" not in inspect(connection).get_table_names()
    engine.dispose()
