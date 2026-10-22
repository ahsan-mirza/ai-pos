import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.batches import SupplierCreate, SupplierOut
from app.schemas.payables import (
    BillCreate,
    BillFromReceipt,
    BillOut,
    PayablesSummary,
    SupplierBalance,
    SupplierPaymentCreate,
    SupplierPaymentOut,
    SupplierStatement,
    SupplierTerms,
    UnbilledReceipt,
)
from app.services import import_batch_service, payables_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanManage = Annotated[Principal, Depends(authorize(Permission.PAYABLES_MANAGE))]


def _user(principal: Principal) -> uuid.UUID | None:
    return principal.user.id if principal.user else None


@router.get("/summary", response_model=PayablesSummary)
def summary(db: Db, _: CanManage) -> PayablesSummary:
    return payables_service.summary(db)


@router.post("/suppliers", response_model=SupplierOut, status_code=201)
def create_supplier(payload: SupplierCreate, db: Db, _: CanManage) -> SupplierOut:
    return import_batch_service.create_supplier(db, payload)


@router.put("/suppliers/{supplier_id}", response_model=SupplierBalance)
def supplier_terms(supplier_id: uuid.UUID, payload: SupplierTerms, db: Db, _: CanManage) -> SupplierBalance:
    return payables_service.set_terms(db, supplier_id, payload)


@router.get("/suppliers/{supplier_id}/statement", response_model=SupplierStatement)
def statement(supplier_id: uuid.UUID, db: Db, _: CanManage) -> SupplierStatement:
    return payables_service.statement(db, supplier_id)


@router.get("/bills", response_model=list[BillOut])
def list_bills(
    db: Db,
    principal: CanManage,
    status: Literal["OPEN", "PARTIAL", "PAID", "VOID", "UNPAID"] | None = None,
    supplier_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[BillOut]:
    return payables_service.list_bills(
        db, status=status, supplier_id=supplier_id, store_scope=principal.store_id, limit=limit
    )


@router.post("/bills", response_model=BillOut, status_code=201)
def create_bill(payload: BillCreate, db: Db, principal: CanManage) -> BillOut:
    return payables_service.create_bill(db, payload, _user(principal))


@router.post("/bills/from-receipt", response_model=BillOut, status_code=201)
def bill_receipt(payload: BillFromReceipt, db: Db, principal: CanManage) -> BillOut:
    return payables_service.create_bill_from_receipt(db, payload, _user(principal))


@router.post("/bills/{bill_id}/void", response_model=BillOut)
def void_bill(bill_id: uuid.UUID, db: Db, _: CanManage) -> BillOut:
    return payables_service.void_bill(db, bill_id)


@router.get("/receipts/unbilled", response_model=list[UnbilledReceipt])
def unbilled(db: Db, principal: CanManage) -> list[UnbilledReceipt]:
    return payables_service.unbilled_receipts(db, principal.store_id)


@router.get("/payments", response_model=list[SupplierPaymentOut])
def list_payments(
    db: Db,
    _: CanManage,
    supplier_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[SupplierPaymentOut]:
    return payables_service.list_payments(db, supplier_id=supplier_id, limit=limit)


@router.post("/payments", response_model=SupplierPaymentOut, status_code=201)
def pay(payload: SupplierPaymentCreate, db: Db, principal: CanManage) -> SupplierPaymentOut:
    return payables_service.pay(db, payload, _user(principal))


@router.post("/payments/{payment_id}/clear", response_model=SupplierPaymentOut)
def clear(payment_id: uuid.UUID, db: Db, _: CanManage) -> SupplierPaymentOut:
    return payables_service.clear_cheque(db, payment_id)


@router.post("/payments/{payment_id}/void", response_model=SupplierPaymentOut)
def void_payment(
    payment_id: uuid.UUID, db: Db, _: CanManage, note: Annotated[str, Body(embed=True, max_length=200)] = ""
) -> SupplierPaymentOut:
    return payables_service.void_payment(db, payment_id, note)
