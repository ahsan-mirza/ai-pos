"""Customers added at the register: the `customer` sync event, offline-first like sales.

Registers create customers but never edit them. Credit terms and discounted price tiers are a manager's call: a
cashier without customers:manage gets the customer created on retail pricing with no credit, and a manager sets
the terms from the portal."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import SyncRejected
from app.core.permissions import Permission
from app.models.customer import Customer
from app.models.user import User
from app.schemas.wholesale import CustomerWrite, RegisterCustomerPayload
from app.services import customer_service
from app.services.sync_service import SyncContext, register_handler
from app.services.sync_validation import parse_payload


def apply_customer(db: Session, settings: Settings, payload: dict[str, object], ctx: SyncContext) -> uuid.UUID:
    data = parse_payload(RegisterCustomerPayload, payload)
    if db.get(Customer, data.id) is not None:
        return data.id
    creator = db.get(User, data.created_by_id)
    if creator is None or Permission.POS_ACCESS.value not in creator.permissions:
        raise SyncRejected("The cashier adding the customer cannot use a register.")
    values = data.model_dump(exclude={"id", "created_by_id"})
    if Permission.CUSTOMERS_MANAGE.value not in creator.permissions:
        values.update(price_tier="RETAIL", credit_limit_cents=0, payment_terms="DUE_ON_RECEIPT")
    customer = customer_service.new_customer(db, CustomerWrite(**values), customer_id=data.id)
    db.flush()
    return customer.id


register_handler("customer", apply_customer)
