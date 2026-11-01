"""WhatsApp connections on the central Evolution API. One instance per connection."""

from __future__ import annotations

import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from reach.models import ReachConnection
from reach.providers.evolution.client import client_for
from reach.service import require_reach


def list_connections(db: Session) -> list[ReachConnection]:
    require_reach(db)
    return list(db.scalars(select(ReachConnection).order_by(ReachConnection.created_at.desc())))


def create_connection(db: Session, settings: Settings, name: str) -> ReachConnection:
    require_reach(db)
    instance = f"reach-{uuid.uuid4().hex[:12]}"
    client = client_for(settings.evolution_api_url, settings.evolution_api_key)
    try:
        client.create_instance(instance)
    except Exception as exc:
        raise ApiError(502, "evolution_unavailable", str(exc)[:300]) from exc
    row = ReachConnection(
        name=name.strip(),
        instance_name=instance,
        status="created",
        webhook_key=secrets.token_urlsafe(32),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def connect(db: Session, settings: Settings, connection_id: uuid.UUID) -> dict:
    row = _row(db, connection_id)
    client = client_for(settings.evolution_api_url, settings.evolution_api_key)
    try:
        payload = client.connect(row.instance_name)
    except Exception as exc:
        row.status = "error"
        row.last_error = str(exc)[:300]
        db.commit()
        raise ApiError(502, "evolution_unavailable", row.last_error) from exc
    row.status = "qr"
    row.last_error = None
    db.commit()
    db.refresh(row)
    return {**_public(row), "qr_base64": _qr(payload)}


def refresh_status(db: Session, settings: Settings, connection_id: uuid.UUID) -> dict:
    row = _row(db, connection_id)
    client = client_for(settings.evolution_api_url, settings.evolution_api_key)
    try:
        payload = client.status(row.instance_name)
    except Exception as exc:
        row.last_error = str(exc)[:300]
        db.commit()
        raise ApiError(502, "evolution_unavailable", row.last_error) from exc
    state = _state(payload)
    row.status = state
    if state == "open":
        row.phone_number = _phone(payload) or row.phone_number
        row.last_error = None
    db.commit()
    db.refresh(row)
    return _public(row)


def disconnect(db: Session, settings: Settings, connection_id: uuid.UUID) -> dict:
    row = _row(db, connection_id)
    client = client_for(settings.evolution_api_url, settings.evolution_api_key)
    try:
        client.logout(row.instance_name)
    except Exception as exc:
        row.last_error = str(exc)[:300]
    row.status = "disconnected"
    db.commit()
    db.refresh(row)
    return _public(row)


def _row(db: Session, connection_id: uuid.UUID) -> ReachConnection:
    require_reach(db)
    row = db.get(ReachConnection, connection_id)
    if row is None:
        raise ApiError(404, "not_found", "Connection not found.")
    return row


def _public(row: ReachConnection) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "instance_name": row.instance_name,
        "phone_number": row.phone_number,
        "status": row.status,
        "last_error": row.last_error,
        "qr_base64": None,
    }


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
