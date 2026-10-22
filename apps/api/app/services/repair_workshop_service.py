"""Repairs 2.0 on top of repair_service: the workshop state machine, technician board, estimate approval by
signed link, intake photos and passcode, deposits credited on the invoice, parts held in stock, the public
tracking page, and the warranty an invoiced repair carries."""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import Principal
from app.core.errors import ApiError, SyncRejected
from app.core.security import decrypt_value, encrypt_value
from app.models.customer import Customer
from app.models.inventory import InventoryLevel
from app.models.repair_ticket import RepairAttachment, RepairDeposit, RepairEvent, RepairLine, RepairTicket
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.serial_number import SerialNumber
from app.models.store import Store
from app.models.user import User
from app.models.warranty import WarrantyRegistration
from app.schemas.module_settings import RepairSettings
from app.schemas.repairs import (
    ApprovalDecision,
    ApprovalRequest,
    BoardCard,
    BoardColumn,
    DepositCreate,
    RepairAssign,
    RepairAttachmentOut,
    RepairBoard,
    RepairDepositOut,
    RepairDetail,
    RepairWarrantyOut,
    TrackingOut,
)
from app.services import audit, inventory, messaging_service
from app.services.settings_service import cached_settings

STORAGE_ROOT = Path(__file__).resolve().parents[2] / "storage" / "repairs"
BOARD_STATUSES = ("intake", "diagnosing", "awaiting_approval", "in_repair", "waiting_parts", "ready")
FINAL = ("closed", "cancelled")
# Where a ticket may go next from the portal. The register may skip steps offline; the board shows what it sends.
TRANSITIONS: dict[str, frozenset[str]] = {
    "intake": frozenset({"diagnosing", "awaiting_approval", "in_repair", "ready", "cancelled", "closed"}),
    "diagnosing": frozenset(
        {"intake", "awaiting_approval", "in_repair", "waiting_parts", "ready", "cancelled", "closed"}
    ),
    "awaiting_approval": frozenset({"diagnosing", "in_repair", "ready", "cancelled", "closed"}),
    "in_repair": frozenset({"diagnosing", "waiting_parts", "ready", "cancelled", "closed"}),
    "waiting_parts": frozenset({"in_repair", "ready", "cancelled", "closed"}),
    "ready": frozenset({"in_repair", "closed"}),
    "closed": frozenset(),
    "cancelled": frozenset(),
}
STATUS_LABELS = {
    "intake": "Booked in",
    "diagnosing": "Diagnosing",
    "awaiting_approval": "Waiting for your approval",
    "in_repair": "Being repaired",
    "waiting_parts": "Waiting for parts",
    "ready": "Ready for collection",
    "closed": "Collected",
    "cancelled": "Cancelled",
}
ATTACHMENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "application/pdf": ".pdf",
}
MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024
MAX_ATTACHMENTS = 20


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    return None if value is None else (value if value.tzinfo else value.replace(tzinfo=UTC))


def reference(ticket: RepairTicket) -> str:
    return str(ticket.id)[:8].upper()


def barcode_value(ticket: RepairTicket) -> str:
    """What the job card's Code 128 encodes; scanning it at the register opens the ticket."""
    return f"RPR-{reference(ticket)}"


def repair_settings(db: Session) -> RepairSettings:
    return cached_settings(db).module_settings.repairs


def warranty_days(db: Session, ticket: RepairTicket) -> int:
    return ticket.repair_warranty_days if ticket.repair_warranty_days is not None else repair_settings(db).warranty_days


def ensure_tracking(ticket: RepairTicket) -> str:
    if not ticket.tracking_token:
        ticket.tracking_token = secrets.token_urlsafe(18)[:24]
    return ticket.tracking_token


def tracking_url(settings: Settings, ticket: RepairTicket) -> str:
    return f"{settings.public_base_url.rstrip('/')}/track/{ensure_tracking(ticket)}"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _event(db: Session, ticket: RepairTicket, status: str, note: str, user_id, source: str = "portal") -> None:
    db.add(
        RepairEvent(
            ticket_id=ticket.id,
            from_status=ticket.status,
            to_status=status,
            note=note[:500],
            user_id=user_id,
            source=source,
        )
    )


