"""Medicine lot identity and lifecycle on the existing cost layer.

Stock quantity changes go through inventory.move_stock. This module stamps lot
status and appends batch_item_events in the same transaction.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, has_capability
from app.core.errors import ApiError
from app.models.batch import BatchAllocation, BatchItem, PurchaseBatch
from app.models.inventory import StockMovement
from app.models.pharmacy import PharmacyProductDetails
from app.models.pharmacy_lots import (
    RECALL_STATUSES,
    BatchItemEvent,
    PharmacistAuthorization,
    PharmacyGovernanceOfficer,
    PharmacyRecall,
    PharmacyRecallLot,
    PharmacySupplierReturn,
    PharmacySupplierReturnLine,
)
from app.models.user import User
from app.models.sale import Sale
from app.models.sale_item import SaleItem

UNRELEASED = "UNRELEASED"
RELEASED = "RELEASED"


def lot_controlled_ids(db: Session, product_ids: list[uuid.UUID] | set[uuid.UUID]) -> set[uuid.UUID]:
    """Medicines are lot-controlled only when this tenant has the pharmacy catalogue and FEFO."""
    ids = list(product_ids)
    if not ids:
        return set()
    if not has_capability(db, Capability.PHARMACY_CATALOG) or not has_capability(db, Capability.FEFO):
        return set()
    return set(
        db.scalars(
            select(PharmacyProductDetails.product_id).where(
                PharmacyProductDetails.product_id.in_(ids),
                PharmacyProductDetails.product_kind == "MEDICINE",
            )
        ).all()
    )


def is_lot_controlled(db: Session, product_id: uuid.UUID) -> bool:
    return product_id in lot_controlled_ids(db, [product_id])


def lot_problems(
    manufacturer_lot: str | None,
    manufactured_on: date | None,
    expiry_date: date | None,
) -> list[str]:
    """Problems that reject a medicine receipt. An empty list means the lot can be stored."""
    problems: list[str] = []
    lot = (manufacturer_lot or "").strip()
    if not lot:
        problems.append("Manufacturer lot is required for a medicine.")
    elif len(lot) > 64:
        problems.append("Manufacturer lot must be 64 characters or fewer.")
    if expiry_date is None:
        problems.append("Expiry date is required for a medicine.")
    if manufactured_on is not None and expiry_date is not None and manufactured_on > expiry_date:
        problems.append("Manufacture date cannot be after the expiry date.")
    return problems


def release_for_sale(db: Session, item: BatchItem, user_id: uuid.UUID | None) -> None:
    """Move one received lot to RELEASED so the register can sell it."""
    if item.lot_status != UNRELEASED:
        return
    previous = item.lot_status
    item.lot_status = RELEASED
    _event(db, item, action="RELEASED", from_status=previous, to_status=RELEASED, user_id=user_id)


def record_received(
    db: Session,
    item: BatchItem,
    *,
    manufacturer_lot: str | None,
    manufactured_on: date | None,
    expiry_date: date | None,
    user_id: uuid.UUID | None,
) -> None:
    """Stamp a new layer as an unreleased medicine lot and append the receiving event.

    Does not change quantity_imported, quantity_remaining, or inventory_levels.
    """
    problems = lot_problems(manufacturer_lot, manufactured_on, expiry_date)
    if problems:
        raise ApiError(422, "lot_required", problems[0])
    assert manufacturer_lot is not None
    assert expiry_date is not None
    item.manufacturer_lot = manufacturer_lot.strip()
    item.manufactured_on = manufactured_on
    item.expiry_date = expiry_date
    item.lot_status = UNRELEASED
    _event(db, item, action="RECEIVED", from_status=None, to_status=UNRELEASED, user_id=user_id)
    _apply_open_recall(db, item, user_id)
    db.flush()


def transfer_candidates(items: list[BatchItem], on: date | None = None) -> list[BatchItem]:
    """Released, in-date medicine layers, soonest expiry first.

    Grocery fefo_order is not used. Expired, unreleased, quarantined, recalled,
    damaged, and supplier-returned layers are left out.
    """
    from app.services.batch_ledger import today

    day = on or today()
    chosen: list[BatchItem] = []
    for item in items:
        if item.lot_status != RELEASED:
            continue
        if item.expiry_date is None or item.expiry_date < day:
            continue
        if item.manufactured_on is not None and item.manufactured_on > item.expiry_date:
            continue
        chosen.append(item)
    chosen.sort(key=lambda item: (item.expiry_date or day, item.created_at, item.id))
    return chosen


def strict_sale_candidates(items: list[BatchItem], on: date | None = None) -> list[BatchItem]:
    """Released in-date layers for a medicine sale, soonest expiry first.

    A null status is not released, and a null expiry is not eligible. Expired,
    quarantined, recalled, damaged, and supplier-returned layers are left out.
    Grocery fefo_order is not used.
    """
    from app.services.batch_ledger import today

    day = on or today()
    chosen = [
        item
        for item in items
        if item.lot_status == RELEASED
        and item.expiry_date is not None
        and item.expiry_date >= day
        and item.quantity_remaining > 0
    ]
    chosen.sort(key=lambda item: (item.expiry_date, item.created_at, item.id))
    return chosen


def explain_shortage(items: list[BatchItem], product_name: str) -> tuple[str, str]:
    """Why a medicine sale cannot be filled. Messages name only this tenant's product.

    Precedence, after the branch on-hand check in move_stock: eligible lots that
    still cannot cover the quantity, then no remaining quantity, then one status
    shared by every positive layer, then released stock that is only expired.
    An expired layer that was never released is lot_unreleased. A zero-quantity
    supplier return is insufficient stock, not lot_supplier_return.
    """
    from app.services.batch_ledger import today

    name = product_name or "This medicine"
    if strict_sale_candidates(items):
        return (
            "insufficient_released_stock",
            f"Not enough released stock of {name} before expiry.",
        )
    day = today()
    positive = [item for item in items if item.quantity_remaining > 0]
    if not positive:
        return (
            "insufficient_released_stock",
            f"Not enough released stock of {name} before expiry.",
        )
    statuses = {item.lot_status for item in positive}
    if statuses == {UNRELEASED}:
        return "lot_unreleased", f"{name} is not released for sale."
    if statuses == {"QUARANTINED"}:
        return "lot_quarantined", f"{name} is quarantined and cannot be sold."
    if statuses == {"RECALLED"}:
        return "lot_recalled", f"{name} is recalled and cannot be sold."
    if statuses == {"DAMAGED"}:
        return "lot_damaged", f"{name} is damaged and cannot be sold."
    if statuses == {"SUPPLIER_RETURN"}:
        return "lot_supplier_return", f"{name} was returned to the supplier and cannot be sold."
    if all(
        item.lot_status == RELEASED and item.expiry_date is not None and item.expiry_date < day for item in positive
    ):
        return "lot_expired", f"{name} has only expired stock."
    return "lot_ineligible", f"{name} has no released in-date lot."


def eligible_quantities(
    db: Session, product_ids: list[uuid.UUID] | set[uuid.UUID], store_id: uuid.UUID | None
) -> dict[uuid.UUID, int]:
    """Released in-date units. Informational for stock screens; checkout rechecks under a lock."""
    ids = list(product_ids)
    if not ids:
        return {}
    from app.services.batch_ledger import today

    statement = (
        select(BatchItem.product_id, func.coalesce(func.sum(BatchItem.quantity_remaining), 0))
        .where(
            BatchItem.product_id.in_(ids),
            BatchItem.lot_status == RELEASED,
            BatchItem.expiry_date.is_not(None),
            BatchItem.expiry_date >= today(),
            BatchItem.quantity_remaining > 0,
        )
        .group_by(BatchItem.product_id)
    )
    if store_id is not None:
        statement = statement.where(BatchItem.store_id == store_id)
    return {product_id: int(quantity) for product_id, quantity in db.execute(statement).all()}


def record_transfer_shipped(db: Session, movement: StockMovement, user_id: uuid.UUID | None) -> None:
    """Append TRANSFER_OUT for each source layer this shipment drew. Status is unchanged."""
    if movement.movement_type != "TRANSFER_OUT" or not is_lot_controlled(db, movement.product_id):
        return
    allocations = db.scalars(
        select(BatchAllocation).where(BatchAllocation.stock_movement_id == movement.id)
    ).all()
    for allocation in allocations:
        item = db.get(BatchItem, allocation.batch_item_id)
        if item is None or item.lot_status is None:
            continue
        _event(
            db,
            item,
            action="TRANSFER_OUT",
            from_status=item.lot_status,
            to_status=item.lot_status,
            reason=movement.note or None,
            user_id=user_id,
        )
    db.flush()


def open_transfer_destination(
    db: Session,
    *,
    transfer_id: uuid.UUID,
    transfer_number: str,
    line_position: int,
    product_id: uuid.UUID,
    destination_store_id: uuid.UUID,
    quantity: int,
    user_id: uuid.UUID,
    currency: str,
) -> list[BatchItem]:
    """Open one UNRELEASED destination layer per source allocation. On-hand is already posted."""
    if not is_lot_controlled(db, product_id):
        return []
    rows = db.execute(
        select(BatchAllocation, BatchItem)
        .join(StockMovement, StockMovement.id == BatchAllocation.stock_movement_id)
        .join(BatchItem, BatchItem.id == BatchAllocation.batch_item_id)
        .where(
            StockMovement.reference_type == "stock_transfer",
            StockMovement.reference_id == transfer_id,
            StockMovement.movement_type == "TRANSFER_OUT",
            StockMovement.product_id == product_id,
        )
        .order_by(BatchAllocation.created_at, BatchAllocation.id)
    ).all()
    covered = sum(allocation.quantity for allocation, _source in rows)
    if covered != quantity:
        raise ApiError(422, "lot_trace_missing", "This medicine transfer is missing its source lot allocation.")
    opened: list[BatchItem] = []
    for index, (allocation, source) in enumerate(rows, start=1):
        batch = PurchaseBatch(
            batch_number=f"{transfer_number}-{line_position + 1}-{index}"[:32],
            store_id=destination_store_id,
            import_source="TRANSFER",
            total_cost_amount=allocation.quantity * source.purchase_cost_per_unit,
            total_items_count=allocation.quantity,
            currency=currency,
            status="ACTIVE",
            notes=f"Transfer {transfer_number}"[:1000],
            created_by_id=user_id,
        )
        db.add(batch)
        db.flush()
        item = BatchItem(
            batch_id=batch.id,
            product_id=product_id,
            store_id=destination_store_id,
            quantity_imported=allocation.quantity,
            quantity_remaining=allocation.quantity,
            purchase_cost_per_unit=source.purchase_cost_per_unit,
            selling_price_per_unit=source.selling_price_per_unit,
            expiry_date=source.expiry_date,
            manufacturer_lot=source.manufacturer_lot,
            manufactured_on=source.manufactured_on,
            lot_status=UNRELEASED,
            source_batch_item_id=source.id,
        )
        db.add(item)
        db.flush()
        _event(db, item, action="TRANSFER_IN", from_status=None, to_status=UNRELEASED, user_id=user_id)
        _apply_open_recall(db, item, user_id)
        opened.append(item)
    db.flush()
    return opened


CUSTOMER_RETURN_HOLD = "Customer return. These units are not released for resale."


def hold_customer_return(
    db: Session, *, sale_item_id: uuid.UUID, store_id: uuid.UUID, user_id: uuid.UUID | None
) -> None:
    """Put a released medicine layer on hold after a customer return. Does not commit.

    The whole layer is held, including units that were not returned. A recalled,
    quarantined, unreleased, damaged, or supplier-return layer keeps its status.
    """
    from app.services import audit

    sold = db.get(SaleItem, sale_item_id)
    if sold is None or not is_lot_controlled(db, sold.product_id):
        return
    layers = db.scalars(
        select(BatchItem)
        .join(BatchAllocation, BatchAllocation.batch_item_id == BatchItem.id)
        .where(
            BatchAllocation.sale_item_id == sale_item_id,
            BatchItem.store_id == store_id,
            BatchItem.lot_status == RELEASED,
        )
    ).unique().all()
    for item in layers:
        previous = item.lot_status
        item.lot_status = "QUARANTINED"
        item.quarantine_reason = CUSTOMER_RETURN_HOLD
        _event(
            db,
            item,
            action="QUARANTINED",
            from_status=previous,
            to_status="QUARANTINED",
            reason=CUSTOMER_RETURN_HOLD,
            user_id=user_id,
        )
        audit.record(
            db,
            action_type="LOT_QUARANTINED",
            action="pharmacy.lot_quarantined",
            target_entity="BatchItem",
            target_entity_id=item.id,
            store_id=item.store_id,
            user_id=user_id,
            reason_notes=CUSTOMER_RETURN_HOLD,
            old_values={"lot_status": previous},
            new_values={"lot_status": "QUARANTINED"},
        )
    if layers:
        db.flush()


def quarantine_lot(db: Session, batch_item_id: uuid.UUID, reason: str, user_id: uuid.UUID | None) -> BatchItem:
    """Hold a medicine layer. This does not release stock and cannot clear a recall."""
    from app.services import audit

    cleaned = audit.require_reason(reason, "quarantine")
    item = _medicine_layer(db, batch_item_id)
    if item.lot_status == "RECALLED":
        raise ApiError(422, "lot_recalled", "A recalled lot cannot be released or cleared by quarantine.")
    if item.lot_status == "SUPPLIER_RETURN":
        raise ApiError(422, "lot_closed", "Stock returned to the supplier cannot be quarantined back into use.")
    if item.lot_status == "QUARANTINED":
        raise ApiError(409, "already_quarantined", "This lot is already quarantined.")
    if item.quantity_remaining <= 0:
        raise ApiError(422, "lot_empty", "This lot has no stock left to quarantine.")
    previous = item.lot_status
    item.lot_status = "QUARANTINED"
    item.quarantine_reason = cleaned
    _event(
        db,
        item,
        action="QUARANTINED",
        from_status=previous,
        to_status="QUARANTINED",
        reason=cleaned,
        user_id=user_id,
    )
    audit.record(
        db,
        action_type="LOT_QUARANTINED",
        action="pharmacy.lot_quarantined",
        target_entity="BatchItem",
        target_entity_id=item.id,
        store_id=item.store_id,
        user_id=user_id,
        reason_notes=cleaned,
        old_values={"lot_status": previous},
        new_values={"lot_status": "QUARANTINED"},
    )
    db.commit()
    return item


def _lock(db: Session, statement):
    if db.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    return statement


def _audit_decision(db: Session, **fields) -> None:
    from app.services import audit

    audit.record(db, **fields)


def note_failure(
    db: Session,
    *,
    actor_id: uuid.UUID,
    action: str,
    action_type: str,
    target_entity: str,
    target_id: uuid.UUID | None,
    code: str,
    reason: str | None,
    store_id: uuid.UUID | None = None,
) -> None:
    """Keeps a failed attempt after the business change has been rolled back."""
    db.rollback()
    _audit_decision(
        db,
        action_type=action_type,
        action=action,
        target_entity=target_entity,
        target_entity_id=target_id,
        user_id=actor_id,
        store_id=store_id,
        reason_notes=(reason or "").strip() or None,
        details={"attempted": True, "outcome": "failed", "code": code},
    )
    db.commit()


def _abort(db: Session, status: int, code: str, message: str, **audit_fields) -> None:
    note_failure(db, code=code, **audit_fields)
    raise ApiError(status, code, message)


def active_officer(db: Session, user_id: uuid.UUID) -> PharmacyGovernanceOfficer | None:
    return db.scalar(
        select(PharmacyGovernanceOfficer).where(
            PharmacyGovernanceOfficer.user_id == user_id,
            PharmacyGovernanceOfficer.status == "ACTIVE",
        )
    )


def _active_officer_count(db: Session) -> int:
    return db.scalar(
        select(func.count()).select_from(PharmacyGovernanceOfficer).where(PharmacyGovernanceOfficer.status == "ACTIVE")
    ) or 0


def _require_known_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise ApiError(404, "not_found", "User not found.")
    return user


def nominate_officer(db: Session, actor_id: uuid.UUID, user_id: uuid.UUID, reason: str, *, role_manager: bool) -> PharmacyGovernanceOfficer:
    from app.services import audit

    if actor_id == user_id:
        raise ApiError(403, "self_authorization", "You cannot nominate yourself as a governance officer.")
    cleaned = audit.require_reason(reason, "governance nomination")
    _require_known_user(db, user_id)
    established = _active_officer_count(db) >= 2
    if established:
        if active_officer(db, actor_id) is None:
            raise ApiError(403, "officer_required", "Only a governance officer can nominate another officer.")
    elif not role_manager:
        raise ApiError(403, "role_manager_required", "The first officers are nominated by two users who manage roles.")
    if db.scalar(
        select(PharmacyGovernanceOfficer.id).where(
            PharmacyGovernanceOfficer.user_id == user_id,
            PharmacyGovernanceOfficer.status.in_(("PENDING", "ACTIVE")),
        )
    ):
        raise ApiError(409, "already_pending", "This user already has an open governance nomination.")
    row = PharmacyGovernanceOfficer(user_id=user_id, requested_by_id=actor_id, reason=cleaned, status="PENDING")
    db.add(row)
    _audit_decision(
        db,
        action_type="OFFICER_NOMINATED",
        action="pharmacy.governance_officer_nominated",
        target_entity="User",
        target_entity_id=user_id,
        user_id=actor_id,
        reason_notes=cleaned,
        details={"attempted": True, "outcome": "requested"},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "already_pending", "This user already has an open governance nomination.") from None
    db.refresh(row)
    return row


def confirm_officer(db: Session, actor_id: uuid.UUID, user_id: uuid.UUID, reason: str, *, role_manager: bool) -> PharmacyGovernanceOfficer:
    from app.services import audit

    cleaned = audit.require_reason(reason, "governance confirmation")
    statement = _lock(
        db,
        select(PharmacyGovernanceOfficer).where(
            PharmacyGovernanceOfficer.user_id == user_id,
            PharmacyGovernanceOfficer.status == "PENDING",
        ),
    )
    row = db.scalar(statement)
    if row is None:
        raise ApiError(404, "not_found", "There is no pending governance nomination for this user.")
    if actor_id in {row.requested_by_id, row.user_id}:
        note_failure(
            db,
            actor_id=actor_id,
            action="pharmacy.governance_officer_confirmation_failed",
            action_type="OFFICER_CONFIRM_FAILED",
            target_entity="User",
            target_id=user_id,
            code="separation_of_duties",
            reason=cleaned,
        )
        raise ApiError(403, "separation_of_duties", "The requester and the nominee cannot confirm this nomination.")
    established = _active_officer_count(db) >= 2
    if established:
        if active_officer(db, actor_id) is None:
            db.rollback()
            raise ApiError(403, "officer_required", "Only a governance officer can confirm another officer.")
    elif not role_manager:
        db.rollback()
        raise ApiError(403, "role_manager_required", "A second user who manages roles confirms the first officers.")
    row.status = "ACTIVE"
    row.approved_by_id = actor_id
    row.approved_at = datetime.now(UTC)
    _audit_decision(
        db,
        action_type="OFFICER_CONFIRMED",
        action="pharmacy.governance_officer_confirmed",
        target_entity="User",
        target_entity_id=user_id,
        user_id=actor_id,
        approver_id=actor_id,
        reason_notes=cleaned,
        details={"attempted": True, "outcome": "approved"},
    )
    db.commit()
    return row


def revoke_officer(db: Session, actor_id: uuid.UUID, user_id: uuid.UUID, reason: str) -> PharmacyGovernanceOfficer:
    from app.services import audit

    cleaned = audit.require_reason(reason, "governance revocation")
    if active_officer(db, actor_id) is None:
        raise ApiError(403, "officer_required", "Only a governance officer can revoke an officer.")
    active = list(
        db.scalars(_lock(db, select(PharmacyGovernanceOfficer).where(PharmacyGovernanceOfficer.status == "ACTIVE")))
    )
    if len(active) <= 2:
        db.rollback()
        raise ApiError(409, "oversight_required", "Two governance officers have to remain so one person cannot approve alone.")
    row = next((item for item in active if item.user_id == user_id), None)
    if row is None:
        db.rollback()
        raise ApiError(404, "not_found", "This user is not an active governance officer.")
    row.status = "REVOKED"
    row.revoked_at = datetime.now(UTC)
    row.revoked_by_id = actor_id
    row.revocation_reason = cleaned
    _audit_decision(
        db,
        action_type="OFFICER_REVOKED",
        action="pharmacy.governance_officer_revoked",
        target_entity="User",
        target_entity_id=user_id,
        user_id=actor_id,
        reason_notes=cleaned,
        details={"attempted": True, "outcome": "revoked"},
    )
    db.commit()
    return row


def active_pharmacist(db: Session, user_id: uuid.UUID) -> PharmacistAuthorization | None:
    return db.scalar(
        select(PharmacistAuthorization).where(
            PharmacistAuthorization.user_id == user_id,
            PharmacistAuthorization.status == "ACTIVE",
        )
    )


def _locked_active_pharmacist(db: Session, user_id: uuid.UUID) -> PharmacistAuthorization | None:
    return db.scalar(
        _lock(
            db,
            select(PharmacistAuthorization).where(
                PharmacistAuthorization.user_id == user_id,
                PharmacistAuthorization.status == "ACTIVE",
            ),
        )
    )


def require_pharmacist(db: Session, user_id: uuid.UUID) -> PharmacistAuthorization:
    row = _locked_active_pharmacist(db, user_id)
    if row is None:
        raise ApiError(
            403,
            "pharmacist_required",
            "Only an authorized pharmacist can release or clear a medicine lot.",
        )
    return row


def _require_officer(db: Session, actor_id: uuid.UUID) -> PharmacyGovernanceOfficer:
    row = db.scalar(
        _lock(
            db,
            select(PharmacyGovernanceOfficer).where(
                PharmacyGovernanceOfficer.user_id == actor_id,
                PharmacyGovernanceOfficer.status == "ACTIVE",
            ),
        )
    )
    if row is None:
        raise ApiError(403, "officer_required", "Only a governance officer can appoint or revoke a pharmacist.")
    return row


def request_pharmacist(db: Session, actor_id: uuid.UUID, user_id: uuid.UUID, reason: str) -> PharmacistAuthorization:
    """Opens a pending appointment. It does not allow release until a different officer approves it."""
    from app.services import audit

    if actor_id == user_id:
        raise ApiError(403, "self_authorization", "You cannot authorize yourself to release medicine lots.")
    _require_officer(db, actor_id)
    cleaned = audit.require_reason(reason, "pharmacist authorization")
    _require_known_user(db, user_id)
    open_row = db.scalar(
        select(PharmacistAuthorization).where(
            PharmacistAuthorization.user_id == user_id,
            PharmacistAuthorization.status.in_(("PENDING", "ACTIVE")),
        )
    )
    if open_row is not None and open_row.status == "ACTIVE":
        raise ApiError(409, "already_authorized", "This user is already authorized to release medicine lots.")
    if open_row is not None:
        raise ApiError(409, "already_pending", "This user already has a pharmacist appointment waiting for approval.")
    row = PharmacistAuthorization(
        user_id=user_id,
        requested_by_id=actor_id,
        granted_by_id=actor_id,
        reason=cleaned,
        status="PENDING",
        approval_basis="TWO_PERSON",
    )
    db.add(row)
    _audit_decision(
        db,
        action_type="PHARMACIST_REQUESTED",
        action="pharmacy.pharmacist_appointment_requested",
        target_entity="User",
        target_entity_id=user_id,
        user_id=actor_id,
        reason_notes=cleaned,
        details={"attempted": True, "outcome": "requested"},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "already_pending", "This user already has a pharmacist appointment waiting for approval.") from None
    db.refresh(row)
    return row


def approve_pharmacist(db: Session, actor_id: uuid.UUID, user_id: uuid.UUID, reason: str) -> PharmacistAuthorization:
    from app.services import audit

    _require_officer(db, actor_id)
    cleaned = audit.require_reason(reason, "pharmacist approval")
    row = db.scalar(
        _lock(
            db,
            select(PharmacistAuthorization).where(
                PharmacistAuthorization.user_id == user_id,
                PharmacistAuthorization.status == "PENDING",
            ),
        )
    )
    if row is None:
        db.rollback()
        raise ApiError(404, "not_found", "There is no pharmacist appointment waiting for approval.")
    if actor_id in {row.requested_by_id, row.user_id}:
        note_failure(
            db,
            actor_id=actor_id,
            action="pharmacy.pharmacist_appointment_failed",
            action_type="PHARMACIST_DECIDE_FAILED",
            target_entity="User",
            target_id=user_id,
            code="separation_of_duties",
            reason=cleaned,
        )
        raise ApiError(403, "separation_of_duties", "The requester and the pharmacist cannot approve this appointment.")
    now = datetime.now(UTC)
    row.status = "ACTIVE"
    row.approved_by_id = actor_id
    row.approved_at = now
    row.granted_by_id = actor_id
    row.granted_at = now
    _audit_decision(
        db,
        action_type="PHARMACIST_APPROVED",
        action="pharmacy.pharmacist_appointment_approved",
        target_entity="User",
        target_entity_id=user_id,
        user_id=actor_id,
        approver_id=actor_id,
        reason_notes=cleaned,
        details={"attempted": True, "outcome": "approved"},
    )
    _audit_decision(
        db,
        action_type="PHARMACIST_AUTHORIZED",
        action="pharmacy.pharmacist_authorized",
        target_entity="User",
        target_entity_id=user_id,
        user_id=actor_id,
        approver_id=actor_id,
        reason_notes=cleaned,
        new_values={"user_id": str(user_id), "status": "ACTIVE"},
        details={"attempted": True, "outcome": "granted"},
    )
    db.commit()
    return row


def reject_pharmacist(db: Session, actor_id: uuid.UUID, user_id: uuid.UUID, reason: str) -> PharmacistAuthorization:
    from app.services import audit

    _require_officer(db, actor_id)
    cleaned = audit.require_reason(reason, "pharmacist rejection")
    row = db.scalar(
        _lock(
            db,
            select(PharmacistAuthorization).where(
                PharmacistAuthorization.user_id == user_id,
                PharmacistAuthorization.status == "PENDING",
            ),
        )
    )
    if row is None:
        db.rollback()
        raise ApiError(404, "not_found", "There is no pharmacist appointment waiting for approval.")
    if actor_id in {row.requested_by_id, row.user_id}:
        db.rollback()
        raise ApiError(403, "separation_of_duties", "The requester and the pharmacist cannot decide this appointment.")
    row.status = "REJECTED"
    row.rejected_by_id = actor_id
    row.rejected_at = datetime.now(UTC)
    row.rejection_reason = cleaned
    _audit_decision(
        db,
        action_type="PHARMACIST_REJECTED",
        action="pharmacy.pharmacist_appointment_rejected",
        target_entity="User",
        target_entity_id=user_id,
        user_id=actor_id,
        reason_notes=cleaned,
        details={"attempted": True, "outcome": "rejected"},
    )
    db.commit()
    return row


def revoke_pharmacist(db: Session, actor_id: uuid.UUID, user_id: uuid.UUID, reason: str) -> PharmacistAuthorization:
    from app.services import audit

    _require_officer(db, actor_id)
    cleaned = audit.require_reason(reason, "pharmacist revocation")
    row = _locked_active_pharmacist(db, user_id)
    if row is None:
        db.rollback()
        raise ApiError(404, "not_found", "This user has no active pharmacist authorization.")
    row.status = "REVOKED"
    row.revoked_at = datetime.now(UTC)
    row.revoked_by_id = actor_id
    row.revocation_reason = cleaned
    _audit_decision(
        db,
        action_type="PHARMACIST_REVOKED",
        action="pharmacy.pharmacist_revoked",
        target_entity="User",
        target_entity_id=user_id,
        user_id=actor_id,
        reason_notes=cleaned,
        old_values={"authorized": True},
        new_values={"authorized": False},
        details={"attempted": True, "outcome": "revoked"},
    )
    db.commit()
    return row


def governance_snapshot(db: Session, actor_id: uuid.UUID, *, role_manager: bool) -> dict[str, object]:
    officer = active_officer(db, actor_id) is not None
    if not officer and not role_manager:
        raise ApiError(403, "governance_hidden", "Appointment governance is not available for this account.")
    established = _active_officer_count(db) >= 2

    def names(ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not ids:
            return {}
        return {user.id: user.full_name for user in db.scalars(select(User).where(User.id.in_(ids))).all()}

    officers = list(db.scalars(select(PharmacyGovernanceOfficer).where(PharmacyGovernanceOfficer.status.in_(("PENDING", "ACTIVE")))))
    appointments = list(
        db.scalars(select(PharmacistAuthorization).where(PharmacistAuthorization.status.in_(("PENDING", "ACTIVE"))))
    )
    # Closed rows stay readable. Nothing here changes their status; a new appointment is a new row.
    history = list(
        db.scalars(
            select(PharmacistAuthorization).where(PharmacistAuthorization.status.in_(("REVOKED", "REJECTED")))
        )
    )
    known = {row.user_id for row in officers} | {row.requested_by_id for row in officers}
    known |= {row.user_id for row in appointments} | {row.requested_by_id for row in appointments}
    for row in history:
        known.add(row.user_id)
        known.add(row.requested_by_id)
        for actor in (row.approved_by_id, row.revoked_by_id, row.rejected_by_id):
            if actor is not None:
                known.add(actor)
    label = names(known)

    def officer_item(row: PharmacyGovernanceOfficer) -> dict[str, object]:
        can_confirm = row.status == "PENDING" and actor_id not in {row.requested_by_id, row.user_id} and (
            officer if established else role_manager
        )
        can_revoke = officer and row.status == "ACTIVE" and _active_officer_count(db) > 2
        return {
            "user_id": row.user_id,
            "user_name": label.get(row.user_id, ""),
            "status": row.status,
            "requested_by_id": row.requested_by_id,
            "requested_by_name": label.get(row.requested_by_id, ""),
            "can_decide": can_confirm or can_revoke,
        }

    def appointment_item(row: PharmacistAuthorization) -> dict[str, object]:
        can_decide = officer and row.status == "PENDING" and actor_id not in {row.requested_by_id, row.user_id}
        can_revoke = officer and row.status == "ACTIVE"
        return {
            "user_id": row.user_id,
            "user_name": label.get(row.user_id, ""),
            "status": row.status,
            "requested_by_id": row.requested_by_id,
            "requested_by_name": label.get(row.requested_by_id, ""),
            "can_decide": can_decide or can_revoke,
        }

    def history_item(row: PharmacistAuthorization) -> dict[str, object]:
        return {
            "id": row.id,
            "user_id": row.user_id,
            "user_name": label.get(row.user_id, ""),
            "status": row.status,
            "requested_at": row.requested_at.isoformat(),
            "requested_by_name": label.get(row.requested_by_id, ""),
            "approved_at": row.approved_at.isoformat() if row.approved_at is not None else None,
            "approved_by_name": label.get(row.approved_by_id, "") if row.approved_by_id is not None else "",
            "revoked_at": row.revoked_at.isoformat() if row.revoked_at is not None else None,
            "revoked_by_name": label.get(row.revoked_by_id, "") if row.revoked_by_id is not None else "",
            "revocation_reason": row.revocation_reason,
            "rejected_at": row.rejected_at.isoformat() if row.rejected_at is not None else None,
            "rejection_reason": row.rejection_reason,
        }

    return {
        "established": established,
        "viewer_is_officer": officer,
        "can_nominate": officer or (role_manager and not established),
        "officers": [officer_item(row) for row in officers],
        "appointments": [appointment_item(row) for row in appointments],
        "appointment_history": [history_item(row) for row in history],
    }


def _locked_medicine_layer(db: Session, batch_item_id: uuid.UUID) -> BatchItem:
    statement = select(BatchItem).where(BatchItem.id == batch_item_id)
    if db.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    item = db.scalar(statement)
    if item is None or item.lot_status is None or not is_lot_controlled(db, item.product_id):
        raise ApiError(404, "not_found", "Medicine lot not found.")
    return item


def _release_block(item: BatchItem) -> tuple[str, str] | None:
    """Shared reasons a layer cannot become released. None means the dates and identity are acceptable."""
    from app.services.batch_ledger import today

    if item.lot_status == "RECALLED":
        return "lot_recalled", "A recalled lot cannot be released."
    if item.lot_status == "DAMAGED":
        return "lot_damaged", "A damaged lot cannot be released."
    if item.lot_status == "SUPPLIER_RETURN":
        return "lot_supplier_return", "Stock returned to the supplier cannot be released."
    if not (item.manufacturer_lot or "").strip():
        return "lot_required", "A manufacturer lot is required before release."
    if item.expiry_date is None:
        return "expiry_required", "An expiry date is required before release."
    if item.expiry_date < today():
        return "lot_expired", "An expired lot cannot be released."
    if item.quantity_remaining <= 0:
        return "lot_empty", "This lot has no stock left to release."
    return None


def _become_released(db: Session, item: BatchItem, user_id: uuid.UUID, reason: str, action_name: str) -> None:
    from app.services import audit

    previous = item.lot_status
    item.lot_status = RELEASED
    item.released_at = datetime.now(UTC)
    item.released_by_id = user_id
    _event(
        db,
        item,
        action="RELEASED",
        from_status=previous,
        to_status=RELEASED,
        reason=reason,
        user_id=user_id,
    )
    audit.record(
        db,
        action_type="LOT_RELEASED",
        action=action_name,
        target_entity="BatchItem",
        target_entity_id=item.id,
        store_id=item.store_id,
        user_id=user_id,
        reason_notes=reason,
        old_values={"lot_status": previous},
        new_values={"lot_status": RELEASED, "outcome": "succeeded"},
        details={"attempted": True, "outcome": "succeeded"},
    )


def _release_failure(db: Session, batch_item_id: uuid.UUID, user_id: uuid.UUID, reason: str, status: int, code: str, message: str, *, clearance: bool) -> None:
    _abort(
        db,
        status,
        code,
        message,
        actor_id=user_id,
        action="pharmacy.lot_clearance_failed" if clearance else "pharmacy.lot_release_failed",
        action_type="LOT_CLEARANCE_FAILED" if clearance else "LOT_RELEASE_FAILED",
        target_entity="BatchItem",
        target_id=batch_item_id,
        reason=reason,
    )


def release_lot(db: Session, batch_item_id: uuid.UUID, user_id: uuid.UUID, reason: str) -> BatchItem:
    """UNRELEASED to RELEASED. Quantity and the stock ledger stay unchanged."""
    from app.services import audit

    try:
        cleaned = audit.require_reason(reason, "release")
        require_pharmacist(db, user_id)
    except ApiError as exc:
        _release_failure(db, batch_item_id, user_id, reason, exc.status_code, exc.code, exc.message, clearance=False)
    item = _locked_medicine_layer(db, batch_item_id)
    if item.lot_status == "RELEASED":
        _release_failure(db, batch_item_id, user_id, cleaned, 409, "already_released", "This lot is already released.", clearance=False)
    blocked = _release_block(item)
    if blocked is not None:
        _release_failure(db, batch_item_id, user_id, cleaned, 422, blocked[0], blocked[1], clearance=False)
    if item.lot_status != UNRELEASED:
        _release_failure(db, batch_item_id, user_id, cleaned, 422, "invalid_transition", "Only an unreleased lot can be released.", clearance=False)
    _become_released(db, item, user_id, cleaned, "pharmacy.lot_released")
    db.commit()
    return item


def clear_quarantine(db: Session, batch_item_id: uuid.UUID, user_id: uuid.UUID, reason: str) -> BatchItem:
    """QUARANTINED to RELEASED. A recall is never cleared by this action."""
    from app.services import audit

    try:
        cleaned = audit.require_reason(reason, "quarantine clearance")
        require_pharmacist(db, user_id)
    except ApiError as exc:
        _release_failure(db, batch_item_id, user_id, reason, exc.status_code, exc.code, exc.message, clearance=True)
    item = _locked_medicine_layer(db, batch_item_id)
    if item.lot_status == "RECALLED":
        _release_failure(db, batch_item_id, user_id, cleaned, 422, "lot_recalled", "A recalled lot cannot be cleared through quarantine.", clearance=True)
    if item.lot_status == "RELEASED":
        _release_failure(db, batch_item_id, user_id, cleaned, 409, "already_released", "This lot is already released.", clearance=True)
    blocked = _release_block(item)
    if blocked is not None:
        _release_failure(db, batch_item_id, user_id, cleaned, 422, blocked[0], blocked[1], clearance=True)
    if item.lot_status != "QUARANTINED":
        _release_failure(db, batch_item_id, user_id, cleaned, 422, "invalid_transition", "Only a quarantined lot can be cleared.", clearance=True)
    _become_released(db, item, user_id, cleaned, "pharmacy.lot_quarantine_cleared")
    db.commit()
    return item


def lot_events(db: Session, batch_item_id: uuid.UUID) -> list[tuple[BatchItemEvent, str | None]]:
    _medicine_layer(db, batch_item_id)
    rows = db.execute(
        select(BatchItemEvent, User.full_name)
        .join(User, User.id == BatchItemEvent.user_id, isouter=True)
        .where(BatchItemEvent.batch_item_id == batch_item_id)
        .order_by(BatchItemEvent.created_at, BatchItemEvent.id)
    ).all()
    return [(event, name) for event, name in rows]


def return_to_supplier(
    db: Session,
    *,
    reference: str,
    reason: str,
    lines: list[tuple[uuid.UUID, int]],
    user_id: uuid.UUID,
) -> PharmacySupplierReturn:
    """Send unsold medicine units back. Quantity leaves only through move_stock."""
    from app.services import audit
    from app.services.inventory import move_stock

    cleaned_reference = reference.strip()
    if not cleaned_reference or len(cleaned_reference) > 64:
        raise ApiError(422, "invalid_request", "A supplier return needs a reference of 1 to 64 characters.")
    cleaned_reason = audit.require_reason(reason, "a supplier return")
    if not lines:
        raise ApiError(422, "invalid_request", "Choose at least one lot to return.")
    if db.scalar(select(PharmacySupplierReturn.id).where(PharmacySupplierReturn.reference == cleaned_reference)):
        raise ApiError(409, "conflict", "A supplier return with this reference already exists.")
    if len({item_id for item_id, _quantity in lines}) != len(lines):
        raise ApiError(422, "invalid_request", "Each lot can appear once on a supplier return.")
    prepared: list[tuple[BatchItem, int]] = []
    for item_id, quantity in lines:
        if quantity < 1:
            raise ApiError(422, "invalid_request", "Return at least one unit.")
        item = _return_layer(db, item_id)
        if item.quantity_remaining < quantity:
            raise ApiError(422, "insufficient_stock", "That lot does not have this many units left.")
        prepared.append((item, quantity))
    document = PharmacySupplierReturn(reference=cleaned_reference, reason=cleaned_reason, created_by_id=user_id)
    db.add(document)
    db.flush()
    for item, quantity in prepared:
        before = item.quantity_remaining
        previous = item.lot_status
        move_stock(
            db,
            product_id=item.product_id,
            store_id=item.store_id,
            quantity=-quantity,
            movement_type="PURCHASE_REVERSAL",
            reference_type="pharmacy_supplier_return",
            reference_id=document.id,
            user_id=user_id,
            note=f"{cleaned_reference}: {cleaned_reason}"[:1000],
            reason_code="SUPPLIER_RETURN",
            batch_item_id=item.id,
        )
        if item.quantity_remaining != before - quantity:
            raise ApiError(422, "lot_trace_missing", "The return did not come off the selected lot.")
        to_status = "SUPPLIER_RETURN" if item.quantity_remaining == 0 else previous
        if to_status != previous:
            item.lot_status = to_status
        _event(
            db,
            item,
            action="SUPPLIER_RETURN",
            from_status=previous,
            to_status=to_status,
            reason=f"{cleaned_reference}: {cleaned_reason}",
            user_id=user_id,
        )
        db.add(
            PharmacySupplierReturnLine(
                return_id=document.id,
                batch_item_id=item.id,
                product_id=item.product_id,
                quantity=quantity,
            )
        )
    audit.record(
        db,
        action_type="SUPPLIER_RETURN",
        action="pharmacy.supplier_return",
        target_entity="PharmacySupplierReturn",
        target_entity_id=document.id,
        user_id=user_id,
        reason_notes=cleaned_reason,
        details={"reference": cleaned_reference, "lines": len(prepared)},
    )
    db.commit()
    return document


def open_recall(
    db: Session,
    *,
    reference: str,
    source_text: str,
    severity: str,
    reason: str,
    lots: list[tuple[uuid.UUID, str]],
    user_id: uuid.UUID | None,
) -> PharmacyRecall:
    """Mark matching medicine layers recalled. Quantities are not changed."""
    from app.services import audit

    cleaned_reference = reference.strip()
    cleaned_source = source_text.strip()
    cleaned_severity = severity.strip()
    cleaned_reason = reason.strip()
    if not cleaned_reference or len(cleaned_reference) > 64:
        raise ApiError(422, "invalid_request", "A recall needs a reference of 1 to 64 characters.")
    if not cleaned_source:
        raise ApiError(422, "invalid_request", "Record where this recall came from.")
    if not cleaned_severity or len(cleaned_severity) > 32:
        raise ApiError(422, "invalid_request", "Severity must be 1 to 32 characters.")
    if len(cleaned_reason) < 3:
        raise ApiError(422, "reason_required", "A reason of at least 3 characters is required for a recall.")
    if not lots:
        raise ApiError(422, "invalid_request", "Name at least one manufacturer lot.")
    if db.scalar(select(PharmacyRecall.id).where(PharmacyRecall.reference == cleaned_reference)):
        raise ApiError(409, "conflict", "A recall with this reference already exists.")
    recall = PharmacyRecall(
        reference=cleaned_reference,
        source_text=cleaned_source,
        severity=cleaned_severity,
        reason=cleaned_reason,
        status="OPEN",
        opened_by_id=user_id,
    )
    db.add(recall)
    db.flush()
    matched: list[BatchItem] = []
    seen: set[uuid.UUID] = set()
    for product_id, manufacturer_lot in lots:
        lot_code = manufacturer_lot.strip()
        if not lot_code or len(lot_code) > 64:
            raise ApiError(422, "invalid_request", "Manufacturer lot must be 1 to 64 characters.")
        if not is_lot_controlled(db, product_id):
            raise ApiError(422, "lot_required", "Only a medicine can be recalled.")
        db.add(
            PharmacyRecallLot(
                recall_id=recall.id,
                product_id=product_id,
                manufacturer_lot=lot_code,
            )
        )
        layers = list(
            db.scalars(
                select(BatchItem).where(
                    BatchItem.product_id == product_id,
                    BatchItem.manufacturer_lot == lot_code,
                )
            ).all()
        )
        for layer in layers:
            if layer.id not in seen:
                seen.add(layer.id)
                matched.append(layer)
    _recall_layers(db, recall, matched, user_id)
    descendants = _transfer_descendants(db, [item.id for item in matched])
    extra = [item for item in descendants if item.id not in seen]
    _recall_layers(db, recall, extra, user_id)
    audit.record(
        db,
        action_type="RECALL_OPENED",
        action="pharmacy.recall_opened",
        target_entity="PharmacyRecall",
        target_entity_id=recall.id,
        user_id=user_id,
        reason_notes=cleaned_reason,
        details={"reference": cleaned_reference, "layers": len(matched) + len(extra)},
    )
    db.commit()
    return recall


def set_recall_status(db: Session, recall_id: uuid.UUID, status: str, user_id: uuid.UUID | None) -> PharmacyRecall:
    """Change the recall header only. Stock status is left where it is."""
    from app.services import audit

    if status not in RECALL_STATUSES:
        raise ApiError(422, "invalid_request", "Recall status must be OPEN, CONTAINED, or CLOSED.")
    recall = db.get(PharmacyRecall, recall_id)
    if recall is None:
        raise ApiError(404, "not_found", "Recall not found.")
    previous = recall.status
    if previous == status:
        return recall
    recall.status = status
    audit.record(
        db,
        action_type="RECALL_STATUS",
        action="pharmacy.recall_status",
        target_entity="PharmacyRecall",
        target_entity_id=recall.id,
        user_id=user_id,
        old_values={"status": previous},
        new_values={"status": status},
        details={"reference": recall.reference},
    )
    db.commit()
    return recall


def recall_sales(
    db: Session, recall_id: uuid.UUID, *, offset: int, limit: int
) -> tuple[list[tuple[BatchAllocation, SaleItem, Sale]], int]:
    recall = db.get(PharmacyRecall, recall_id)
    if recall is None:
        raise ApiError(404, "not_found", "Recall not found.")
    layer_ids = set(
        db.scalars(
            select(PharmacyRecallLot.batch_item_id).where(
                PharmacyRecallLot.recall_id == recall.id,
                PharmacyRecallLot.batch_item_id.is_not(None),
            )
        ).all()
    )
    layer_ids.update(
        db.scalars(select(BatchItem.id).where(BatchItem.recall_id == recall.id)).all()
    )
    if not layer_ids:
        return [], 0
    statement = (
        select(BatchAllocation, SaleItem, Sale)
        .join(SaleItem, SaleItem.id == BatchAllocation.sale_item_id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(
            BatchAllocation.batch_item_id.in_(layer_ids),
            BatchAllocation.sale_item_id.is_not(None),
        )
        .order_by(Sale.created_at, BatchAllocation.id)
    )
    total = int(
        db.scalar(
            select(func.count())
            .select_from(BatchAllocation)
            .where(
                BatchAllocation.batch_item_id.in_(layer_ids),
                BatchAllocation.sale_item_id.is_not(None),
            )
        )
        or 0
    )
    rows = list(db.execute(statement.offset(offset).limit(limit)).all())
    return rows, total


def _event(
    db: Session,
    item: BatchItem,
    *,
    action: str,
    from_status: str | None,
    to_status: str | None,
    reason: str | None = None,
    recall_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    db.add(
        BatchItemEvent(
            batch_item_id=item.id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            recall_id=recall_id,
            user_id=user_id,
        )
    )


def _medicine_layer(db: Session, batch_item_id: uuid.UUID) -> BatchItem:
    item = db.get(BatchItem, batch_item_id)
    if item is None or item.lot_status is None or not is_lot_controlled(db, item.product_id):
        raise ApiError(404, "not_found", "Medicine lot not found.")
    return item


def _return_layer(db: Session, batch_item_id: uuid.UUID) -> BatchItem:
    """Lock the branch balance, then the lot, and read the quantity after that lock.

    A supplier return used to read the lot before locking it. Two returns could
    each subtract from the same in-memory quantity and leave the lot above the
    stock ledger.
    """
    from app.services.inventory import level_for

    ids = db.execute(
        select(BatchItem.product_id, BatchItem.store_id).where(BatchItem.id == batch_item_id)
    ).one_or_none()
    if ids is None:
        raise ApiError(404, "not_found", "Medicine lot not found.")
    level_for(db, ids.product_id, ids.store_id)
    statement = select(BatchItem).where(BatchItem.id == batch_item_id)
    if db.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update().execution_options(populate_existing=True)
    item = db.scalar(statement)
    if item is None or item.lot_status is None or not is_lot_controlled(db, item.product_id):
        raise ApiError(404, "not_found", "Medicine lot not found.")
    return item


def _recall_layers(
    db: Session,
    recall: PharmacyRecall,
    layers: list[BatchItem],
    user_id: uuid.UUID | None,
) -> None:
    for item in layers:
        if item.lot_status == "RECALLED" and item.recall_id not in {None, recall.id}:
            continue
        previous = item.lot_status
        if item.recall_id != recall.id or item.lot_status != "RECALLED":
            item.lot_status = "RECALLED"
            item.recall_id = recall.id
            item.recall_reason = recall.reason
            _event(
                db,
                item,
                action="RECALLED",
                from_status=previous,
                to_status="RECALLED",
                reason=recall.reason,
                recall_id=recall.id,
                user_id=user_id,
            )
        already = db.scalar(
            select(PharmacyRecallLot.id).where(
                PharmacyRecallLot.recall_id == recall.id,
                PharmacyRecallLot.batch_item_id == item.id,
            )
        )
        if already is None and item.manufacturer_lot:
            db.add(
                PharmacyRecallLot(
                    recall_id=recall.id,
                    product_id=item.product_id,
                    manufacturer_lot=item.manufacturer_lot,
                    batch_item_id=item.id,
                )
            )
    db.flush()


def _transfer_descendants(db: Session, source_ids: list[uuid.UUID]) -> list[BatchItem]:
    found: list[BatchItem] = []
    pending = list(source_ids)
    seen = set(source_ids)
    while pending:
        children = list(db.scalars(select(BatchItem).where(BatchItem.source_batch_item_id.in_(pending))).all())
        pending = []
        for child in children:
            if child.id in seen:
                continue
            seen.add(child.id)
            found.append(child)
            pending.append(child.id)
    return found


def _apply_open_recall(db: Session, item: BatchItem, user_id: uuid.UUID | None) -> None:
    """A layer received or transferred after an open recall for the same lot is recalled before commit."""
    if not item.manufacturer_lot or item.lot_status == "RECALLED":
        return
    recall = db.scalar(
        select(PharmacyRecall)
        .join(PharmacyRecallLot, PharmacyRecallLot.recall_id == PharmacyRecall.id)
        .where(
            PharmacyRecall.status.in_(("OPEN", "CONTAINED")),
            PharmacyRecallLot.product_id == item.product_id,
            PharmacyRecallLot.manufacturer_lot == item.manufacturer_lot,
        )
        .order_by(PharmacyRecall.created_at, PharmacyRecall.id)
    )
    if recall is None:
        return
    _recall_layers(db, recall, [item], user_id)
