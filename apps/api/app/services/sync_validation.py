import uuid

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.core.errors import SyncRejected
from app.core.permissions import Permission
from app.models.store import Store
from app.models.user import User


def parse_payload[TModel: BaseModel](model: type[TModel], payload: dict[str, object]) -> TModel:
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        message = "Payload is invalid."
        errors = exc.errors()
        if errors:
            message = str(errors[0].get("msg", message))
        raise SyncRejected(message) from exc


def require_store(db: Session, store_id: uuid.UUID) -> Store:
    store = db.get(Store, store_id)
    if store is None:
        raise SyncRejected("Store does not exist.")
    return store


def require_cashier(db: Session, cashier_id: uuid.UUID, store_id: uuid.UUID) -> User:
    cashier = db.get(User, cashier_id)
    if cashier is None:
        raise SyncRejected("Cashier does not exist.")
    # Offline sales can sync after the cashier was disabled; the sale still happened, so is_active is not checked.
    if Permission.POS_ACCESS.value not in cashier.permissions:
        raise SyncRejected("Cashier does not have POS access.")
    if cashier.store_id is not None and cashier.store_id != store_id:
        raise SyncRejected("Cashier is not assigned to this store.")
    return cashier