def check_transition(ticket: RepairTicket, status: str) -> None:
    if status == ticket.status:
        return
    if status not in TRANSITIONS.get(ticket.status, frozenset()):
        raise ApiError(
            409,
            "invalid_transition",
            f"A repair that is {STATUS_LABELS.get(ticket.status, ticket.status).lower()} cannot move to "
            f"{STATUS_LABELS.get(status, status).lower()}.",
        )


def on_status(db: Session, ticket: RepairTicket, status: str) -> None:
    """Side effects of entering a status (called before the status changes)."""
    if status == "cancelled":
        release_all(db, ticket)
        if any(deposit.status == "HELD" for deposit in held_deposits(db, ticket)):
            raise ApiError(409, "deposit_held", "Refund the deposit before cancelling the repair.")
    if status == "closed" and ticket.sale_id is None:
        if _lines_total(db, ticket) > 0:
            raise ApiError(409, "invoice_first", "Invoice the parts and labour before the customer collects.")
        if held_deposits(db, ticket):
            raise ApiError(409, "deposit_held", "Refund the deposit, or invoice it, before the customer collects.")
        release_all(db, ticket)
        ticket.picked_up_at = _now()


# --- Parts held in stock -----------------------------------------------------------------------------------


def reserve_line(db: Session, ticket: RepairTicket, line: RepairLine) -> None:
    """Holds as many of the part as the branch has free; a shortfall leaves the ticket flagged for parts."""
    if line.kind != "PART":
        return
    wanted = line.quantity - (line.reserved_quantity or 0)
    if wanted <= 0:
        return
    level = db.scalar(
        select(InventoryLevel).where(
            InventoryLevel.product_id == line.product_id, InventoryLevel.store_id == ticket.store_id
        )
    )
    free = max(0, level.available) if level is not None else 0
    take = min(wanted, free)
    if take > 0:
        try:
            inventory.reserve(db, line.product_id, ticket.store_id, take)
        except SyncRejected:
            return
        line.reserved_quantity = (line.reserved_quantity or 0) + take


def release_line(db: Session, ticket: RepairTicket, line: RepairLine) -> None:
    if line.reserved_quantity:
        inventory.release(db, line.product_id, ticket.store_id, line.reserved_quantity)
        line.reserved_quantity = 0


def release_all(db: Session, ticket: RepairTicket) -> None:
    for line in db.scalars(select(RepairLine).where(RepairLine.ticket_id == ticket.id)):
        release_line(db, ticket, line)


def retry_reservations(db: Session, ticket: RepairTicket) -> None:
    for line in db.scalars(select(RepairLine).where(RepairLine.ticket_id == ticket.id, RepairLine.kind == "PART")):
        reserve_line(db, ticket, line)


def _lines(db: Session, ticket: RepairTicket) -> list[RepairLine]:
    return list(db.scalars(select(RepairLine).where(RepairLine.ticket_id == ticket.id)))


def _lines_total(db: Session, ticket: RepairTicket) -> int:
    return sum(line.quantity * line.unit_price_cents for line in _lines(db, ticket))


# --- Enrichment for the detail view -----------------------------------------------------------------------


def held_deposits(db: Session, ticket: RepairTicket) -> list[RepairDeposit]:
    return list(
        db.scalars(select(RepairDeposit).where(RepairDeposit.ticket_id == ticket.id, RepairDeposit.status == "HELD"))
    )


