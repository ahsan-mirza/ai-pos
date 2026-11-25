"""SKU is required outside Restaurant and Cafe. A blank menu SKU is stored as null."""

from sqlalchemy.orm import Session

from app.core.errors import ApiError

MENU_PROFILES = frozenset({"restaurant", "cafe"})


def menu_sku_optional(db: Session) -> bool:
    from app.services.settings_service import load_settings

    return load_settings(db).business_profile in MENU_PROFILES


def stored_sku(db: Session, raw: str | None) -> str | None:
    text = (raw or "").strip()
    if text:
        return text
    if menu_sku_optional(db):
        return None
    raise ApiError(422, "sku_required", "SKU is required.", details={"fields": {"sku": "SKU is required."}})
