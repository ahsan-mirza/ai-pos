"""Per-terminal stock allocation.

An allocation reserves existing available stock for one device. It does not insert a stock movement
and it does not reduce quantity_on_hand. Sales still post through inventory.move_stock.
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.deps import Principal
from app.core.errors import ApiError, SyncRejected
from app.core.permissions import Permission
from app.models.batch import BatchItem
from app.models.device import Device
from app.models.inventory import InventoryLevel
from app.models.product import Product
from app.models.serial_number import SerialNumber
from app.models.terminal_allocation import (
    HOLDING_STATUSES,
    TerminalAllocation,
    TerminalAllocationConsumption,
)
from app.schemas.payloads import SalePayload
from app.services import audit, entitlement_service, inventory
from app.services.entitlement_service import canonical_payload

PURPOSE = "stock_allocation"
RELEASE_PURPOSE = "stock_allocation_release"
SCHEMA_VERSION = 1
POLICY_VERSION = 1


def _require_inventory_manager(principal: Principal) -> None:
    if principal.kind != "user" or not principal.has(Permission.INVENTORY_ADJUST_STOCK):
        raise ApiError(403, "forbidden", "Stock allocation requires inventory adjustment permission.")


def _lock_level(db: Session, product_id: uuid.UUID, store_id: uuid.UUID) -> InventoryLevel:
    """Take a write lock before reading availability so two issuers cannot reserve the same units."""
    level = inventory.level_for(db, product_id, store_id)
    db.flush()
    db.execute(
        update(InventoryLevel)
        .where(InventoryLevel.id == level.id)
        .values(quantity_on_hand=InventoryLevel.quantity_on_hand)
    )
    db.refresh(level)
    return level


def _holding(db: Session, product_id: uuid.UUID, store_id: uuid.UUID) -> list[TerminalAllocation]:
    return list(
        db.scalars(
            select(TerminalAllocation).where(
                TerminalAllocation.product_id == product_id,
                TerminalAllocation.store_id == store_id,
                TerminalAllocation.status.in_(HOLDING_STATUSES),
            )
        ).all()
    )


def _sign(document: dict[str, object]) -> tuple[str, str, str]:
    key_id, private = entitlement_service._signing_key()
    document["key_id"] = key_id
    payload = canonical_payload(document)
    signature = base64.b64encode(private.sign(payload.encode("utf-8"))).decode("ascii")
    return key_id, payload, signature


def issue_allocation(
    db: Session,
    principal: Principal,
    *,
    store_id: uuid.UUID,
    device_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: int,
    serial_number_id: uuid.UUID | None = None,
    batch_item_id: uuid.UUID | None = None,
) -> TerminalAllocation:
    _require_inventory_manager(principal)
    if principal.store_id is not None and principal.store_id != store_id:
        raise ApiError(403, "store_scope", "You can only allocate stock in your own store.")
    from app.tenancy.scoping import bind_request_scope

    bind_request_scope(db, store_id, None)
    if quantity < 1:
        raise ApiError(422, "invalid_quantity", "Allocation quantity must be a positive integer.")
    device = db.get(Device, device_id)
    if device is None or device.revoked_at is not None:
        raise ApiError(404, "terminal_not_found", "That terminal is not active.")
    if device.store_id != store_id:
        raise ApiError(422, "branch_mismatch", "A terminal can only be allocated stock at its own branch.")
    if not device.device_public_key_thumbprint:
        raise ApiError(422, "device_unbound", "The terminal has no device binding yet.")
    product = db.get(Product, product_id)
    if product is None or not product.is_active or not product.is_stock_tracked:
        raise ApiError(422, "product_not_allocatable", "That product cannot be allocated.")
    if product.is_serialized:
        if serial_number_id is None or quantity != 1:
            raise ApiError(422, "serial_required", "A serialized product allocates one exact serial.")
    elif serial_number_id is not None:
        raise ApiError(422, "serial_not_tracked", "This product does not allocate by serial.")

    level = _lock_level(db, product_id, store_id)
    if serial_number_id is not None:
        serial = db.get(SerialNumber, serial_number_id)
        if serial is None or serial.product_id != product_id or serial.store_id != store_id or serial.status != "in_stock":
            raise ApiError(422, "serial_unavailable", "That serial is not in stock at this branch.")
        taken = db.scalar(
            select(TerminalAllocation.id).where(
                TerminalAllocation.serial_number_id == serial_number_id,
                TerminalAllocation.status.in_(HOLDING_STATUSES),
            )
        )
        if taken is not None:
            raise ApiError(409, "serial_allocated", "That serial is already allocated to a terminal.")
    if batch_item_id is not None:
        lot = db.get(BatchItem, batch_item_id)
        if lot is None or lot.product_id != product_id or lot.store_id != store_id:
            raise ApiError(422, "lot_mismatch", "That lot is not at this branch for this product.")
        if lot.lot_status not in (None, "RELEASED"):
            raise ApiError(422, "lot_unavailable", "That lot is not released for sale.")
        if lot.expiry_date is not None and lot.expiry_date < date.today():
            raise ApiError(422, "lot_expired", "That lot is expired.")
        already = sum(
            row.remaining for row in _holding(db, product_id, store_id) if row.batch_item_id == batch_item_id
        )
        if already + quantity > lot.quantity_remaining:
            raise ApiError(409, "lot_overlap", "That lot does not have this much unallocated quantity.")

    if level.available < quantity:
        raise ApiError(
            409,
            "allocation_exceeds_stock",
            f"Only {max(level.available, 0)} units can still be allocated at this branch.",
        )
    inventory.reserve(db, product_id, store_id, quantity)
    unit = "g" if product.sold_by_weight else "each"
    allocation_id = uuid.uuid4()
    manifest_id = uuid.uuid4()
    issued_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    document: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "purpose": PURPOSE,
        "manifest_id": str(manifest_id),
        "allocation_id": str(allocation_id),
        "allocation_version": 1,
        "issuer": "axizpos",
        "tenant_id": str(device.tenant_id),
        "branch_id": str(store_id),
        "terminal_id": str(device.id),
        "device_binding": device.device_public_key_thumbprint,
        "product_id": str(product_id),
        "serial_number_id": str(serial_number_id) if serial_number_id else None,
        "batch_item_id": str(batch_item_id) if batch_item_id else None,
        "unit": unit,
        "quantity": quantity,
        "policy_version": POLICY_VERSION,
        "issued_at": issued_at,
    }
    key_id, payload, signature = _sign(document)
    row = TerminalAllocation(
        id=allocation_id,
        manifest_id=manifest_id,
        version=1,
        store_id=store_id,
        device_id=device.id,
        device_thumbprint=device.device_public_key_thumbprint,
        product_id=product_id,
        serial_number_id=serial_number_id,
        batch_item_id=batch_item_id,
        unit=unit,
        quantity_allocated=quantity,
        quantity_consumed=0,
        last_sequence=0,
        status="ACTIVE",
        policy_version=POLICY_VERSION,
        signing_key_id=key_id,
        manifest_payload=payload,
        manifest_signature=signature,
        issued_at=datetime.now(UTC),
    )
    db.add(row)
    db.flush()
    audit.record(
        db,
        action_type="CREATE",
        action="allocation.issue",
        target_entity="TerminalAllocation",
        target_entity_id=row.id,
        store_id=store_id,
        user=principal.user,
        new_values={"quantity": quantity, "device_id": str(device.id), "product_id": str(product_id)},
    )
    return row


def release_allocation(
    db: Session,
    principal: Principal,
    allocation_id: uuid.UUID,
    *,
    confirmed_sequence: int,
    confirmed_remaining: int,
) -> tuple[TerminalAllocation, str, str]:
    """Release unused quantity after the terminal's synced sequence matches the server."""
    _require_inventory_manager(principal)
    row = _locked_allocation(db, allocation_id)
    if row.status == "QUARANTINED":
        raise ApiError(409, "allocation_quarantined", "A quarantined allocation is not released automatically.")
    if row.status != "ACTIVE" and row.status != "EXHAUSTED":
        raise ApiError(409, "allocation_closed", "This allocation is not open.")
    if confirmed_sequence != row.last_sequence or confirmed_remaining != row.remaining:
        raise ApiError(409, "sequence_mismatch", "The terminal balance does not match the last synced consumption.")
    leftover = row.remaining
    if leftover:
        inventory.release(db, row.product_id, row.store_id, leftover)
    row.status = "RELEASED"
    document: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "purpose": RELEASE_PURPOSE,
        "allocation_id": str(row.id),
        "manifest_id": str(row.manifest_id),
        "allocation_version": row.version,
        "terminal_id": str(row.device_id),
        "device_binding": row.device_thumbprint,
        "released_quantity": leftover,
        "sequence": row.last_sequence,
    }
    _key_id, payload, signature = _sign(document)
    audit.record(
        db,
        action_type="UPDATE",
        action="allocation.release",
        target_entity="TerminalAllocation",
        target_entity_id=row.id,
        store_id=row.store_id,
        user=principal.user,
        new_values={"released_quantity": leftover, "sequence": row.last_sequence},
    )
    db.flush()
    return row, payload, signature


