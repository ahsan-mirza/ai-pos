import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize, require_device
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.schemas.devices import ActivationKeyOut, DeviceCreate, DeviceKeyOut, DeviceOut, DeviceSelfOut
from app.services import device_service

router = APIRouter()

Db = Annotated[Session, Depends(get_db)]
CanManage = Annotated[Principal, Depends(authorize(Permission.DEVICES_MANAGE))]


@router.get("", response_model=list[DeviceOut])
def list_devices(db: Db, principal: CanManage, store_id: uuid.UUID | None = None) -> list[DeviceOut]:
    return device_service.list_devices(db, principal, store_id)


@router.post("", response_model=DeviceKeyOut, status_code=201)
def create_device(payload: DeviceCreate, db: Db, principal: CanManage) -> DeviceKeyOut:
    return device_service.create_device(db, principal, payload)


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
