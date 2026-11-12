"""Signup, password reset, and store-code recovery send codes through one service."""

import pytest

from app.console import mail
from app.core.config import get_settings
from app.services import otp_service
from app.services.messaging_providers import ProviderError


def test_seal_matches_only_that_subject_and_code() -> None:
    sealed = otp_service.seal("user-1", "482916")
    assert otp_service.matches(sealed, "user-1", "482916")
    assert otp_service.matches(sealed, "user-1", "482 916")
    assert not otp_service.matches(sealed, "user-1", "111111")
    assert not otp_service.matches(sealed, "user-2", "482916")
    assert not otp_service.matches(None, "user-1", "482916")


def test_email_otp_uses_the_platform_mailbox(monkeypatch) -> None:
    sent: dict[str, str] = {}

    def capture(_settings, message) -> str:
        sent["to"] = message.to
        sent["subject"] = message.subject
        sent["body"] = message.body
        return "id"

    monkeypatch.setattr(mail, "send", capture)
    otp_service.send(
        get_settings(),
        to="person@example.com",
        purpose="password_reset",
        code="482916",
        minutes=10,
        name="Ahsan",
    )
    assert sent["to"] == "person@example.com"
    assert sent["subject"] == "Reset your AxizPOS password"
    assert "482916" in sent["body"]


def test_signup_and_store_code_are_the_same_sender(monkeypatch) -> None:
    subjects: list[str] = []
    monkeypatch.setattr(mail, "send", lambda _settings, message: subjects.append(message.subject) or "id")
    settings = get_settings()
    otp_service.send(settings, to="a@example.com", purpose="signup", code="100200", minutes=3)
    otp_service.send(settings, to="a@example.com", purpose="store_code", code="100200", minutes=10)
    assert subjects == ["Verify your AxizPOS email", "Your AxizPOS store code verification"]


def test_log_channel_does_not_open_the_mailbox(monkeypatch) -> None:
    def refuse(*_args, **_kwargs) -> str:
        raise AssertionError("the log channel must not email")

    monkeypatch.setattr(mail, "send", refuse)
    otp_service.send(
        get_settings(),
        to="+971500000000",
        purpose="signup",
        code="100200",
        minutes=3,
        channel="log",
    )


def test_unknown_purpose_is_refused() -> None:
    with pytest.raises(ProviderError):
        otp_service.send(
            get_settings(),
            to="person@example.com",
            purpose="nope",  # type: ignore[arg-type]
            code="100200",
            minutes=3,
        )
