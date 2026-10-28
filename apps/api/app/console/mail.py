"""Platform mailbox, edited in the console and used to email store users."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.console.security import OperatorPrincipal, audit_operator
from app.core.config import Settings
from app.core.errors import ApiError
from app.core.security import decrypt_value, encrypt_value
from app.schemas.mail import MailSettingsIn, MailSettingsOut
from app.services.email_brand import notice_html
from app.services.messaging_providers import Outgoing, ProviderError, transmit_smtp
from app.tenancy import registry
from app.tenancy.models import MailSettings

_ROW_ID = 1
_EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}")


@dataclass(frozen=True)
class SmtpLink:
    host: str
    port: int
    username: str | None
    password: str | None
    sender: str
    security: str


def _row(db: Session) -> MailSettings:
    row = db.get(MailSettings, _ROW_ID)
    if row is None:
        row = MailSettings(id=_ROW_ID, updated_at=datetime.now(UTC))
        db.add(row)
        db.flush()
    return row


def _address(value: str, label: str) -> str:
    text = value.strip()
    if text and (len(text) > 254 or _EMAIL.fullmatch(text.lower()) is None):
        raise ApiError(422, "invalid_email", f"{label} is not an email address.")
    return text


def _sender(name: str, address: str) -> str:
    clean = name.replace('"', "").strip() or "AxizPOS"
    return f"{clean} <{address}>"


def read_settings(db: Session) -> MailSettingsOut:
    row = _row(db)
    security = row.security if row.security in {"ssl", "starttls", "none"} else "ssl"
    return MailSettingsOut(
        enabled=row.enabled,
        host=row.host,
        port=row.port,
        security=security,  # type: ignore[arg-type]
        username=row.username,
        password_set=bool(row.password_encrypted),
        from_address=row.from_address,
        from_name=row.from_name,
    )


def save_settings(
    db: Session, settings: Settings, operator: OperatorPrincipal, data: MailSettingsIn
) -> MailSettingsOut:
    host = data.host.strip()
    username = data.username.strip()
    from_address = _address(data.from_address, "From address")
    from_name = data.from_name.strip() or "AxizPOS"
    row = _row(db)
    if data.enabled and (not host or not from_address):
        raise ApiError(422, "mail_incomplete", "Enter the outgoing server and the From address before turning mail on.")
    if data.enabled and username and not data.password and not row.password_encrypted:
        raise ApiError(422, "mail_incomplete", "Enter the mailbox password.")
    before = {"enabled": row.enabled, "host": row.host, "port": row.port, "from_address": row.from_address}
    row.enabled = data.enabled
    row.host = host
    row.port = data.port
    row.security = data.security
    row.username = username
    if data.password:
        row.password_encrypted = encrypt_value(data.password, settings)
    elif not username:
        row.password_encrypted = ""
    row.from_address = from_address
    row.from_name = from_name
    row.updated_at = datetime.now(UTC)
    audit_operator(
        db,
        operator,
        "mail.settings",
        before=before,
        after={"enabled": row.enabled, "host": row.host, "port": row.port, "from_address": row.from_address},
        reason=data.reason,
    )
    db.commit()
    return read_settings(db)


def _link_from_row(settings: Settings, row: MailSettings) -> SmtpLink | None:
    if not row.enabled or not row.host.strip() or not row.from_address.strip():
        return None
    password = decrypt_value(row.password_encrypted, settings) if row.password_encrypted else None
    security = row.security if row.security in {"ssl", "starttls", "none"} else "ssl"
    return SmtpLink(
        host=row.host.strip(),
        port=row.port,
        username=row.username.strip() or None,
        password=password,
        sender=_sender(row.from_name, row.from_address.strip()),
        security=security,
    )


def _link_from_env(settings: Settings) -> SmtpLink | None:
    if not settings.smtp_host or not settings.smtp_from:
        return None
    if settings.smtp_starttls:
        security = "starttls"
    elif settings.smtp_port == 465:
        security = "ssl"
    else:
        security = "none"
    return SmtpLink(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        sender=settings.smtp_from,
        security=security,
    )


def platform_link(settings: Settings) -> SmtpLink | None:
    """Console mailbox when it is turned on, otherwise the SMTP_* values in the server env."""
    if settings.control_database_url:
        try:
            with registry.control_session(settings) as db:
                row = db.get(MailSettings, _ROW_ID)
                link = _link_from_row(settings, row) if row is not None else None
        except SQLAlchemyError:
            link = None
        if link is not None:
            return link
    return _link_from_env(settings)


def send(settings: Settings, message: Outgoing) -> str:
    link = platform_link(settings)
    if link is None:
        raise ProviderError("Email is not configured. Add the mailbox in the console.", permanent=True)
    return transmit_smtp(
        message,
        host=link.host,
        port=link.port,
        username=link.username,
        password=link.password,
        sender=link.sender,
        security=link.security,
    )


def send_test(settings: Settings, to: str) -> None:
    address = _address(to, "Test address")
    if not address:
        raise ApiError(422, "invalid_email", "Enter an email address to send the test to.")
    try:
        send(
            settings,
            Outgoing(
                to=address,
                subject="AxizPOS mailbox test",
                body="This is a test from AxizPOS. Password-reset codes use this mailbox.",
                html=notice_html(
                    heading="Mailbox test",
                    body="This is a test from AxizPOS. Password-reset codes use this mailbox.",
                    support_email=settings.support_email,
                ),
            ),
        )
    except ProviderError as error:
        raise ApiError(502, "mail_failed", str(error)) from error
