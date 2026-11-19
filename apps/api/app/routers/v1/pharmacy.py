"""Pharmacy catalogue. Tenant comes from the signed-in session, never from the request body."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import REGISTER_SCOPES, Principal, authorize, authorize_any, get_principal
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.models.batch import BatchItem
from app.models.pharmacy_lots import PharmacySupplierReturnLine
from app.schemas.inventory import ProductCreate, ProductUpdate
from app.schemas.payloads import ProductOut
from app.schemas.pharmacy import PharmacyProductOut
from app.schemas.pharmacy_lots import (
    ConfirmedReason,
    GovernanceOut,
    LotDecisionOut,
    LotEventOut,
    PharmacistGrantIn,
    PharmacistOut,
    PharmacistSelfOut,
    QuarantineIn,
    QuarantineOut,
    RecallIn,
    RecallOut,
    RecallSaleOut,
    RecallSalesOut,
    RecallStatusIn,
    SupplierReturnIn,
    SupplierReturnLineOut,
    SupplierReturnOut,
)
from app.services import inventory, pharmacy_catalog, pharmacy_lots
from app.services.settings_service import business_currency

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanCatalogue = Annotated[
    Principal,
    Depends(
        authorize_any(
            Permission.PORTAL_INVENTORY_MANAGE,
            Permission.PHARMACY_CATALOGUE,
            scopes=REGISTER_SCOPES,
        )
    ),
]
CanStock = Annotated[Principal, Depends(authorize(Permission.PORTAL_INVENTORY_MANAGE, scopes=REGISTER_SCOPES))]
SignedIn = Annotated[Principal, Depends(get_principal)]


@router.get("/products", response_model=list[PharmacyProductOut])
def list_products(
    db: Db,
    _: CanCatalogue,
    q: Annotated[str, Query(max_length=80)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[PharmacyProductOut]:
    return pharmacy_catalog.list_products(db, query=q, limit=limit)


@router.get("/products/{product_id}", response_model=PharmacyProductOut)
def get_product(product_id: uuid.UUID, db: Db, _: CanCatalogue) -> PharmacyProductOut:
    return pharmacy_catalog.get_product(db, product_id)


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(payload: ProductCreate, db: Db, principal: CanCatalogue) -> ProductOut:
    if payload.pharmacy is None:
        raise ApiError(422, "pharmacy_required", "A pharmacy product needs its medicine details.")
    return inventory.create_product(db, principal, payload, business_currency(db))


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: uuid.UUID, payload: ProductUpdate, db: Db, principal: CanCatalogue) -> ProductOut:
    if payload.pharmacy is None:
        raise ApiError(422, "pharmacy_required", "Send the pharmacy details to update this product.")
    actor = None if principal.user is None else principal.user.id
    return inventory.update_product(db, product_id, payload, user_id=actor)


def _user_id(principal: Principal) -> uuid.UUID:
    if principal.user is None:
        raise ApiError(403, "forbidden", "This action requires a signed-in user.")
    return principal.user.id


def _confirm(payload: ConfirmedReason) -> str:
    if payload.confirm is not True:
        raise ApiError(422, "confirmation_required", "Confirm this action before it is saved.")
    return payload.reason


def _decision_out(row) -> PharmacistOut:
    return PharmacistOut(
        user_id=row.user_id,
        status=row.status,
        granted_at=row.granted_at.isoformat(),
        active=row.status == "ACTIVE",
    )


def _role_manager(principal: Principal) -> bool:
    return principal.has(Permission.ROLES_MANAGE)


def _decision(item: BatchItem) -> LotDecisionOut:
    return LotDecisionOut(
        batch_item_id=item.id,
        lot_status=item.lot_status or "",
        released_at=item.released_at.isoformat() if item.released_at is not None else None,
    )


@router.get("/pharmacist-authorization", response_model=PharmacistSelfOut)
def own_pharmacist_authorization(db: Db, principal: CanStock) -> PharmacistSelfOut:
    row = pharmacy_lots.active_pharmacist(db, _user_id(principal))
    return PharmacistSelfOut(authorized=row is not None)


@router.get("/governance", response_model=GovernanceOut)
def governance(db: Db, principal: SignedIn) -> GovernanceOut:
    _user_id(principal)
    return GovernanceOut.model_validate(
        pharmacy_lots.governance_snapshot(db, _user_id(principal), role_manager=_role_manager(principal))
    )


@router.post("/governance-officers", response_model=PharmacistOut, status_code=201)
def nominate_officer(payload: PharmacistGrantIn, db: Db, principal: SignedIn) -> PharmacistOut:
    row = pharmacy_lots.nominate_officer(
        db, _user_id(principal), payload.user_id, _confirm(payload), role_manager=_role_manager(principal)
    )
    return PharmacistOut(user_id=row.user_id, status=row.status, granted_at=row.requested_at.isoformat(), active=False)


@router.post("/governance-officers/{user_id}/confirm", response_model=PharmacistOut)
def confirm_officer(
    user_id: uuid.UUID, payload: ConfirmedReason, db: Db, principal: SignedIn
) -> PharmacistOut:
    row = pharmacy_lots.confirm_officer(
        db, _user_id(principal), user_id, _confirm(payload), role_manager=_role_manager(principal)
    )
    return PharmacistOut(user_id=row.user_id, status=row.status, granted_at=row.approved_at.isoformat(), active=True)


@router.post("/governance-officers/{user_id}/revoke", response_model=PharmacistOut)
def revoke_officer(
    user_id: uuid.UUID, payload: ConfirmedReason, db: Db, principal: SignedIn
) -> PharmacistOut:
    row = pharmacy_lots.revoke_officer(db, _user_id(principal), user_id, _confirm(payload))
    return PharmacistOut(user_id=row.user_id, status=row.status, granted_at=row.requested_at.isoformat(), active=False)


@router.post("/pharmacists", response_model=PharmacistOut, status_code=201)
def request_pharmacist(payload: PharmacistGrantIn, db: Db, principal: SignedIn) -> PharmacistOut:
    row = pharmacy_lots.request_pharmacist(db, _user_id(principal), payload.user_id, _confirm(payload))
    return _decision_out(row)


@router.post("/pharmacists/{user_id}/approve", response_model=PharmacistOut)
def approve_pharmacist(
    user_id: uuid.UUID, payload: ConfirmedReason, db: Db, principal: SignedIn
) -> PharmacistOut:
    row = pharmacy_lots.approve_pharmacist(db, _user_id(principal), user_id, _confirm(payload))
    return _decision_out(row)


@router.post("/pharmacists/{user_id}/reject", response_model=PharmacistOut)
def reject_pharmacist(
    user_id: uuid.UUID, payload: ConfirmedReason, db: Db, principal: SignedIn
) -> PharmacistOut:
    row = pharmacy_lots.reject_pharmacist(db, _user_id(principal), user_id, _confirm(payload))
    return _decision_out(row)


@router.post("/pharmacists/{user_id}/revoke", response_model=PharmacistOut)
def revoke_pharmacist(
    user_id: uuid.UUID, payload: ConfirmedReason, db: Db, principal: SignedIn
) -> PharmacistOut:
    row = pharmacy_lots.revoke_pharmacist(db, _user_id(principal), user_id, _confirm(payload))
    return _decision_out(row)


@router.post("/lots/{batch_item_id}/release", response_model=LotDecisionOut)
def release_lot(batch_item_id: uuid.UUID, payload: ConfirmedReason, db: Db, principal: CanStock) -> LotDecisionOut:
    if payload.confirm is not True:
        pharmacy_lots.note_failure(
            db,
            actor_id=_user_id(principal),
            action="pharmacy.lot_release_failed",
            action_type="LOT_RELEASE_FAILED",
            target_entity="BatchItem",
            target_id=batch_item_id,
            code="confirmation_required",
            reason=payload.reason,
        )
        raise ApiError(422, "confirmation_required", "Confirm this action before it is saved.")
    item = pharmacy_lots.release_lot(db, batch_item_id, _user_id(principal), payload.reason)
    return _decision(item)


@router.post("/lots/{batch_item_id}/clear-quarantine", response_model=LotDecisionOut)
def clear_quarantine(
    batch_item_id: uuid.UUID, payload: ConfirmedReason, db: Db, principal: CanStock
) -> LotDecisionOut:
    if payload.confirm is not True:
        pharmacy_lots.note_failure(
            db,
            actor_id=_user_id(principal),
            action="pharmacy.lot_clearance_failed",
            action_type="LOT_CLEARANCE_FAILED",
            target_entity="BatchItem",
            target_id=batch_item_id,
            code="confirmation_required",
            reason=payload.reason,
        )
        raise ApiError(422, "confirmation_required", "Confirm this action before it is saved.")
    item = pharmacy_lots.clear_quarantine(db, batch_item_id, _user_id(principal), payload.reason)
    return _decision(item)


@router.get("/lots/{batch_item_id}/events", response_model=list[LotEventOut])
def lot_events(batch_item_id: uuid.UUID, db: Db, _: CanStock) -> list[LotEventOut]:
    return [
        LotEventOut(
            action=event.action,
            from_status=event.from_status,
            to_status=event.to_status,
            reason=event.reason,
            user_name=name,
            created_at=event.created_at.isoformat(),
        )
        for event, name in pharmacy_lots.lot_events(db, batch_item_id)
    ]


@router.post("/lots/{batch_item_id}/quarantine", response_model=QuarantineOut)
def quarantine_lot(batch_item_id: uuid.UUID, payload: QuarantineIn, db: Db, principal: CanStock) -> QuarantineOut:
    item = pharmacy_lots.quarantine_lot(db, batch_item_id, payload.reason, _user_id(principal))
    return QuarantineOut(
        batch_item_id=item.id,
        lot_status=item.lot_status or "QUARANTINED",
        quarantine_reason=item.quarantine_reason or payload.reason,
    )


@router.post("/supplier-returns", response_model=SupplierReturnOut, status_code=201)
def supplier_return(payload: SupplierReturnIn, db: Db, principal: CanStock) -> SupplierReturnOut:
    document = pharmacy_lots.return_to_supplier(
        db,
        reference=payload.reference,
        reason=payload.reason,
        lines=[(line.batch_item_id, line.quantity) for line in payload.lines],
        user_id=_user_id(principal),
    )
    rows = db.execute(
        select(PharmacySupplierReturnLine, BatchItem)
        .join(BatchItem, BatchItem.id == PharmacySupplierReturnLine.batch_item_id)
        .where(PharmacySupplierReturnLine.return_id == document.id)
        .order_by(PharmacySupplierReturnLine.created_at, PharmacySupplierReturnLine.id)
    ).all()
    return SupplierReturnOut(
        id=document.id,
        reference=document.reference,
        reason=document.reason,
        lines=[
            SupplierReturnLineOut(
                batch_item_id=line.batch_item_id,
                product_id=line.product_id,
                quantity=line.quantity,
                quantity_remaining=item.quantity_remaining,
                lot_status=item.lot_status,
            )
            for line, item in rows
        ],
    )


@router.post("/recalls", response_model=RecallOut, status_code=201)
def open_recall(payload: RecallIn, db: Db, principal: CanStock) -> RecallOut:
    recall = pharmacy_lots.open_recall(
        db,
        reference=payload.reference,
        source_text=payload.source_text,
        severity=payload.severity,
        reason=payload.reason,
        lots=[(lot.product_id, lot.manufacturer_lot) for lot in payload.lots],
        user_id=_user_id(principal),
    )
    blocked = int(db.scalar(select(func.count()).select_from(BatchItem).where(BatchItem.recall_id == recall.id)) or 0)
    return RecallOut(
        id=recall.id,
        reference=recall.reference,
        status=recall.status,
        severity=recall.severity,
        layers_recalled=blocked,
    )


@router.post("/recalls/{recall_id}/status", response_model=RecallOut)
def recall_status(recall_id: uuid.UUID, payload: RecallStatusIn, db: Db, principal: CanStock) -> RecallOut:
    recall = pharmacy_lots.set_recall_status(db, recall_id, payload.status.strip().upper(), _user_id(principal))
    blocked = int(db.scalar(select(func.count()).select_from(BatchItem).where(BatchItem.recall_id == recall.id)) or 0)
    return RecallOut(
        id=recall.id,
        reference=recall.reference,
        status=recall.status,
        severity=recall.severity,
        layers_recalled=blocked,
    )


@router.get("/recalls/{recall_id}/sales", response_model=RecallSalesOut)
def recall_sales(
    recall_id: uuid.UUID,
    db: Db,
    _: CanStock,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> RecallSalesOut:
    rows, total = pharmacy_lots.recall_sales(db, recall_id, offset=offset, limit=limit)
    return RecallSalesOut(
        total=total,
        sales=[
            RecallSaleOut(
                sale_id=sale.id,
                invoice_number=sale.invoice_number,
                sale_item_id=item.id,
                batch_item_id=allocation.batch_item_id,
                quantity=allocation.quantity,
                quantity_returned=allocation.quantity_returned,
            )
            for allocation, item, sale in rows
        ],
    )