def enrich(db: Session, settings: Settings, ticket: RepairTicket, detail: RepairDetail) -> RepairDetail:
    technician = db.get(User, ticket.technician_id) if ticket.technician_id else None
    deposits = list(
        db.scalars(
            select(RepairDeposit).where(RepairDeposit.ticket_id == ticket.id).order_by(RepairDeposit.received_at)
        )
    )
    names = {
        user.id: user.full_name
        for user in db.scalars(
            select(User).where(User.id.in_({d.received_by_id for d in deposits if d.received_by_id}))
        )
    }
    attachments = db.scalars(
        select(RepairAttachment).where(RepairAttachment.ticket_id == ticket.id).order_by(RepairAttachment.created_at)
    ).all()
    lines = {line.id: line for line in _lines(db, ticket)}
    held = sum(d.amount_cents for d in deposits if d.status == "HELD")
    registration = db.scalar(
        select(WarrantyRegistration).where(
            WarrantyRegistration.repair_ticket_id == ticket.id, WarrantyRegistration.kind == "REPAIR"
        )
    )
    url = tracking_url(settings, ticket)
    open_ticket = ticket.sale_id is None and ticket.status not in FINAL
    return detail.model_copy(
        update={
            "reference": reference(ticket),
            "technician_id": ticket.technician_id,
            "technician_name": technician.full_name if technician else None,
            "priority": ticket.priority or "NORMAL",
            "promised_at": _aware(ticket.promised_at),
            "has_passcode": bool(ticket.passcode_encrypted),
            "intake_checklist": ticket.intake_checklist,
            "accessories": ticket.accessories or "",
            "approval_status": ticket.approval_status,
            "approval_amount_cents": ticket.approval_amount_cents,
            "approval_requested_at": _aware(ticket.approval_requested_at),
            "approval_decided_at": _aware(ticket.approval_decided_at),
            "approval_channel": ticket.approval_channel,
            "approval_note": ticket.approval_note or "",
            "repair_warranty_days": warranty_days(db, ticket),
            "tracking_url": url,
            "picked_up_at": _aware(ticket.picked_up_at),
            "lines": [
                line.model_copy(update={"reserved_quantity": lines[line.id].reserved_quantity or 0})
                if line.id in lines
                else line
                for line in detail.lines
            ],
            "attachments": [
                RepairAttachmentOut(
                    id=row.id,
                    kind=row.kind,  # type: ignore[arg-type]
                    file_name=row.file_name,
                    content_type=row.content_type,
                    size_bytes=row.size_bytes,
                    created_at=_aware(row.created_at),  # type: ignore[arg-type]
                )
                for row in attachments
            ],
            "deposits": [
                RepairDepositOut(
                    id=row.id,
                    amount_cents=row.amount_cents,
                    method=row.method,
                    reference=row.reference,
                    status=row.status,  # type: ignore[arg-type]
                    received_at=_aware(row.received_at),  # type: ignore[arg-type]
                    received_by_name=names.get(row.received_by_id) if row.received_by_id else None,
                )
                for row in deposits
            ],
            "deposit_held_cents": held,
            "balance_due_cents": max(0, detail.total_cents - held) if open_ticket else 0,
            "parts_short": open_ticket
            and any(line.kind == "PART" and (line.reserved_quantity or 0) < line.quantity for line in lines.values()),
            "repair_warranty": RepairWarrantyOut(
                id=registration.id,
                starts_at=_aware(registration.starts_at),  # type: ignore[arg-type]
                expires_at=_aware(registration.expires_at),  # type: ignore[arg-type]
                status=registration.status,
            )
            if registration is not None
            else None,
        }
    )


# --- Assignment and the bench board -----------------------------------------------------------------------


def _ticket(db: Session, ticket_id: uuid.UUID, store_scope: uuid.UUID | None) -> RepairTicket:
    ticket = db.get(RepairTicket, ticket_id)
    if ticket is None or (store_scope is not None and ticket.store_id != store_scope):
        raise ApiError(404, "not_found", "Repair ticket was not found.")
    return ticket


def _user(principal: Principal) -> User:
    if principal.user is None:
        raise ApiError(403, "forbidden", "This action requires a signed-in user.")
    return principal.user


