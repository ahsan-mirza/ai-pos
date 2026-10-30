import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize, get_principal
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.schemas.currencies import ConvertResult, RateBoard
from app.schemas.module_settings import ModuleSettings
from app.schemas.pos_policy import PosPolicy
from app.schemas.receipt import ReceiptProfileOut, ReceiptSettings
from app.schemas.settings import (
    AppearanceUpdate,
    BusinessSettingsOut,
    CurrencyUpdate,
    ProfileUpdate,
    TaxSettingsUpdate,
)
from app.services import fx_service, settings_service
from app.services.fx_service import QuoteUnavailable

router = APIRouter()


@router.get("/country-tax/{code}")
def read_country_tax(code: str) -> dict[str, object]:
    from app.tenancy.countries import COUNTRY_CURRENCIES
    from app.tenancy.country_tax import as_dict, describe

    if code.upper() not in COUNTRY_CURRENCIES:
        raise ApiError(404, "not_found", "That country is not in the list.")
    return as_dict(describe(code))


@router.get("", response_model=BusinessSettingsOut)
def read_settings(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
    x_pending_sales: Annotated[str | None, Header(alias="X-Pending-Sales")] = None,
) -> BusinessSettingsOut:
    if principal.kind == "device":
        device_id = str(principal.device.id) if principal.device is not None else "shared"
        settings_service.note_offline_pending(device_id, x_pending_sales)
    settings = settings_service.cached_settings(db)
    device = principal.device
    settings_service.note_register_entitlement(
        db,
        device.id if device is not None else None,
        settings.entitlement_revision,
        device.entitlement_revision if device is not None else None,
    )
    db.commit()
    out = settings_service.settings_out(settings)
    if principal.store_id is None:
        return out
    from app.services.branch_tax import overlay_settings

    return overlay_settings(db, principal.store_id, out)  # type: ignore[return-value]


@router.put("/currency", response_model=BusinessSettingsOut)
def update_currency(
    payload: CurrencyUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
) -> BusinessSettingsOut:
    if principal.user is None or principal.store_id is not None:
        raise ApiError(403, "forbidden", "Only a business-wide administrator can change the currency.")
    return settings_service.change_currency(db, principal.user, payload.currency)


@router.get("/exchange-rates", response_model=RateBoard)
def exchange_rates(
    principal: Annotated[Principal, Depends(get_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
    source: Annotated[str, Query(min_length=3, max_length=3)],
    amount_cents: Annotated[int, Query(ge=0, le=10**14)] = 0,
    refresh: Annotated[bool, Query()] = False,
) -> RateBoard:
    """Live or saved rates for the currencies this business can use. Does not change prices."""
    del principal
    return fx_service.rate_board(settings, source, amount_cents, refresh=refresh)


@router.get("/exchange-rates/convert", response_model=ConvertResult)
def convert_currency(
    principal: Annotated[Principal, Depends(get_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
    source: Annotated[str, Query(min_length=3, max_length=3)],
    target: Annotated[str, Query(min_length=3, max_length=3)],
    amount_cents: Annotated[int, Query(ge=0, le=10**14)],
    refresh: Annotated[bool, Query()] = False,
) -> ConvertResult:
    del principal
    try:
        return fx_service.convert(amount_cents, source, target, settings, refresh=refresh)
    except QuoteUnavailable as exc:
        raise ApiError(503, "rate_unavailable", exc.message) from exc


@router.put("/appearance", response_model=BusinessSettingsOut)
def update_appearance(
    payload: AppearanceUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
) -> BusinessSettingsOut:
    if principal.user is None or principal.store_id is not None:
        raise ApiError(403, "forbidden", "Only a business-wide administrator can change the brand color.")
    return settings_service.change_appearance(db, principal.user, payload)


@router.put("/profile", response_model=BusinessSettingsOut)
def update_profile(
    payload: ProfileUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
) -> BusinessSettingsOut:
    if principal.user is None or principal.store_id is not None:
        raise ApiError(403, "forbidden", "Only a business-wide administrator can change the business type.")
    return settings_service.change_profile(db, principal.user, payload)


@router.put("/modules", response_model=BusinessSettingsOut)
def update_module_settings(
    payload: ModuleSettings,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
) -> BusinessSettingsOut:
    if principal.user is None or principal.store_id is not None:
        raise ApiError(403, "forbidden", "Only a business-wide administrator can change module settings.")
    return settings_service.change_module_settings(db, principal.user, payload)


@router.put("/pos-policy", response_model=BusinessSettingsOut)
def update_pos_policy(
    payload: PosPolicy,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
) -> BusinessSettingsOut:
    if principal.user is None or principal.store_id is not None:
        raise ApiError(403, "forbidden", "Only a business-wide administrator can change the till rules.")
    return settings_service.change_pos_policy(db, principal.user, payload)


@router.get("/receipt", response_model=ReceiptProfileOut)
def read_receipt(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
    store_id: Annotated[uuid.UUID | None, Query(description="Branch whose address and phone to include")] = None,
) -> ReceiptProfileOut:
    profile = settings_service.receipt_profile(db, store_id or principal.store_id)
    db.commit()
    return profile


@router.put("/receipt", response_model=ReceiptProfileOut)
def update_receipt(
    payload: ReceiptSettings,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
) -> ReceiptProfileOut:
    if principal.user is None or principal.store_id is not None:
        raise ApiError(403, "forbidden", "Only a business-wide administrator can change the receipt layout.")
    return settings_service.change_receipt(db, principal.user, payload)


@router.put("/tax", response_model=BusinessSettingsOut)
def update_tax(
    payload: TaxSettingsUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
) -> BusinessSettingsOut:
    if principal.user is None or principal.store_id is not None:
        raise ApiError(403, "forbidden", "Only a business-wide administrator can change VAT settings.")
    return settings_service.change_tax(db, principal.user, payload)
