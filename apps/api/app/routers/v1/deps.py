import re
import uuid
from typing import Annotated

from fastapi import Header

from app.core.deps import Principal
from app.core.errors import ApiError

_DEVICE = re.compile(r"[A-Za-z0-9:_.-]{1,64}")
_IDEMPOTENCY = re.compile(r"[A-Za-z0-9:_.-]{8,128}")


def require_device_id(x_device_id: Annotated[str, Header(alias="X-Device-Id")]) -> str:
    if _DEVICE.fullmatch(x_device_id) is None:
        raise ApiError(422, "invalid_request", "X-Device-Id is invalid.")
    return x_device_id


def assert_store_access(principal: Principal, store_id: uuid.UUID) -> None:
    if principal.store_id is not None and principal.store_id != store_id:
        raise ApiError(403, "store_scope", "You can only change records in your own store.")


def require_idempotency_key(idempotency_key: Annotated[str, Header(alias="Idempotency-Key")]) -> str:
    if _IDEMPOTENCY.fullmatch(idempotency_key) is None:
        raise ApiError(422, "invalid_request", "Idempotency-Key is invalid.")
    return idempotency_key