def assign(db: Session, principal: Principal, ticket_id: uuid.UUID, data: RepairAssign) -> RepairTicket:
    user = _user(principal)
    ticket = _ticket(db, ticket_id, principal.store_id)
    notes: list[str] = []
    if data.clear_technician:
        ticket.technician_id = None
        notes.append("Unassigned")
    elif data.technician_id is not None:
        technician = db.get(User, data.technician_id)
        if technician is None or not technician.is_active:
            raise ApiError(422, "validation_error", "Choose an active member of staff.")
        if technician.store_id is not None and technician.store_id != ticket.store_id:
            raise ApiError(422, "validation_error", f"{technician.full_name} works at another branch.")
        ticket.technician_id = technician.id
        notes.append(f"Assigned to {technician.full_name}")
    if data.priority is not None and data.priority != ticket.priority:
        ticket.priority = data.priority
        notes.append(f"Priority {data.priority.lower()}")
    if data.clear_promise:
        ticket.promised_at = None
    elif data.promised_at is not None:
        ticket.promised_at = data.promised_at
        notes.append(f"Promised for {data.promised_at:%d %b %H:%M}")
    if data.repair_warranty_days is not None:
        ticket.repair_warranty_days = data.repair_warranty_days
        notes.append(f"Repair warranty {data.repair_warranty_days} days")
    if notes:
        _event(db, ticket, ticket.status, "; ".join(notes), user.id)
    db.commit()
    return ticket


def board(
    db: Session, store_scope: uuid.UUID | None, store_id: uuid.UUID | None, technician_id: uuid.UUID | None
) -> RepairBoard:
    filters = [RepairTicket.status.in_(BOARD_STATUSES)]
    scope = store_scope or store_id
    if scope is not None:
        filters.append(RepairTicket.store_id == scope)
    if technician_id is not None:
        filters.append(RepairTicket.technician_id == technician_id)
    tickets = list(db.scalars(select(RepairTicket).where(*filters).order_by(RepairTicket.created_at)))
    ids = [ticket.id for ticket in tickets] or [uuid.uuid4()]
    held = {
        ticket_id: int(total)
        for ticket_id, total in db.execute(
            select(RepairDeposit.ticket_id, func.sum(RepairDeposit.amount_cents))
            .where(RepairDeposit.ticket_id.in_(ids), RepairDeposit.status == "HELD")
            .group_by(RepairDeposit.ticket_id)
        )
    }
    short = set(
        db.scalars(
            select(RepairLine.ticket_id).where(
                RepairLine.ticket_id.in_(ids),
                RepairLine.kind == "PART",
                RepairLine.reserved_quantity < RepairLine.quantity,
            )
        )
    )
    staff_ids = {ticket.technician_id for ticket in tickets if ticket.technician_id}
    technicians = [
        {"id": str(user.id), "name": user.full_name}
        for user in db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name))
        if "repairs:update" in user.permissions and (scope is None or user.store_id in (None, scope))
    ]
    names = {row["id"]: row["name"] for row in technicians}
    for user in db.scalars(select(User).where(User.id.in_(staff_ids or {uuid.uuid4()}))):
        names.setdefault(str(user.id), user.full_name)
    now = _now()
    priority_rank = {"URGENT": 0, "HIGH": 1, "NORMAL": 2, "LOW": 3}
    columns: list[BoardColumn] = []
    for status in BOARD_STATUSES:
        cards = [
            BoardCard(
                id=ticket.id,
                reference=reference(ticket),
                device_model=ticket.device_model,
                customer_name=ticket.customer_name,
                issue=ticket.issue[:160],
                status=ticket.status,  # type: ignore[arg-type]
                priority=ticket.priority or "NORMAL",  # type: ignore[arg-type]
                technician_id=ticket.technician_id,
                technician_name=names.get(str(ticket.technician_id)) if ticket.technician_id else None,
                promised_at=_aware(ticket.promised_at),
                overdue=bool(ticket.promised_at and _aware(ticket.promised_at) < now and status != "ready"),  # type: ignore[operator]
                approval_status=ticket.approval_status,  # type: ignore[arg-type]
                parts_short=ticket.id in short,
                deposit_held_cents=held.get(ticket.id, 0),
                estimated_cost_cents=ticket.estimated_cost_cents,
                currency=ticket.currency,
                updated_at=_aware(ticket.updated_at),  # type: ignore[arg-type]
            )
            for ticket in tickets
            if ticket.status == status
        ]
        cards.sort(
            key=lambda card: (priority_rank.get(card.priority, 2), card.promised_at or datetime.max.replace(tzinfo=UTC))
        )
        columns.append(BoardColumn(status=status, cards=cards))  # type: ignore[arg-type]
    return RepairBoard(columns=columns, technicians=technicians)


