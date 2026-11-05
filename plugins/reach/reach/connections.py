"""WhatsApp connections on the central Evolution API. One instance per connection."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from app.core.config import Settings
from app.core.errors import ApiError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from reach.models import ReachConnection, ReachWebhookEvent
from reach.providers.evolution.client import EvolutionError, client_for
from reach.service import bind_evolution_channel


def list_connections(db: Session) -> list[ReachConnection]:
    return list(db.scalars(select(ReachConnection).order_by(ReachConnection.created_at.desc())))


def provider_health(settings: Settings) -> dict:
    """Central Evolution status. This is not the store's WhatsApp session."""
    client = client_for(settings.evolution_api_url, settings.evolution_api_key)
    try:
        client.health()
    except EvolutionError as exc:
        return {"status": exc.code, "detail": str(exc)[:300]}
    return {"status": "healthy", "detail": None}


def create_connection(db: Session, settings: Settings, name: str) -> ReachConnection:
    existing = db.scalar(select(ReachConnection).order_by(ReachConnection.created_at.asc()).limit(1))
    if existing is not None:
        return existing
    _require_healthy(settings)
    instance = f"reach-{uuid.uuid4().hex[:12]}"
    client = client_for(settings.evolution_api_url, settings.evolution_api_key)
    try:
        client.create_instance(instance)
    except Exception as exc:
        raise ApiError(502, _error_code(exc), str(exc)[:300]) from exc
    row = ReachConnection(
        name=name.strip(),
        instance_name=instance,
        status="created",
        webhook_key=secrets.token_urlsafe(32),
    )
    db.add(row)
    db.flush()
    _register_webhook(settings, row)
    db.commit()
    db.refresh(row)
    return row


def connect(db: Session, settings: Settings, connection_id: uuid.UUID) -> dict:
    row = _row(db, connection_id)
    if row.status == "open":
        return refresh_status(db, settings, connection_id)
    _require_healthy(settings)
    client = client_for(settings.evolution_api_url, settings.evolution_api_key)
    try:
        payload = client.connect(row.instance_name)
    except Exception as exc:
        if "HTTP 404" in str(exc):
            try:
                client.create_instance(row.instance_name)
                payload = client.connect(row.instance_name)
            except EvolutionError as retry_exc:
                exc = retry_exc
                payload = None
        else:
            payload = None
        if payload is None:
            row.last_error = str(exc)[:300]
            if row.status != "open":
                row.status = "error"
            db.commit()
            raise ApiError(502, _error_code(exc), row.last_error) from exc
    row.status = "qr"
    row.last_error = None
    _register_webhook(settings, row)
    db.commit()
    db.refresh(row)
    return {**_public(row, _last_webhook(db, row.id)), "qr_base64": _qr(payload)}


def refresh_status(db: Session, settings: Settings, connection_id: uuid.UUID) -> dict:
    row = _row(db, connection_id)
    client = client_for(settings.evolution_api_url, settings.evolution_api_key)
    try:
        payload = client.status(row.instance_name)
    except Exception as exc:
        row.last_error = str(exc)[:300]
        db.commit()
        raise ApiError(502, _error_code(exc), row.last_error) from exc
    state = _state(payload)
    row.status = state
    if state == "open":
        row.phone_number = _phone(payload) or row.phone_number
        row.last_error = None
        bind_evolution_channel(db)
        _register_webhook(settings, row)
    db.commit()
    db.refresh(row)
    return _public(row, _last_webhook(db, row.id))


def disconnect(db: Session, settings: Settings, connection_id: uuid.UUID) -> dict:
    row = _row(db, connection_id)
    client = client_for(settings.evolution_api_url, settings.evolution_api_key)
    try:
        client.logout(row.instance_name)
    except Exception as exc:
        row.last_error = str(exc)[:300]
    row.status = "disconnected"
    row.phone_number = None
    db.commit()
    db.refresh(row)
    return _public(row, _last_webhook(db, row.id))


def _row(db: Session, connection_id: uuid.UUID) -> ReachConnection:
    row = db.get(ReachConnection, connection_id)
    if row is None:
        raise ApiError(404, "not_found", "Connection not found.")
    return row


def published(db: Session) -> list[dict]:
    rows = list_connections(db)
    return [_public(row, _last_webhook(db, row.id)) for row in rows]


def _public(row: ReachConnection, last_webhook_at: datetime | None = None) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "instance_name": row.instance_name,
        "phone_number": row.phone_number,
        "status": row.status,
        "last_error": row.last_error,
        "qr_base64": None,
        "webhook_status": row.webhook_status,
        "webhook_registered_at": row.webhook_registered_at,
        "last_webhook_at": last_webhook_at,
        "updated_at": row.updated_at,
        "session_state": _session_state(row.status),
    }


def _require_healthy(settings: Settings) -> None:
    health = provider_health(settings)
    if health["status"] == "healthy":
        return
    code = {
        "authentication_error": "evolution_authentication",
        "not_configured": "evolution_not_configured",
    }.get(health["status"], "evolution_unavailable")
    raise ApiError(502, code, health["detail"] or "Evolution API could not be reached.")


def _error_code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if code == "authentication_error":
        return "evolution_authentication"
    if code == "not_configured":
        return "evolution_not_configured"
    return "evolution_unavailable"


def _session_state(status: str) -> str:
    if status == "open":
        return "open"
    if status == "qr":
        return "qr_pending"
    if status == "connecting":
        return "connecting"
    if status in {"close", "closed", "disconnected"}:
        return "disconnected"
    if status == "error":
        return "failed"
    return "not_connected"


def _register_webhook(settings: Settings, row: ReachConnection) -> None:
    """Points Evolution at this connection. A failed registration does not drop the QR session."""
    secret = (settings.evolution_webhook_secret or "").strip()
    base = (settings.public_base_url or "").rstrip("/")
    if not secret or not base:
        row.webhook_status = "error"
        row.last_error = "Set the public URL and webhook secret so delivery updates can arrive."
        return
    url = f"{base}/api/v1/reach/webhooks/evolution/{row.webhook_key}"
    client = client_for(settings.evolution_api_url, settings.evolution_api_key)
    try:
        client.set_webhook(row.instance_name, url, secret)
    except Exception as exc:
        row.webhook_status = "error"
        row.last_error = str(exc)[:300]
        return
    row.webhook_status = "registered"
    row.webhook_registered_at = datetime.now(UTC)
    if row.status == "open":
        row.last_error = None


def _last_webhook(db: Session, connection_id: uuid.UUID) -> datetime | None:
    return db.scalar(
        select(func.max(ReachWebhookEvent.created_at)).where(ReachWebhookEvent.connection_id == connection_id)
    )


def _qr(payload: dict) -> str | None:
    for key in ("base64", "qrcode", "code"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict):
            nested = value.get("base64") or value.get("code")
            if isinstance(nested, str):
                return nested
    return None


def _state(payload: dict) -> str:
    instance = payload.get("instance") if isinstance(payload.get("instance"), dict) else {}
    raw = str(instance.get("state") or payload.get("state") or payload.get("status") or "close").lower()
    if raw in {"open", "connected"}:
        return "open"
    if raw in {"connecting", "qr", "qrcode"}:
        return "qr"
    return "close"


def _phone(payload: dict) -> str | None:
    instance = payload.get("instance") if isinstance(payload.get("instance"), dict) else {}
    number = instance.get("wuid") or instance.get("owner") or payload.get("number")
    if not number:
        return None
    digits = "".join(ch for ch in str(number) if ch.isdigit())
    return digits or None
