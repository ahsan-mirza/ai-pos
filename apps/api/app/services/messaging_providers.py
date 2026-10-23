"""Message delivery adapters. "log" works out of the box; the others are configured through env credentials."""

import logging
import smtplib
import uuid
from dataclasses import dataclass
from email.message import EmailMessage

import httpx

from app.core.config import Settings

logger = logging.getLogger("ai_pos.messaging")

CHANNEL_PROVIDERS: dict[str, tuple[str, ...]] = {
    "whatsapp": ("log", "whatsapp_cloud"),
    "sms": ("log", "http_sms"),
    "email": ("log", "smtp"),
}


class ProviderError(Exception):
    """Delivery failed. `permanent` errors are not retried (bad number, provider not configured)."""

    def __init__(self, message: str, *, permanent: bool = False) -> None:
        super().__init__(message)
        self.permanent = permanent


@dataclass
class Outgoing:
    to: str
    subject: str
    body: str
    attachment: tuple[str, bytes] | None = None


def _require(value: str | None, name: str) -> str:
    if not value:
        raise ProviderError(f"{name} is not configured on the server.", permanent=True)
    return value


def send_log(settings: Settings, message: Outgoing) -> str:
    logger.info("message to %s: %s", message.to, message.body[:200])
    return f"log-{uuid.uuid4().hex[:12]}"


def send_whatsapp_cloud(settings: Settings, message: Outgoing) -> str:
    token = _require(settings.whatsapp_token, "WHATSAPP_TOKEN")
    phone_id = _require(settings.whatsapp_phone_number_id, "WHATSAPP_PHONE_NUMBER_ID")
    number = "".join(ch for ch in message.to if ch.isdigit())
    response = httpx.post(
        f"https://graph.facebook.com/{settings.whatsapp_api_version}/{phone_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"messaging_product": "whatsapp", "to": number, "type": "text", "text": {"body": message.body}},
        timeout=15,
    )
    if response.status_code >= 400:
        raise ProviderError(
            f"WhatsApp {response.status_code}: {response.text[:200]}", permanent=response.status_code < 500
        )
    return str(response.json().get("messages", [{}])[0].get("id", ""))


def send_http_sms(settings: Settings, message: Outgoing) -> str:
    url = _require(settings.sms_http_url, "SMS_HTTP_URL")
    headers = {"Authorization": f"Bearer {settings.sms_http_token}"} if settings.sms_http_token else {}
    response = httpx.post(
        url, headers=headers, json={"to": message.to, "from": settings.sms_sender, "text": message.body}, timeout=15
    )
    if response.status_code >= 400:
        raise ProviderError(
            f"SMS gateway {response.status_code}: {response.text[:200]}", permanent=response.status_code < 500
        )
    try:
        return str(response.json().get("id", ""))
    except ValueError:
        return ""


def transmit_smtp(
    message: Outgoing,
    *,
    host: str,
    port: int,
    username: str | None,
    password: str | None,
    sender: str,
    security: str,
) -> str:
    """security is ssl (port 465), starttls (port 587), or none."""
    email = EmailMessage()
    email["From"] = sender
    email["To"] = message.to
    email["Subject"] = message.subject or "Message"
    email.set_content(message.body)
    if message.attachment is not None:
        name, content = message.attachment
        email.add_attachment(content, maintype="application", subtype="pdf", filename=name)
    client_cls = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
    try:
        with client_cls(host, port, timeout=20) as client:
            if security == "starttls":
                client.starttls()
            if username and password:
                client.login(username, password)
            client.send_message(email)
    except smtplib.SMTPRecipientsRefused as exc:
        raise ProviderError(f"Address refused: {exc}", permanent=True) from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise ProviderError(f"SMTP failed: {exc}") from exc
    return email.get("Message-ID", "") or ""


def send_smtp(settings: Settings, message: Outgoing) -> str:
    from app.console.mail import platform_link

    link = platform_link(settings)
    if link is None:
        host = _require(settings.smtp_host, "SMTP_HOST")
        sender = _require(settings.smtp_from, "SMTP_FROM")
        security = "starttls" if settings.smtp_starttls else ("ssl" if settings.smtp_port == 465 else "none")
        return transmit_smtp(
            message,
            host=host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            sender=sender,
            security=security,
        )
    return transmit_smtp(
        message,
        host=link.host,
        port=link.port,
        username=link.username,
        password=link.password,
        sender=link.sender,
        security=link.security,
    )


SENDERS = {
    "log": send_log,
    "whatsapp_cloud": send_whatsapp_cloud,
    "http_sms": send_http_sms,
    "smtp": send_smtp,
}


def deliver(settings: Settings, provider: str, message: Outgoing) -> str:
    sender = SENDERS.get(provider)
    if sender is None:
        raise ProviderError(f"Unknown provider {provider}.", permanent=True)
    return sender(settings, message)