# --- Estimate approval ------------------------------------------------------------------------------------


def request_approval(
    db: Session, settings: Settings, principal: Principal, ticket_id: uuid.UUID, data: ApprovalRequest
) -> tuple[RepairTicket, str, str | None]:
    user = _user(principal)
    ticket = _ticket(db, ticket_id, principal.store_id)
    if ticket.sale_id is not None or ticket.status in FINAL or ticket.status == "ready":
        raise ApiError(409, "approval_closed", "Estimates are approved before the repair is finished.")
    amount = data.amount_cents
    if amount is None:
        amount = _lines_total(db, ticket) or ticket.estimated_cost_cents
    token = secrets.token_urlsafe(24)
    now = _now()
    ticket.approval_status = "PENDING"
    ticket.approval_amount_cents = amount
    ticket.approval_requested_at = now
    ticket.approval_decided_at = None
    ticket.approval_channel = None
    ticket.approval_note = data.note.strip()
    ticket.approval_token_hash = _token_hash(token)
    ticket.approval_expires_at = now + timedelta(hours=repair_settings(db).approval_link_hours)
    if ticket.status != "awaiting_approval":
        check_transition(ticket, "awaiting_approval")
        _event(db, ticket, "awaiting_approval", f"Estimate {amount / 100:.2f} sent for approval", user.id)
        ticket.status = "awaiting_approval"
    url = f"{settings.public_base_url.rstrip('/')}/repair/approve/{token}"
    message_status: str | None = None
    if data.send_link:
        customer = db.get(Customer, ticket.customer_id) if ticket.customer_id else None
        store = db.get(Store, ticket.store_id)
        if customer is None:
            message_status = "NO_CUSTOMER"
        else:
            from app.services.invoice_pdf import money

            queued = messaging_service.enqueue(
                db,
                template_key="repair_estimate",
                customer=customer,
                context={
                    "device": ticket.device_model,
                    "ticket": reference(ticket),
                    "store": store.name if store else "",
                    "amount": money(amount, ticket.currency),
                    "link": url,
                },
                dedupe_key=f"repair:{ticket.id}:estimate:{int(now.timestamp())}",
            )
            message_status = queued.status if queued is not None else "SWITCHED_OFF"
    db.commit()
    return ticket, url, message_status


def _decide(db: Session, ticket: RepairTicket, approve: bool, channel: str, note: str, user_id) -> None:
    ticket.approval_status = "APPROVED" if approve else "DECLINED"
    ticket.approval_decided_at = _now()
    ticket.approval_channel = channel
    ticket.approval_token_hash = None
    if note:
        ticket.approval_note = note[:300]
    who = {"link": "by the customer online", "in_store": "in store", "phone": "by phone"}.get(channel, "")
    if approve:
        target = "in_repair" if ticket.status in ("awaiting_approval", "diagnosing", "intake") else ticket.status
        retry_reservations(db, ticket)
        _event(
            db,
            ticket,
            target,
            f"Estimate approved {who}".strip(),
            user_id,
            "customer" if channel == "link" else "portal",
        )
        ticket.status = target
    else:
        release_all(db, ticket)
        _event(
            db,
            ticket,
            "ready",
            f"Estimate declined {who}; return the device unrepaired".strip(),
            user_id,
            "customer" if channel == "link" else "portal",
        )
        ticket.status = "ready"
        store = db.get(Store, ticket.store_id)
        if store is not None:
            from app.services.sync_service import notify_repair_ready

            notify_repair_ready(db, ticket, store)


def decide_in_store(db: Session, principal: Principal, ticket_id: uuid.UUID, data: ApprovalDecision) -> RepairTicket:
    user = _user(principal)
    ticket = _ticket(db, ticket_id, principal.store_id)
    if ticket.sale_id is not None or ticket.status in FINAL:
        raise ApiError(409, "approval_closed", "This repair is already finished.")
    if ticket.approval_status in ("APPROVED", "DECLINED") and ticket.status != "awaiting_approval":
        raise ApiError(409, "already_decided", f"The estimate was already {ticket.approval_status.lower()}.")
    if ticket.approval_amount_cents is None:
        ticket.approval_amount_cents = _lines_total(db, ticket) or ticket.estimated_cost_cents
        ticket.approval_requested_at = _now()
    _decide(db, ticket, data.decision == "approve", data.channel, data.note.strip(), user.id)
    db.commit()
    return ticket