def quarantine_allocation(db: Session, principal: Principal, allocation_id: uuid.UUID) -> TerminalAllocation:
    """Hold a lost terminal's remainder. This does not free the stock."""
    _require_inventory_manager(principal)
    row = _locked_allocation(db, allocation_id)
    if row.status != "ACTIVE":
        raise ApiError(409, "allocation_closed", "Only an active allocation can be quarantined.")
    row.status = "QUARANTINED"
    audit.record(
        db,
        action_type="UPDATE",
        action="allocation.quarantine",
        target_entity="TerminalAllocation",
        target_entity_id=row.id,
        store_id=row.store_id,
        user=principal.user,
        new_values={"remaining": row.remaining},
    )
    db.flush()
    return row


def _locked_allocation(db: Session, allocation_id: uuid.UUID) -> TerminalAllocation:
    statement = select(TerminalAllocation).where(TerminalAllocation.id == allocation_id)
    if db.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    row = db.scalar(statement)
    if row is None:
        raise ApiError(404, "allocation_not_found", "That allocation does not exist.")
    return row


def consume_for_sale(
    db: Session,
    data: SalePayload,
    device: Device | None,
    *,
    idempotency_key: str | None,
) -> dict[uuid.UUID, list[tuple[int, uuid.UUID | None]]]:
    """Release this sale's reserved units and record the consumption. Stock movement stays with the sale."""
    if not data.allocations:
        return {}
    if device is None or device.revoked_at is not None:
        raise SyncRejected("An allocated sale must come from the terminal that holds the allocation.")
    from app.tenancy.scoping import bind_request_scope

    bind_request_scope(db, device.store_id, device.id)
    slices: dict[uuid.UUID, list[tuple[int, uuid.UUID | None]]] = {}
    seen: set[uuid.UUID] = set()
    for entry in sorted(data.allocations, key=lambda item: (str(item.allocation_id), item.sequence)):
        if entry.allocation_id in seen:
            raise SyncRejected("A sale cannot consume the same allocation twice.")
        seen.add(entry.allocation_id)
        statement = select(TerminalAllocation).where(TerminalAllocation.id == entry.allocation_id)
        if db.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update()
        row = db.scalar(statement)
        if row is None:
            raise SyncRejected("The allocation does not exist.")
        if row.device_id != device.id or row.store_id != data.store_id:
            raise SyncRejected("This terminal cannot consume that allocation.")
        if row.device_thumbprint != (device.device_public_key_thumbprint or ""):
            raise SyncRejected("The allocation is bound to a different device.")
        if row.status != "ACTIVE":
            raise SyncRejected("The allocation is not active.")
        if entry.product_id != row.product_id:
            raise SyncRejected("The allocation is for a different product.")
        if entry.sequence != row.last_sequence + 1:
            raise SyncRejected("The allocation consumption sequence does not follow the last accepted sale.")
        if entry.quantity > row.remaining:
            raise SyncRejected("The sale exceeds the remaining allocation.")
        if row.serial_number_id is not None and entry.quantity != 1:
            raise SyncRejected("A serial allocation consumes exactly one unit.")
        inventory.release(db, row.product_id, row.store_id, entry.quantity)
        row.quantity_consumed += entry.quantity
        row.last_sequence = entry.sequence
        if row.quantity_consumed == row.quantity_allocated:
            row.status = "EXHAUSTED"
        if not idempotency_key:
            raise SyncRejected("An allocated sale needs its idempotency key.")
        db.add(
            TerminalAllocationConsumption(
                allocation_id=row.id,
                sequence=entry.sequence,
                quantity=entry.quantity,
                sale_id=data.id,
                idempotency_key=f"{idempotency_key}:{row.id}",
            )
        )
        slices.setdefault(row.product_id, []).append((entry.quantity, row.batch_item_id))
    db.flush()
    return slices
