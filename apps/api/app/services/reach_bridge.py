"""Core entry points into AxizReach. Transactional messaging keeps working if the plugin cannot be imported."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.messaging_providers import ProviderError, deliver

_ROOT = Path(__file__).resolve().parents[4] / "plugins" / "reach"
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def channel_enabled(db: Session, channel: str) -> bool:
    try:
        from reach.service import channel_enabled as enabled
    except Exception:
        return True
    return enabled(db, channel)


def channel_credentials(db: Session, settings: Settings, channel: str) -> tuple[str, dict]:
    """Tenant channel row wins. No row, and no plugin, keeps the server provider."""
    from app.services.messaging_service import providers

    try:
        from reach.models import MessagingChannel
    except ModuleNotFoundError:
        return providers(db).get(channel, "log"), {}
    from sqlalchemy import select

    from app.core.security import decrypt_value

    row = db.scalar(select(MessagingChannel).where(MessagingChannel.channel == channel))
    if row is None:
        return providers(db).get(channel, "log"), {}
    if not row.enabled:
        raise ProviderError("This channel is turned off.", permanent=False)
    creds = {key: str(value) for key, value in (row.public_config or {}).items() if value not in (None, "")}
    if row.secret_encrypted:
        try:
            creds["secret"] = decrypt_value(row.secret_encrypted, settings)
        except Exception as exc:
            raise ProviderError("The saved credential could not be read. Save it again.", permanent=True) from exc
    return row.provider, creds


def hold_reason(db: Session, message: object) -> str | None:
    try:
        from reach.service import hold_reason as reason
    except Exception:
        return None
    return reason(db, message)


def submit(settings: Settings, provider: str, outgoing: object, creds: dict) -> str:
    if provider != "evolution":
        return deliver(settings, provider, outgoing, creds)
    from reach.providers.evolution.client import client_for

    number = "".join(ch for ch in outgoing.to if ch.isdigit())
    instance = creds.get("instance_name") or ""
    if not instance:
        raise ProviderError("No Evolution instance is selected for this message.", permanent=True)
    client = client_for(settings.evolution_api_url, settings.evolution_api_key)
    media = creds.get("media") if isinstance(creds.get("media"), dict) else None
    if media:
        return client.send_media(
            instance,
            number,
            mediatype=str(media.get("mediatype") or "document"),
            mimetype=str(media.get("mimetype") or "application/octet-stream"),
            caption=outgoing.body,
            media_b64=str(media.get("data_b64") or ""),
            file_name=str(media.get("file_name") or "file"),
        )
    return client.send_text(instance, number, outgoing.body)


def submit_message(
    db: Session,
    settings: Settings,
    provider: str,
    outgoing: object,
    creds: dict,
    message: object,
) -> str:
    if provider == "evolution":
        from reach.models import ReachConnection, ReachRecipient
        from sqlalchemy import select

        recipient = db.scalar(select(ReachRecipient).where(ReachRecipient.outbound_message_id == message.id))
        instance = ""
        if recipient is not None and recipient.connection_id is not None:
            connection = db.get(ReachConnection, recipient.connection_id)
            instance = connection.instance_name if connection is not None else ""
        if not instance:
            connection = db.scalar(select(ReachConnection).where(ReachConnection.status == "open").limit(1))
            instance = connection.instance_name if connection is not None else ""
        creds = {**creds, "instance_name": instance}
        if getattr(message, "attachment_ref", None):
            from reach.media_store import payload_for

            media = payload_for(db, str(message.attachment_ref))
            if media is None:
                from app.services.messaging_providers import ProviderError

                raise ProviderError("The campaign file is missing.", permanent=True)
            creds = {**creds, "media": media}
    return submit(settings, provider, outgoing, creds)


def record_usage(db: Session, message: object) -> None:
    try:
        from reach.service import record_usage as record
    except Exception:
        return
    record(db, message)


def after_sent(db: Session, message: object) -> None:
    try:
        from reach.service import after_sent as sent
    except Exception:
        return
    sent(db, message)


def after_skipped(db: Session, message: object) -> None:
    try:
        from reach.service import after_skipped as skipped
    except Exception:
        return
    skipped(db, message)


def after_failed(db: Session, message: object) -> None:
    try:
        from reach.service import after_failed as failed
    except Exception:
        return
    failed(db, message)