def ticket_for_approval_token(db: Session, token: str) -> RepairTicket:
    if not token or len(token) > 64:
        raise ApiError(404, "not_found", "This link is not valid.")
    ticket = db.scalar(select(RepairTicket).where(RepairTicket.approval_token_hash == _token_hash(token)))
    if ticket is None:
        raise ApiError(404, "not_found", "This link was already used or is not valid.")
    return ticket


def approval_open(ticket: RepairTicket) -> bool:
    expires = _aware(ticket.approval_expires_at)
    return ticket.approval_status == "PENDING" and (expires is None or expires > _now())


def decide_by_link(db: Session, token: str, approve: bool) -> RepairTicket:
    ticket = ticket_for_approval_token(db, token)
    if not approval_open(ticket):
        raise ApiError(410, "link_expired", "This approval link has expired. Contact the store.")
    _decide(db, ticket, approve, "link", "", None)
    db.commit()
    return ticket


# --- Deposits ---------------------------------------------------------------------------------------------


def add_deposit(db: Session, principal: Principal, ticket_id: uuid.UUID, data: DepositCreate) -> RepairTicket:
    ticket = _ticket(db, ticket_id, principal.store_id)
    if ticket.sale_id is not None or ticket.status in FINAL:
        raise ApiError(409, "repair_closed", "This repair is already finished.")
    db.add(
        RepairDeposit(
            ticket_id=ticket.id,
            store_id=ticket.store_id,
            amount_cents=data.amount_cents,
            method=data.method,
            reference=data.reference.strip(),
            status="HELD",
            received_by_id=principal.user.id if principal.user is not None else None,
            shift_id=data.shift_id,
            received_at=_now(),
        )
    )
    _event(
        db,
        ticket,
        ticket.status,
        f"Deposit {data.amount_cents / 100:.2f} by {data.method}",
        principal.user.id if principal.user is not None else None,
        "portal" if principal.user is not None else "register",
    )
    db.commit()
    return ticket


def refund_deposit(
    db: Session, principal: Principal, ticket_id: uuid.UUID, deposit_id: uuid.UUID, shift_id: uuid.UUID | None
) -> RepairTicket:
    user = _user(principal)
    ticket = _ticket(db, ticket_id, principal.store_id)
    deposit = db.get(RepairDeposit, deposit_id)
    if deposit is None or deposit.ticket_id != ticket.id:
        raise ApiError(404, "not_found", "Deposit was not found.")
    if deposit.status != "HELD":
        raise ApiError(409, "deposit_closed", f"This deposit was already {deposit.status.lower()}.")
    deposit.status = "REFUNDED"
    deposit.refunded_at = _now()
    deposit.refund_shift_id = shift_id
    _event(db, ticket, ticket.status, f"Deposit {deposit.amount_cents / 100:.2f} refunded", user.id)
    audit.record(
        db,
        action_type="UPDATE",
        action="repair.deposit_refunded",
        target_entity="RepairDeposit",
        target_entity_id=deposit.id,
        user=user,
        store_id=ticket.store_id,
        details={"ticket": reference(ticket), "amount_cents": deposit.amount_cents, "method": deposit.method},
    )
    db.commit()
    return ticket


def apply_deposits(db: Session, ticket: RepairTicket, sale_id: uuid.UUID) -> None:
    for deposit in held_deposits(db, ticket):
        deposit.status = "APPLIED"
        deposit.applied_sale_id = sale_id


# --- Intake details, photos and passcode -------------------------------------------------------------------


