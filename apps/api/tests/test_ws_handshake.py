"""POS sockets can authenticate after connect so the token stays out of the URL."""

from datetime import UTC, datetime, timedelta

import pytest
from starlette.websockets import WebSocketDisconnect

from app.core.config import get_settings


def test_a_token_in_the_url_is_refused(client) -> None:
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/v1/ws/live?token=not-logged&role=pos"):
            pass


def test_query_token_window_follows_the_timestamp(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "ws_query_token_until", "")
    assert settings.query_token_allowed is False
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    monkeypatch.setattr(settings, "ws_query_token_until", past)
    assert settings.query_token_allowed is False
    ahead = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    monkeypatch.setattr(settings, "ws_query_token_until", ahead)
    assert settings.query_token_allowed is True
    monkeypatch.setattr(settings, "ws_query_token_until", "not-a-date")
    assert settings.query_token_allowed is False


def test_live_socket_reads_the_token_from_the_first_frame(client) -> None:
    url = "/api/v1/ws/live?role=pos&terminal_id=00000000-0000-0000-0000-000000000001"
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(url) as socket:
            socket.send_json(
                {
                    "type": "auth",
                    "token": "not-a-device-token",
                    "role": "pos",
                    "terminal_id": "00000000-0000-0000-0000-000000000001",
                }
            )
            socket.receive_text()


def test_live_socket_rejects_a_frame_that_is_not_auth(client) -> None:
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/v1/ws/live?role=pos") as socket:
            socket.send_json({"type": "hello"})
            socket.receive_text()


def test_table_socket_reads_the_token_from_the_first_frame(client) -> None:
    store = "00000000-0000-0000-0000-000000000001"
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/api/v1/ws/stores/{store}/tables?role=pos") as socket:
            socket.send_json({"type": "auth", "token": "not-a-device-token", "role": "pos"})
            socket.receive_text()
