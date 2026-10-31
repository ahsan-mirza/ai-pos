import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session
from tests.test_kds import floor_table, stations
from tests.test_menu import enable
from tests.test_returns import API_KEY, STORE_ID, admin_token, bearer, device, seed_catalog

from app.models import PaymentTerminal, Store
from app.services.peripheral_status import (
    CHECK_FRESH,
    display_light,
    kds_light,
    table_light,
    terminal_light,
)


def _by_kind(body: dict) -> dict[str, dict]:
    return {item["kind"]: item for item in body["items"]}


def test_lights_follow_live_signals_not_configuration() -> None:
    now = datetime.now(UTC)
    assert kds_light(0, 0) is None
    assert kds_light(2, 0) == "red"
    assert kds_light(2, 1) == "amber"
    assert kds_light(2, 2) == "green"
    assert table_light(False, 0, False) is None
    assert table_light(True, 0, False) == "gray"
    assert table_light(True, 0, True) == "red"
    assert table_light(True, 2, True) == "green"
    assert display_light(0, False) is None
    assert display_light(0, True) == "red"
    assert display_light(1, True) == "green"
    assert terminal_light(None, None, now=now, fresh=CHECK_FRESH) == "gray"
    assert terminal_light(now, False, now=now, fresh=CHECK_FRESH) == "red"
    assert terminal_light(now, True, now=now, fresh=CHECK_FRESH) == "green"
    assert terminal_light(now - timedelta(hours=1), True, now=now, fresh=CHECK_FRESH) == "amber"


def test_snapshot_uses_the_register_branch_and_live_sockets(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    enable(client, token, "open_orders", "kds", "tables", "card_terminals")
    suffix = uuid.uuid4().hex[:6].upper()
    created = client.post(
        "/api/v1/devices",
        headers=bearer(token),
        json={"store_id": STORE_ID, "code": f"M{suffix[:4]}", "name": "Monitor"},
    )
    assert created.status_code == 201, created.text
    register = {"X-Terminal-Token": created.json()["key"]}
    register_id = created.json()["device"]["id"]
    bar, _kitchen = stations(client, token, session)
    floor_table(client, token)
    other = Store(code=f"O{suffix[:4]}", name="Other branch", currency="AED")
    session.add(other)
    session.flush()
    session.add(
        PaymentTerminal(
            store_id=other.id,
            provider="simulator",
            terminal_ref=f"OTHER-{suffix}",
            label="Other branch till",
            is_active=True,
        )
    )
    mine = PaymentTerminal(
        store_id=uuid.UUID(STORE_ID),
        provider="simulator",
        terminal_ref=f"SIM-{suffix}",
        label="This branch till",
        device_id=uuid.UUID(register_id),
        is_active=True,
    )
    session.add(mine)
    session.commit()

    shared = client.get("/api/v1/peripherals", headers=device())
    assert shared.status_code == 422

    idle = client.get(f"/api/v1/peripherals?store_id={other.id}", headers=register)
    assert idle.status_code == 200, idle.text
    lights = _by_kind(idle.json())
    assert "Other branch till" not in idle.text
    assert lights["kds"]["light"] == "red"
    assert lights["kds"]["connected"] == 0
    assert lights["table_apps"]["connected"] == 0
    assert lights["table_apps"]["light"] != "green"
    assert lights["card_terminal"]["light"] == "gray"
    assert lights["card_terminal"]["name"] == "This branch till"
    assert f"SIM-{suffix}" not in idle.text
    assert "customer_display" not in lights

    with client.websocket_connect(
        f"/api/v1/ws/live?token={created.json()['key']}&role=kds&station_id={bar['id']}"
    ):
        live = _by_kind(client.get("/api/v1/peripherals", headers=register).json())
        assert live["kds"]["light"] == "amber"
        assert live["kds"]["connected"] == 1

    with client.websocket_connect(f"/api/v1/ws/stores/{STORE_ID}/tables?token={API_KEY}"):
        connected = _by_kind(client.get("/api/v1/peripherals", headers=register).json())
        assert connected["table_apps"]["light"] == "green"
        assert connected["table_apps"]["connected"] >= 1
    dropped = _by_kind(client.get("/api/v1/peripherals", headers=register).json())
    assert dropped["table_apps"]["light"] == "red"

    with client.websocket_connect(
        f"/api/v1/ws/live?token={created.json()['key']}&role=customer-display&terminal_id={register_id}"
    ):
        paired = _by_kind(client.get("/api/v1/peripherals", headers=register).json())
        assert paired["customer_display"]["light"] == "green"
    assert _by_kind(client.get("/api/v1/peripherals", headers=register).json())["customer_display"]["light"] == "red"

    mine.last_checked_at = datetime.now(UTC) - timedelta(hours=1)
    mine.last_check_ok = True
    session.commit()
    assert _by_kind(client.get("/api/v1/peripherals", headers=register).json())["card_terminal"]["light"] == "amber"
    mine.last_check_ok = False
    session.commit()
    assert _by_kind(client.get("/api/v1/peripherals", headers=register).json())["card_terminal"]["light"] == "red"

    cashier = client.post("/api/v1/auth/login-pin", json={"username": "cashier", "pin": "1357"}, headers=device())
    assert cashier.status_code == 200, cashier.text
    forbidden = client.post(
        "/api/v1/peripherals/card-terminal/check",
        headers={"Authorization": f"Bearer {cashier.json()['access_token']}"},
    )
    assert forbidden.status_code == 403
    checked = client.post("/api/v1/peripherals/card-terminal/check", headers=register)
    assert checked.status_code == 200, checked.text
    assert checked.json()["ok"] is True
    assert _by_kind(client.get("/api/v1/peripherals", headers=register).json())["card_terminal"]["light"] == "green"