def apply_intake(db: Session, settings: Settings, ticket: RepairTicket, data) -> None:
    """Stores the optional intake fields a register sends with the booking (RepairPayload)."""
    if data.technician_id is not None and db.get(User, data.technician_id) is not None:
        ticket.technician_id = data.technician_id
    if data.priority is not None:
        ticket.priority = data.priority
    if data.promised_at is not None:
        ticket.promised_at = data.promised_at
    if data.passcode:
        ticket.passcode_encrypted = encrypt_value(data.passcode, settings)
    if data.intake_checklist is not None:
        ticket.intake_checklist = data.intake_checklist
    if data.accessories is not None:
        ticket.accessories = data.accessories.strip()
    ensure_tracking(ticket)


def reveal_passcode(db: Session, settings: Settings, principal: Principal, ticket_id: uuid.UUID) -> str:
    user = _user(principal)
    ticket = _ticket(db, ticket_id, principal.store_id)
    if not ticket.passcode_encrypted:
        raise ApiError(404, "not_found", "No passcode was recorded for this device.")
    audit.record(
        db,
        action_type="UPDATE",
        action="repair.passcode_viewed",
        target_entity="RepairTicket",
        target_entity_id=ticket.id,
        user=user,
        store_id=ticket.store_id,
        details={"ticket": reference(ticket)},
    )
    db.commit()
    return decrypt_value(ticket.passcode_encrypted, settings)


def _store_file(
    db: Session, principal: Principal, ticket: RepairTicket, data: bytes, content_type: str, file_name: str, kind: str
) -> None:
    extension = ATTACHMENT_TYPES.get(content_type)
    if extension is None:
        raise ApiError(415, "unsupported_file", "Attach a JPEG, PNG, WebP or HEIC photo, or a PDF.")
    count = db.scalar(select(func.count(RepairAttachment.id)).where(RepairAttachment.ticket_id == ticket.id)) or 0
    if count >= MAX_ATTACHMENTS:
        raise ApiError(409, "too_many_files", f"A ticket holds at most {MAX_ATTACHMENTS} files.")
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise ApiError(413, "file_too_large", "Files are at most 8 MB.")
    if not data:
        raise ApiError(422, "empty_file", "The file is empty.")
    attachment_id = uuid.uuid4()
    key = f"{ticket.id}/{attachment_id.hex}{extension}"
    path = STORAGE_ROOT / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    db.add(
        RepairAttachment(
            id=attachment_id,
            ticket_id=ticket.id,
            kind=kind,
            file_name=Path(file_name or f"photo{extension}").name[:160],
            content_type=content_type,
            size_bytes=len(data),
            storage_key=key,
            uploaded_by_id=principal.user.id if principal.user is not None else None,
        )
    )


def save_attachment(
    db: Session, principal: Principal, ticket_id: uuid.UUID, upload: UploadFile, kind: str
) -> RepairTicket:
    ticket = _ticket(db, ticket_id, principal.store_id)
    content_type = (upload.content_type or "").split(";")[0].strip().lower()
    _store_file(
        db, principal, ticket, upload.file.read(MAX_ATTACHMENT_BYTES + 1), content_type, upload.filename or "", kind
    )
    db.commit()
    return ticket


def save_attachment_bytes(
    db: Session,
    principal: Principal,
    ticket_id: uuid.UUID,
    content_type: str,
    data_base64: str,
    file_name: str,
    kind: str,
) -> RepairTicket:
    """JSON upload for the register, whose passthrough speaks JSON rather than multipart."""
    ticket = _ticket(db, ticket_id, principal.store_id)
    cleaned = "".join(data_base64.split())
    try:
        raw = base64.b64decode(cleaned + "=" * ((-len(cleaned)) % 4), validate=False)
    except (ValueError, TypeError) as exc:
        raise ApiError(422, "invalid_file", "The photo could not be read.") from exc
    _store_file(db, principal, ticket, raw, content_type.strip().lower(), file_name, kind)
    db.commit()
    return ticket


def attachment_file(
    db: Session, principal: Principal, ticket_id: uuid.UUID, attachment_id: uuid.UUID
) -> tuple[Path, RepairAttachment]:
    ticket = _ticket(db, ticket_id, principal.store_id)
    row = db.get(RepairAttachment, attachment_id)
    if row is None or row.ticket_id != ticket.id:
        raise ApiError(404, "not_found", "File was not found.")
    path = (STORAGE_ROOT / row.storage_key).resolve()
    if STORAGE_ROOT.resolve() not in path.parents or not path.exists():
        raise ApiError(404, "not_found", "File was not found.")
    return path, row


