import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize, require_device
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.schemas.devices import (
    ActivationKeyOut,
    ActivationPreflight,
    DeviceCreate,
    DeviceKeyOut,
    DeviceOut,
    DeviceSelfOut,
    RegisterCapacity,
)
from app.services import device_service, entitlement_service

router = APIRouter()

Db = Annotated[Session, Depends(get_db)]
CanManage = Annotated[Principal, Depends(authorize(Permission.DEVICES_MANAGE))]


@router.get("", response_model=list[DeviceOut])
def list_devices(db: Db, principal: CanManage, store_id: uuid.UUID | None = None) -> list[DeviceOut]:
    return device_service.list_devices(db, principal, store_id)


@router.post("", response_model=DeviceKeyOut, status_code=201)
def create_device(payload: DeviceCreate, db: Db, principal: CanManage) -> DeviceKeyOut:
    return device_service.create_device(db, principal, payload)


@router.get("/activation-preflight", response_model=ActivationPreflight)
def activation_preflight(principal: CanManage) -> ActivationPreflight:
    """Reports whether permanent entitlement signing can run. Does not create a key or a device."""
    _ = principal
    report = entitlement_service.signing_preflight()
    return ActivationPreflight(
        ready=report.ready,
        code=report.code,
        message=report.message,
        key_id=report.key_id,
        public_key=report.public_key,
    )


@router.get("/capacity", response_model=RegisterCapacity)
def capacity(db: Db, principal: CanManage) -> RegisterCapacity:
    _ = principal
    return device_service.register_capacity(db)


@router.get("/me", response_model=DeviceSelfOut)
def whoami(db: Db, principal: Annotated[Principal, Depends(require_device)]) -> DeviceSelfOut:
    if principal.device is None:
        raise ApiError(404, "shared_key", "This register uses the shared API key; register it to get its own series.")
    return device_service.self_info(db, principal.device)


@router.post("/{device_id}/rotate", response_model=DeviceKeyOut)
def rotate(device_id: uuid.UUID, db: Db, principal: CanManage) -> DeviceKeyOut:
    return device_service.rotate_key(db, principal, device_id)


@router.post("/{device_id}/activation-key", response_model=ActivationKeyOut, status_code=201)
def activation_key(device_id: uuid.UUID, db: Db, principal: CanManage) -> ActivationKeyOut:
    return device_service.issue_activation_key(db, principal, device_id)


@router.post("/{device_id}/revoke", response_model=DeviceOut)
def revoke(device_id: uuid.UUID, db: Db, principal: CanManage) -> DeviceOut:
    return device_service.revoke(db, principal, device_id)


@router.post("/{device_id}/release", response_model=DeviceOut)
def release(device_id: uuid.UUID, db: Db, principal: CanManage) -> DeviceOut:
    return device_service.release_device(db, principal, device_id)
