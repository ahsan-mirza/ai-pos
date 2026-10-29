"""Fashion rentals. The module gate is on the router; these checks are the user's own permission."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, get_principal
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.schemas.rentals import (
    AgreementOut,
    CustomerPick,
    ExtendIn,
    HandoverIn,
    RentalCreate,
    RentalOut,
    RentalPaymentIn,
    RentalPolicyIn,
    RentalPolicyOut,
    RentalQuote,
    RentalSummary,
    ReturnIn,
)
from app.services import rental_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]


def _principal(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
    if principal.user is None or principal.scope not in {"portal", "pos"}:
        raise ApiError(403, "forbidden", "Sign in to manage rentals.")
    allowed = {
        Permission.POS_ACCESS.value,
        Permission.PORTAL_INVENTORY_MANAGE.value,
        Permission.PORTAL_REPORTS_READ.value,
    }
    if not allowed.intersection(principal.permissions):
        raise ApiError(403, "forbidden", "You do not have permission for rentals.")
    return principal


def _require_manager(principal: Annotated[Principal, Depends(_principal)]) -> Principal:
    if Permission.PORTAL_INVENTORY_MANAGE.value not in principal.permissions:
        raise ApiError(403, "forbidden", "A manager has to approve this rental change.")
    return principal


Reader = Annotated[Principal, Depends(_principal)]
Manager = Annotated[Principal, Depends(_require_manager)]


def _store(principal: Principal, store_id: uuid.UUID | None) -> uuid.UUID | None:
    home = principal.store_id
    if home is not None and store_id is not None and store_id != home:
        raise ApiError(403, "store_forbidden", "This account can only use its own branch.")
    return home or store_id


@router.get("/products", response_model=list[RentalPolicyOut])
def products(db: Db, _: Reader) -> list[RentalPolicyOut]:
    return rental_service.list_policies(db)


@router.put("/products/{product_id}", response_model=RentalPolicyOut)
def save_product(db: Db, principal: Manager, product_id: uuid.UUID, body: RentalPolicyIn) -> RentalPolicyOut:
    saved = rental_service.save_policy(db, product_id, body)
    db.commit()
    return saved


@router.get("/customers", response_model=list[CustomerPick])
def customers(db: Db, _: Reader, q: Annotated[str, Query(min_length=1, max_length=80)]) -> list[CustomerPick]:
    return rental_service.search_customers(db, q)


@router.post("/quote", response_model=RentalQuote)
def quote(
    db: Db,
    principal: Reader,
    product_id: uuid.UUID,
    store_id: uuid.UUID,
    start_date: date,
    return_date: date,
    quantity: Annotated[int, Query(ge=1, le=100)] = 1,
    discount_cents: Annotated[int, Query(ge=0)] = 0,
) -> RentalQuote:
    branch = _store(principal, store_id)
    if branch is None:
        raise ApiError(422, "validation_error", "Choose a branch.")
    return rental_service.quote(
        db,
        product_id=product_id,
        store_id=branch,
        start=start_date,
        end=return_date,
        quantity=quantity,
        discount_cents=discount_cents,
    )


@router.get("", response_model=list[RentalOut])
def rentals(
    db: Db,
    principal: Reader,
    store_id: uuid.UUID | None = None,
    status: str | None = None,
    product_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    start: date | None = None,
    end: date | None = None,
    reference: Annotated[str | None, Query(max_length=20)] = None,
) -> list[RentalOut]:
    return rental_service.list_rentals(
        db,
        store_id=_store(principal, store_id),
        status=status,
        product_id=product_id,
        customer_id=customer_id,
        start=start,
        end=end,
        reference=reference,
    )


@router.get("/summary", response_model=RentalSummary)
def rental_summary(
    db: Db,
    principal: Reader,
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
    store_id: uuid.UUID | None = None,
) -> RentalSummary:
    return rental_service.summary(db, _store(principal, store_id), start, end)


@router.post("", response_model=RentalOut)
def create(db: Db, principal: Reader, body: RentalCreate) -> RentalOut:
    branch = _store(principal, body.store_id)
    if branch is None:
        raise ApiError(422, "validation_error", "Choose a branch.")
    body = body.model_copy(update={"store_id": branch})
    saved = rental_service.create_rental(db, body, principal.user)
    db.commit()
    return saved


@router.get("/{rental_id}", response_model=RentalOut)
def rental(db: Db, principal: Reader, rental_id: uuid.UUID) -> RentalOut:
    found = rental_service.get_rental(db, rental_id)
    _store(principal, found.store_id)
    return found


@router.get("/{rental_id}/agreement", response_model=AgreementOut)
def rental_agreement(db: Db, principal: Reader, rental_id: uuid.UUID) -> AgreementOut:
    found = rental_service.get_rental(db, rental_id)
    _store(principal, found.store_id)
    return rental_service.agreement(db, rental_id)


@router.post("/{rental_id}/payments", response_model=RentalOut)
def pay(db: Db, principal: Reader, rental_id: uuid.UUID, body: RentalPaymentIn) -> RentalOut:
    if body.kind in {"deposit_refund", "deduction"}:
        _require_manager(principal)
    saved = rental_service.apply_payment(db, rental_id, body, principal.user)
    db.commit()
    return saved


@router.post("/{rental_id}/ready", response_model=RentalOut)
def ready(db: Db, _: Reader, rental_id: uuid.UUID) -> RentalOut:
    saved = rental_service.mark_ready(db, rental_id)
    db.commit()
    return saved


@router.post("/{rental_id}/handover", response_model=RentalOut)
def handover(db: Db, principal: Reader, rental_id: uuid.UUID, body: HandoverIn) -> RentalOut:
    saved = rental_service.handover(db, rental_id, body, principal.user)
    db.commit()
    return saved


@router.post("/{rental_id}/return", response_model=RentalOut)
def returned(db: Db, principal: Reader, rental_id: uuid.UUID, body: ReturnIn) -> RentalOut:
    if body.waive_late or body.damage_cents:
        _require_manager(principal)
    saved = rental_service.return_rental(db, rental_id, body, principal.user)
    db.commit()
    return saved


@router.post("/{rental_id}/release", response_model=RentalOut)
def release(db: Db, _: Manager, rental_id: uuid.UUID) -> RentalOut:
    saved = rental_service.release(db, rental_id)
    db.commit()
    return saved


@router.post("/{rental_id}/extend", response_model=RentalOut)
def extend(db: Db, _: Reader, rental_id: uuid.UUID, body: ExtendIn) -> RentalOut:
    saved = rental_service.extend(db, rental_id, body)
    db.commit()
    return saved


@router.post("/{rental_id}/cancel", response_model=RentalOut)
def cancel(db: Db, _: Reader, rental_id: uuid.UUID) -> RentalOut:
    saved = rental_service.cancel(db, rental_id)
    db.commit()
    return saved
