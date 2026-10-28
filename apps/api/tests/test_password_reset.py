"""A portal user can set a new password with a code emailed from the platform mailbox."""

import re
from datetime import UTC, datetime, timedelta

from redis.exceptions import RedisError
from sqlalchemy import select

from app.console import mail
from app.core import cache
from app.core.config import get_settings
from app.models.user import User
from app.services.messaging_providers import ProviderError


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
    assert "account was changed" in captured["body"].lower()

    again = client.post(
        "/api/v1/auth/reset-password",
        json={"email": "admin@example.com", "code": code.group(1), "password": "another-password-123"},
    )
    assert again.status_code == 400

    old = client.post(
        "/api/v1/auth/login-password",
        json={"username": "admin", "password": "root-password-123"},
    )
    assert old.status_code == 401


def test_expired_code_and_too_many_attempts_are_refused(client, session, monkeypatch):
    _mailbox(monkeypatch)
    captured: dict[str, str] = {}
    def capture(message, **kwargs):
        captured["body"] = message.body
        return "id"

    monkeypatch.setattr(mail, "transmit_smtp", capture)
    assert client.post("/api/v1/auth/forgot-password", json={"email": "admin@example.com"}).status_code == 200
    code = re.search(r"\b(\d{6})\b", captured["body"]).group(1)
    user = session.scalar(select(User).where(User.email == "admin@example.com"))
    user.reset_code_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    session.commit()
    expired = client.post("/api/v1/auth/verify-reset-code", json={"email": "admin@example.com", "code": code})
    assert expired.status_code == 400

    user.reset_code_expires_at = datetime.now(UTC) + timedelta(minutes=10)
    user.reset_code_attempts = 5
    session.commit()
    blocked = client.post("/api/v1/auth/verify-reset-code", json={"email": "admin@example.com", "code": code})
    assert blocked.status_code == 400


def test_inactive_user_is_not_emailed(client, session, monkeypatch):
    _mailbox(monkeypatch)
    sent: list[str] = []
    monkeypatch.setattr(mail, "transmit_smtp", lambda *args, **kwargs: sent.append("x") or "id")
    user = session.scalar(select(User).where(User.email == "admin@example.com"))
    user.is_active = False
    session.commit()
    response = client.post("/api/v1/auth/forgot-password", json={"email": "admin@example.com"})
    assert response.status_code == 200
    assert sent == []


def test_mail_failure_does_not_leave_a_usable_code(client, monkeypatch):
    _mailbox(monkeypatch)

    def fail(*args, **kwargs):
        raise ProviderError("mailbox down")

    monkeypatch.setattr(mail, "transmit_smtp", fail)
    response = client.post("/api/v1/auth/forgot-password", json={"email": "admin@example.com"})
    assert response.status_code == 502
    still = client.post(
        "/api/v1/auth/login-password",
        json={"username": "admin", "password": "root-password-123"},
    )
    assert still.status_code == 200


def test_reset_revokes_the_existing_token(client, monkeypatch):
    _mailbox(monkeypatch)
    captured: dict[str, str] = {}
    def capture(message, **kwargs):
        captured["body"] = message.body
        return "id"

    monkeypatch.setattr(mail, "transmit_smtp", capture)
    signed_in = client.post(
        "/api/v1/auth/login-password",
        json={"username": "admin", "password": "root-password-123"},
    )
    token = signed_in.json()["access_token"]
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    client.post("/api/v1/auth/forgot-password", json={"email": "admin@example.com"})
    code = re.search(r"\b(\d{6})\b", captured["body"]).group(1)
    reset = client.post(
        "/api/v1/auth/reset-password",
        json={"email": "admin@example.com", "code": code, "password": "new-password-123"},
    )
    assert reset.status_code == 200
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_password_reset_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(mail, "platform_link", lambda settings: None)
    last = None
    for _ in range(6):
        last = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})
    assert last is not None
    assert last.status_code == 429


def test_redis_failure_blocks_password_reset(client, monkeypatch):
    class Down:
        def incr(self, *args, **kwargs):
            raise RedisError("down")

    monkeypatch.setattr(cache, "_client_for", lambda: Down())
    response = client.post("/api/v1/auth/forgot-password", json={"email": "admin@example.com"})
    assert response.status_code == 503


def test_short_password_is_rejected(client):
    response = client.post(
        "/api/v1/auth/reset-password",
        json={"email": "admin@example.com", "code": "000000", "password": "short"},
    )
    assert response.status_code == 422
