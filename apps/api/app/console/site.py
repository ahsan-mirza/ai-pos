"""The public site's WhatsApp number, edited in the console."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.console.security import OperatorPrincipal, audit_operator
from app.core.errors import ApiError
from app.schemas.site import SiteContactOut
from app.tenancy.models import SiteSettings

_ROW_ID = 1


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


def _row(db: Session) -> SiteSettings:
    row = db.get(SiteSettings, _ROW_ID)
    if row is None:
        row = SiteSettings(id=_ROW_ID, whatsapp="", updated_at=datetime.now(UTC))
        db.add(row)
        db.flush()
    return row


def read_contact(db: Session) -> SiteContactOut:
    return SiteContactOut(whatsapp=_row(db).whatsapp)


def set_contact(db: Session, operator: OperatorPrincipal, raw: str, reason: str) -> SiteContactOut:
    number = normalize_whatsapp(raw)
    row = _row(db)
    before = row.whatsapp
    row.whatsapp = number
    row.updated_at = datetime.now(UTC)
    audit_operator(
        db,
        operator,
        "site.whatsapp",
        before={"whatsapp": before},
        after={"whatsapp": number},
        reason=reason,
    )
    db.commit()
    return SiteContactOut(whatsapp=number)
