import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize, get_principal
from app.core.errors import ApiError
from app.core.permissions import Permission
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
from app.services import settings_service

router = APIRouter()


@router.get("", response_model=BusinessSettingsOut)
def read_settings(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> BusinessSettingsOut:
    settings = settings_service.cached_settings(db)
    device = principal.device
    settings_service.note_register_entitlement(
        db,
        device.id if device is not None else None,
        settings.entitlement_revision,
        device.entitlement_revision if device is not None else None,
    )
    db.commit()
    return settings_service.settings_out(settings)


@router.put("/currency", response_model=BusinessSettingsOut)
def update_currency(
    payload: CurrencyUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
) -> BusinessSettingsOut:
    if principal.user is None or principal.store_id is not None:
        raise ApiError(403, "forbidden", "Only a business-wide administrator can change the currency.")
    return settings_service.change_currency(db, principal.user, payload.currency)


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