def delete_attachment(
    db: Session, principal: Principal, ticket_id: uuid.UUID, attachment_id: uuid.UUID
) -> RepairTicket:
    path, row = attachment_file(db, principal, ticket_id, attachment_id)
    ticket = _ticket(db, ticket_id, principal.store_id)
    db.delete(row)
    db.commit()
    path.unlink(missing_ok=True)
    return ticket


# --- Repair warranty --------------------------------------------------------------------------------------


def create_repair_warranty(db: Session, ticket: RepairTicket, sale: Sale) -> WarrantyRegistration | None:
    days = warranty_days(db, ticket)
    if days <= 0:
        return None
    item = db.scalar(select(SaleItem).where(SaleItem.sale_id == sale.id).order_by(SaleItem.id).limit(1))
    if item is None:
        return None
    serial = db.scalar(select(SerialNumber).where(SerialNumber.value_hash == ticket.identifier_hash))
    starts = _now()
    registration = WarrantyRegistration(
        sale_id=sale.id,
        sale_item_id=item.id,
        serial_number_id=serial.id if serial is not None else None,
        product_id=item.product_id,
        customer_id=ticket.customer_id,
        store_id=ticket.store_id,
        starts_at=starts,
        expires_at=starts + timedelta(days=days),
        status="ACTIVE",
        kind="REPAIR",
        repair_ticket_id=ticket.id,
        identifier_hash=ticket.identifier_hash,
    )
    db.add(registration)
    db.flush()
    return registration


# --- Lookup and public tracking ---------------------------------------------------------------------------


def find_by_code(db: Session, code: str, store_scope: uuid.UUID | None) -> RepairTicket:
    cleaned = code.strip().upper().removeprefix("RPR-")
    if len(cleaned) != 8 or any(c not in "0123456789ABCDEF" for c in cleaned):
        raise ApiError(404, "not_found", "That is not a repair job card.")
    candidates = db.scalars(
        select(RepairTicket).where(cast(RepairTicket.id, String).ilike(f"{cleaned.lower()}%")).limit(5)
    ).all()
    matches = [t for t in candidates if reference(t) == cleaned and (store_scope is None or t.store_id == store_scope)]
    if not matches:
        raise ApiError(404, "not_found", "No repair has that job card.")
    return matches[0]


def tracking(db: Session, token: str) -> TrackingOut:
    if not token or len(token) > 40:
        raise ApiError(404, "not_found", "Repair was not found.")
    ticket = db.scalar(select(RepairTicket).where(RepairTicket.tracking_token == token))
    if ticket is None:
        raise ApiError(404, "not_found", "Repair was not found.")
    store = db.get(Store, ticket.store_id)
    total = _lines_total(db, ticket)
    held = sum(d.amount_cents for d in held_deposits(db, ticket))
    order = ["intake", "diagnosing", "in_repair", "ready", "closed"]
    position = {"awaiting_approval": 1, "waiting_parts": 2}.get(
        ticket.status, order.index(ticket.status) if ticket.status in order else 0
    )
    steps = [
        {
            "label": STATUS_LABELS[step],
            "done": index < position or ticket.status == "closed",
            "current": index == position,
        }
        for index, step in enumerate(order)
    ]
    return TrackingOut(
        reference=reference(ticket),
        device_model=ticket.device_model,
        status=ticket.status,  # type: ignore[arg-type]
        status_label=STATUS_LABELS.get(ticket.status, ticket.status),
        store_name=store.name if store else "",
        promised_at=_aware(ticket.promised_at),
        approval_status=ticket.approval_status,  # type: ignore[arg-type]
        total_cents=total or ticket.estimated_cost_cents,
        balance_due_cents=max(0, total - held) if ticket.sale_id is None else 0,
        currency=ticket.currency,
        updated_at=_aware(ticket.updated_at),  # type: ignore[arg-type]
        steps=steps,
    )
