"""Public marketing-site WhatsApp contact, edited in the console.

Click-to-chat only: the landing page opens wa.me and the visitor sends the message.
Replies stay in WhatsApp. Do not store Business Platform tokens or webhooks on this row.
"""

import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session

from app.console.security import OperatorPrincipal, audit_operator
from app.core.errors import ApiError
from app.schemas.site import SiteContactIn, SiteContactOut
from app.tenancy.models import WHATSAPP_TOOLTIP_DEFAULT, SiteSettings

_ROW_ID = 1
_CHANGED = "site_settings_changed"
# This process drops the cache on commit. The TTL covers a worker that did not see that commit.
CACHE_TTL_SECONDS = 30.0
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_whatsapp(raw: str) -> str:
    """Digits with the country code, or blank to hide the button. Spaces and a leading + are allowed."""
    text = raw.strip()
    if not text:
        return ""
    body = text[1:] if text.startswith("+") else text
    if any(character not in "0123456789 -()" for character in body):
        raise ApiError(422, "invalid_whatsapp", "Use the country code and digits, for example +971501234567.")
    digits = "".join(character for character in body if character.isdigit())
    if not 8 <= len(digits) <= 15:
        raise ApiError(422, "invalid_whatsapp", "Use the country code and digits, for example +971501234567.")
    return digits


def normalize_message(raw: str) -> str:
    text = raw.strip()
    if _CONTROL.search(text):
        raise ApiError(422, "invalid_whatsapp_message", "The welcome message cannot include control characters.")
    if len(text) > 500:
        raise ApiError(422, "invalid_whatsapp_message", "Keep the welcome message under 500 characters.")
    return text


def normalize_email(raw: str) -> str:
    """Public sales address for the footer, or blank to hide it."""
    text = raw.strip()
    if not text:
        return ""
    if _CONTROL.search(text) or len(text) > 254 or _EMAIL.fullmatch(text) is None:
        raise ApiError(422, "invalid_sales_email", "Enter a valid sales email, or leave it blank.")
    return text


def normalize_tooltip(raw: str) -> str:
    text = " ".join(raw.split())
    if _CONTROL.search(text):
        raise ApiError(422, "invalid_whatsapp_tooltip", "The button label cannot include control characters.")
    if len(text) > 40:
        raise ApiError(422, "invalid_whatsapp_tooltip", "Keep the button label under 40 characters.")
    return text or WHATSAPP_TOOLTIP_DEFAULT


def _row(db: Session) -> SiteSettings:
    row = db.get(SiteSettings, _ROW_ID)
    if row is None:
        row = SiteSettings(id=_ROW_ID, whatsapp="", updated_at=datetime.now(UTC))
        db.add(row)
        db.flush()
    return row


def _out(row: SiteSettings) -> SiteContactOut:
    return SiteContactOut(
        enabled=row.enabled,
        whatsapp=row.whatsapp,
        message=row.message,
        tooltip=row.tooltip or WHATSAPP_TOOLTIP_DEFAULT,
        email=row.email,
    )


def read_contact(db: Session) -> SiteContactOut:
    return _out(_row(db))


def set_contact(db: Session, operator: OperatorPrincipal, data: SiteContactIn) -> SiteContactOut:
    row = _row(db)
    provided = data.model_fields_set
    number = normalize_whatsapp(data.whatsapp) if "whatsapp" in provided else row.whatsapp
    enabled = data.enabled if "enabled" in provided else row.enabled
    message = normalize_message(data.message) if "message" in provided else row.message
    tooltip = normalize_tooltip(data.tooltip) if "tooltip" in provided else row.tooltip
    email = normalize_email(data.email) if "email" in provided else row.email
    if enabled and not number:
        raise ApiError(422, "whatsapp_required", "Enter the WhatsApp number before showing the button.")
    before = {
        "enabled": row.enabled,
        "whatsapp": row.whatsapp,
        "message": row.message,
        "tooltip": row.tooltip,
        "email": row.email,
    }
    row.enabled = enabled
    row.whatsapp = number
    row.message = message
    row.tooltip = tooltip
    row.email = email
    row.updated_at = datetime.now(UTC)
    after = {"enabled": enabled, "whatsapp": number, "message": message, "tooltip": tooltip, "email": email}
    audit_operator(db, operator, "site.whatsapp", before=before, after=after, reason=data.reason)
    result = SiteContactOut(enabled=enabled, whatsapp=number, message=message, tooltip=tooltip, email=email)
    db.commit()
    remember_contact(db, result)
    return result


@dataclass(frozen=True)
class _CacheEntry:
    expires_at: float
    value: SiteContactOut


_lock = threading.Lock()
_entries: dict[str, _CacheEntry] = {}


def _key(db: Session) -> str:
    return db.get_bind().url.render_as_string(hide_password=False)


def invalidate_contact_cache() -> None:
    with _lock:
        _entries.clear()


def lookup_contact(db: Session) -> SiteContactOut | None:
    now = time.monotonic()
    with _lock:
        entry = _entries.get(_key(db))
        if entry is None or entry.expires_at <= now:
            return None
        return entry.value.model_copy()


def remember_contact(db: Session, value: SiteContactOut) -> None:
    with _lock:
        _entries[_key(db)] = _CacheEntry(time.monotonic() + CACHE_TTL_SECONDS, value.model_copy())


@event.listens_for(Session, "after_flush")
def _track_site_settings(session: Session, _flush_context: object) -> None:
    if any(isinstance(obj, SiteSettings) for obj in (*session.new, *session.dirty, *session.deleted)):
        session.info[_CHANGED] = True


@event.listens_for(Session, "do_orm_execute")
def _track_bulk_site_settings(state: ORMExecuteState) -> None:
    if (state.is_update or state.is_delete) and state.bind_mapper is not None:
        if state.bind_mapper.class_ is SiteSettings:
            state.session.info[_CHANGED] = True


@event.listens_for(Session, "after_commit")
def _invalidate_site_settings(session: Session) -> None:
    if session.info.pop(_CHANGED, False):
        invalidate_contact_cache()


@event.listens_for(Session, "after_rollback")
def _forget_site_settings(session: Session) -> None:
    session.info.pop(_CHANGED, None)
