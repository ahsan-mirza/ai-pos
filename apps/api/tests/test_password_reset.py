"""A portal user can set a new password with a code emailed from the platform mailbox."""

import re

from app.console import mail
from app.core.config import get_settings


def _mailbox(monkeypatch, *, port: int = 587, starttls: bool = True) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "mail.spacemail.com")
    monkeypatch.setattr(settings, "smtp_port", port)
    monkeypatch.setattr(settings, "smtp_starttls", starttls)
    monkeypatch.setattr(settings, "smtp_from", "pos@example.com")


def test_missing_mailbox_uses_the_same_reply(client, monkeypatch):
    monkeypatch.setattr(mail, "platform_link", lambda settings: None)
    response = client.post("/api/v1/auth/forgot-password", json={"email": "admin@example.com"})
    assert response.status_code == 200
    body = response.text.lower()
    assert "console" not in body
    assert "mailbox" not in body


def test_unknown_email_does_not_send(client, monkeypatch):
    _mailbox(monkeypatch)
    sent: list[str] = []
    monkeypatch.setattr(mail, "transmit_smtp", lambda *args, **kwargs: sent.append("x") or "id")
    response = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})
    assert response.status_code == 200
    assert sent == []


def test_code_resets_the_portal_password(client, monkeypatch):
    _mailbox(monkeypatch, port=465, starttls=False)
    captured: dict[str, str] = {}

    def fake_send(message, **kwargs):
        captured["to"] = message.to
        captured["body"] = message.body
        captured["security"] = kwargs["security"]
        return "msg-1"

    monkeypatch.setattr(mail, "transmit_smtp", fake_send)
    requested = client.post("/api/v1/auth/forgot-password", json={"email": "admin@example.com"})
    assert requested.status_code == 200
    assert captured["to"] == "admin@example.com"
    assert captured["security"] == "ssl"
    code = re.search(r"\b(\d{6})\b", captured["body"])
    assert code is not None

    bad = "111111" if code.group(1) == "000000" else "000000"
    wrong = client.post(
        "/api/v1/auth/verify-reset-code",
        json={"email": "admin@example.com", "code": bad},
    )
    assert wrong.status_code == 400

    checked = client.post(
        "/api/v1/auth/verify-reset-code",
        json={"email": "admin@example.com", "code": code.group(1)},
    )
    assert checked.status_code == 200

    reset = client.post(
        "/api/v1/auth/reset-password",
        json={"email": "admin@example.com", "code": code.group(1), "password": "new-password-123"},
    )
    assert reset.status_code == 200

    signed_in = client.post(
        "/api/v1/auth/login-password",
        json={"username": "admin", "password": "new-password-123"},
    )
    assert signed_in.status_code == 200
