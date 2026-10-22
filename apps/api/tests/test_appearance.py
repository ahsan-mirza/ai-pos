from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog
from test_returns import STORE_ID, STORE_MANAGER_ROLE, admin_token, bearer, device, seed_catalog
from test_settings import portal_user


def set_color(client, token: str, color: str | None):
    return client.put("/api/v1/settings/appearance", headers=bearer(token), json={"primary_color": color})


def test_primary_color_defaults_to_brand_and_round_trips(client, session: Session) -> None:
    assert client.get("/api/v1/settings", headers=device()).json()["primary_color"] is None

    token = admin_token(client)
    saved = set_color(client, token, "#2563eb")
    assert saved.status_code == 200, saved.text
    assert saved.json()["primary_color"] == "#2563EB"
    assert client.get("/api/v1/settings", headers=device()).json()["primary_color"] == "#2563EB"

    log = session.scalars(select(AuditLog).where(AuditLog.action == "settings.appearance")).one()
    assert log.old_values == {"primary_color": None}
    assert log.new_values == {"primary_color": "#2563EB"}

    reset = set_color(client, token, None)
    assert reset.status_code == 200 and reset.json()["primary_color"] is None


def test_primary_color_must_be_a_hex_code(client) -> None:
    token = admin_token(client)
    for bad in ("blue", "#12345", "#GGGGGG", "2563EB", "#2563EB80"):
        assert set_color(client, token, bad).status_code == 422, bad


def test_only_business_wide_admins_change_the_color(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    manager = portal_user(client, token, username="manager", role_id=STORE_MANAGER_ROLE, store_id=STORE_ID)
    assert set_color(client, manager, "#10B981").status_code == 403
    assert client.put("/api/v1/settings/appearance", json={"primary_color": "#10B981"}).status_code == 401
