import hashlib
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import tax_authority
from app.core.capabilities import Capability, enabled_capabilities
from app.core.config import Settings
from app.core.errors import ApiError, SyncRejected
from app.core.security import encrypt_value
from app.models.base import utcnow
from app.models.brand import Brand, ProductModel
from app.models.category import Category, SubCategory
from app.models.customer import Customer
from app.models.device import Device
from app.models.product import Product
from app.models.repair_ticket import RepairEvent, RepairTicket
from app.models.sale_return import SaleReturn
from app.models.store import Store
from app.models.sync_event import SyncEvent
from app.schemas.payloads import (
    ProductPayload,
    RepairPayload,
    ReturnPayload,
    SalePayload,
    SerialPayload,
    StorePayload,
    SyncEventIn,
    SyncPushRequest,
    SyncPushResponse,
    SyncPushResult,
)
from app.services import audit, messaging_service, warranty_service
from app.services.brand_service import link, resolve_brand
from app.services.category_service import resolve_by_name
from app.services.identifiers import identifier_hash, normalize_identifier
from app.services.inventory import level_for, move_stock
from app.services.numbering import accept_register_number, next_server_number
from app.services.returns_service import apply_return
from app.services.sale_service import record_sale, write_serial
from app.services.settings_service import business_currency
from app.services.sync_validation import parse_payload, require_store

logger = logging.getLogger("ai_pos.sync")
PayloadModel = StorePayload | ProductPayload | SerialPayload | SalePayload | RepairPayload | ReturnPayload
EntityType = Literal[
    "store",
    "product",
    "serial_number",
    "sale",
    "repair_ticket",
    "sale_return",
    "register_shift",
    "cash_movement",
    "time_entry",
    "customer",
    "open_order",
]
SyncSource = Literal["register", "portal"]
# Entity types whose payload store_id must be the calling register's own branch.
STORE_BOUND = frozenset(
    {
        "product",
        "serial_number",
        "sale",
        "repair_ticket",
        "sale_return",
        "register_shift",
        "cash_movement",
        "time_entry",
        "open_order",
    }
)


@dataclass(frozen=True)
class SyncContext:
    """Where an event came from. Registers may create catalog rows but never edit the portal's catalog."""

    source: SyncSource
    device_id: str
    occurred_at: datetime
    device: Device | None = None


Handler = Callable[[Session, Settings, dict[str, object], SyncContext], uuid.UUID]
EXTRA_HANDLERS: dict[str, Handler] = {}


def register_handler(entity_type: str, handler: Handler) -> None:
    """Feature modules (shifts, cash movements) add their sync entity types here."""
    EXTRA_HANDLERS[entity_type] = handler


def canonical_hash(payload: dict[str, object]) -> str:
    try:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except TypeError as exc:
        raise SyncRejected("Payload is not valid JSON.") from exc
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def apply_store(db: Session, payload: dict[str, object], source: SyncSource = "portal") -> uuid.UUID:
    data = parse_payload(StorePayload, payload)
    existing = db.get(Store, data.id)
    currency = business_currency(db)
    if data.currency != currency:
        raise SyncRejected(f"Stores use the business currency {currency}. A Super Admin changes it in Settings.")
    if existing is not None and source == "register":
        return data.id
    owner = db.scalar(select(Store).where(Store.code == data.code))
    if owner is not None and (existing is None or owner.id != existing.id):
        raise SyncRejected("Store code is already in use.")
    details = {field: getattr(data, field) for field in ("address", "phone", "emirate", "is_warehouse", "is_active")}
    if existing is None:
        db.add(Store(id=data.id, code=data.code, name=data.name, currency=data.currency, **details))
        return data.id
    existing.code = data.code
    existing.name = data.name
    for field in details:
        if field in data.model_fields_set:
            setattr(existing, field, details[field])
    return data.id


def _categories_for(db: Session, data: ProductPayload) -> tuple[Category, SubCategory | None]:
    if data.category_id is not None:
        category = db.get(Category, data.category_id)
        if category is None:
            raise SyncRejected("Category does not exist.")
        sub = None
        if data.sub_category_id is not None:
            sub = db.get(SubCategory, data.sub_category_id)
            if sub is None or sub.category_id != category.id:
                raise SyncRejected("Sub-category does not belong to the category.")
        return category, sub
    return resolve_by_name(db, data.category, data.sub_category)


def _link_brand(db: Session, product: Product, data: ProductPayload) -> None:
    """Brand names map onto the global brand list; a model, when given, also fixes brand and category."""
    if data.product_model_id is not None:
        model = db.get(ProductModel, data.product_model_id)
        if model is None:
            raise SyncRejected("Model does not exist.")
        category = model.sub_category.category
        product.product_model_id = model.id
        product.sub_category_id = model.sub_category_id
        product.category_id = category.id
        product.category = category.name
        product.brand_id = model.brand_id
        product.brand = model.brand.name
        return
    if product.product_model_id is not None:
        return
    brand = None
    if data.brand_id is not None:
        brand = db.get(Brand, data.brand_id)
        if brand is None:
            raise SyncRejected("Brand does not exist.")
    elif data.brand:
        brand = resolve_brand(db, data.brand)
    product.brand_id = brand.id if brand is not None else None
    product.brand = brand.name if brand is not None else None
    if brand is not None and product.sub_category_id is not None:
        link(brand, db.get(SubCategory, product.sub_category_id))


def apply_product(db: Session, payload: dict[str, object], source: SyncSource = "portal") -> uuid.UUID:
    """Upserts the global catalog row. store_id + stock_quantity set opening stock only on creation.

    Registers resend the products in every charge batch from a cache that can be hours old, so for an
    existing product a register upsert only fills a missing category link; price, name, SKU, and barcode
    are owned by the portal."""
    data = parse_payload(ProductPayload, payload)
    store = require_store(db, data.store_id)
    if store.currency != data.currency:
        raise SyncRejected("Product currency must match the store currency.")
    existing = db.get(Product, data.id)
    if existing is not None and source == "register":
        if existing.is_serialized != data.is_serialized:
            raise SyncRejected("Serialized tracking cannot change after creation.")
        if existing.category_id is None:
            category, sub = _categories_for(db, data)
            existing.category_id = category.id
            existing.category = category.name
            existing.sub_category_id = sub.id if sub is not None else None
        if existing.brand_id is None and (data.brand or data.brand_id or data.product_model_id):
            _link_brand(db, existing, data)
        return data.id
    sku_owner = db.scalar(select(Product).where(Product.sku == data.sku))
    barcode_owner = db.scalar(select(Product).where(Product.barcode == data.barcode))
    if sku_owner is not None and (existing is None or sku_owner.id != existing.id):
        raise SyncRejected("SKU is already in use.")
    if barcode_owner is not None and (existing is None or barcode_owner.id != existing.id):
        raise SyncRejected("Barcode is already in use.")
    if existing is None:
        category, sub = _categories_for(db, data)
        product = Product(
            id=data.id,
            sku=data.sku,
            barcode=data.barcode,
            name=data.name,
            model_number=data.model_number,
            brand=data.brand,
            category=category.name,
            category_id=category.id,
            sub_category_id=sub.id if sub is not None else None,
            price_cents=data.price_cents,
            currency=data.currency,
            is_serialized=data.is_serialized,
            tax_category=data.tax_category or "STANDARD",
            is_open_price=bool(data.is_open_price),
        )
        _link_brand(db, product, data)
        db.add(product)
        db.flush()
        level_for(db, data.id, store.id)
        if data.stock_quantity and not data.is_serialized:
            move_stock(
                db,
                product_id=data.id,
                store_id=store.id,
                quantity=data.stock_quantity,
                movement_type="AUDIT_ADJUSTMENT",
                reference_type="opening_balance",
                reference_id=data.id,
                note="Opening stock from product upsert",
            )
        return data.id
    if existing.is_serialized != data.is_serialized:
        raise SyncRejected("Serialized tracking cannot change after creation.")
    existing.sku = data.sku
    existing.barcode = data.barcode
    existing.name = data.name
    existing.price_cents = data.price_cents
    existing.currency = data.currency
    if data.category_id is not None or data.category.lower() != existing.category.lower():
        category, sub = _categories_for(db, data)
        existing.category_id = category.id
        existing.category = category.name
        existing.sub_category_id = sub.id if sub is not None else None
    elif "sub_category_id" in data.model_fields_set or "sub_category" in data.model_fields_set:
        _, sub = _categories_for(db, data)
        existing.sub_category_id = sub.id if sub is not None else None
    if "model_number" in data.model_fields_set:
        existing.model_number = data.model_number
    if data.model_fields_set & {"brand", "brand_id", "product_model_id"}:
        _link_brand(db, existing, data)
    if data.tax_category is not None:
        existing.tax_category = data.tax_category
    if data.is_open_price is not None:
        existing.is_open_price = data.is_open_price
    return data.id


def apply_serial(db: Session, settings: Settings, payload: dict[str, object]) -> uuid.UUID:
    data = parse_payload(SerialPayload, payload)
    require_store(db, data.store_id)
    product = db.get(Product, data.product_id)
    if product is None:
        raise SyncRejected("Product does not exist.")
    if not product.is_serialized:
        raise SyncRejected("Product does not track serial numbers.")
    return write_serial(
        db,
        settings,
        serial_id=data.id,
        product=product,
        store_id=data.store_id,
        kind=data.kind,
        raw_value=data.value,
        status=data.status,
    )


def apply_sale(
    db: Session, settings: Settings, payload: dict[str, object], ctx: SyncContext | None = None
) -> uuid.UUID:
    data = parse_payload(SalePayload, payload)
    if data.sold_at is None and ctx is not None:
        data = data.model_copy(update={"sold_at": ctx.occurred_at})
    return record_sale(db, settings, data, device=ctx.device if ctx is not None else None).id


def apply_sale_return(db: Session, settings: Settings, payload: dict[str, object], ctx: SyncContext) -> uuid.UUID:
    data = parse_payload(ReturnPayload, payload)
    return_id = apply_return(db, settings, payload)
    record = db.get(SaleReturn, return_id)
    if record is not None and record.credit_note_number is None:
        if data.credit_note_number is not None:
            taken = db.scalar(select(SaleReturn.id).where(SaleReturn.credit_note_number == data.credit_note_number))
            record.credit_note_number = accept_register_number(
                db,
                number=data.credit_note_number,
                store_id=data.store_id,
                device=ctx.device,
                doc_type="CN",
                taken=taken is not None,
            )
        else:
            record.credit_note_number = next_server_number(db, data.store_id, "CN")
        db.flush()
        tax_authority.issue_for_return(db, settings, record)
    return return_id


def apply_repair(db: Session, settings: Settings, payload: dict[str, object]) -> uuid.UUID:
    data = parse_payload(RepairPayload, payload)
    store = require_store(db, data.store_id)
    if store.currency != data.currency:
        raise SyncRejected("Repair currency must match the store currency.")
    normalized = normalize_identifier(data.identifier_kind, data.identifier_value)
    digest = identifier_hash(normalized)
    existing = db.get(RepairTicket, data.id)
    from app.services import repair_service

    repair_service.assert_device(db, data, digest, existing.id if existing is not None else None)
    if data.ownership == "internal" and data.product_id is not None:
        product = db.get(Product, data.product_id)
        if product is not None and data.device_model in ("", "Shop device"):
            data.device_model = product.name
    if existing is None:
        registration = warranty_service.registration_for_identifier(db, digest)
        coverage = warranty_service.status_of(registration)
        customer = _repair_customer(db, data, registration)
        if registration is not None and coverage == "IN_WARRANTY":
            registration.claims += 1
            registration.status = "CLAIMED"
        ticket = RepairTicket(
            id=data.id,
            store_id=data.store_id,
            customer_name=data.customer_name,
            customer_phone=data.customer_phone,
            device_model=data.device_model,
            identifier_kind=data.identifier_kind,
            identifier_hash=digest,
            identifier_encrypted=encrypt_value(normalized, settings),
            issue=data.issue,
            status=data.status,
            estimated_cost_cents=data.estimated_cost_cents,
            currency=data.currency,
            customer_id=customer.id if customer is not None else None,
            warranty_registration_id=registration.id if registration is not None else None,
            warranty_status=coverage,
            ownership=data.ownership,
            product_id=data.product_id,
        )
        db.add(ticket)
        db.flush()
        from app.services import repair_workshop_service

        repair_workshop_service.apply_intake(db, settings, ticket, data)
        db.add(RepairEvent(ticket_id=data.id, to_status=data.status, note="Booked in", source="register"))
        notify_repair_ready(db, ticket, store)
        return data.id
    if existing.store_id != data.store_id:
        raise SyncRejected("Repair ticket cannot move between stores.")
    if existing.status != data.status:
        db.add(
            RepairEvent(ticket_id=existing.id, from_status=existing.status, to_status=data.status, source="register")
        )
    existing.customer_name = data.customer_name
    existing.customer_phone = data.customer_phone
    existing.device_model = data.device_model
    existing.identifier_kind = data.identifier_kind
    existing.identifier_hash = digest
    existing.identifier_encrypted = encrypt_value(normalized, settings)
    existing.issue = data.issue
    existing.status = data.status
    existing.estimated_cost_cents = data.estimated_cost_cents
    existing.ownership = data.ownership
    existing.product_id = data.product_id
    if data.customer_id is not None and db.get(Customer, data.customer_id) is not None:
        existing.customer_id = data.customer_id
    from app.services import repair_workshop_service

    repair_workshop_service.apply_intake(db, settings, existing, data)
    notify_repair_ready(db, existing, store)
    return data.id


def _repair_customer(db: Session, data: RepairPayload, registration) -> Customer | None:
    # A shop-owned device is not a customer, and booking it must not create one.
    if data.ownership == "internal":
        return None
    if data.customer_id is not None:
        customer = db.get(Customer, data.customer_id)
        if customer is None:
            raise SyncRejected("Customer does not exist.")
        return customer
    if registration is not None and registration.customer_id is not None:
        return db.get(Customer, registration.customer_id)
    return db.scalar(select(Customer).where(Customer.phone == data.customer_phone.strip()).limit(1))


def notify_repair_ready(db: Session, ticket: RepairTicket, store: Store) -> None:
    if ticket.status != "ready" or ticket.customer_id is None:
        return
    customer = db.get(Customer, ticket.customer_id)
    if customer is None:
        return
    messaging_service.enqueue(
        db,
        template_key="repair_ready",
        customer=customer,
        context={"device": ticket.device_model, "ticket": str(ticket.id)[:8].upper(), "store": store.name},
        dedupe_key=f"repair:{ticket.id}:ready",
    )


def push_batch(
    db: Session,
    request: SyncPushRequest,
    settings: Settings,
    *,
    source: SyncSource = "register",
    device: Device | None = None,
) -> SyncPushResponse:
    if len(request.events) > settings.sync_max_batch_size:
        raise ApiError(413, "batch_too_large", "Sync batch exceeds the configured limit.")
    keys = [event.idempotency_key for event in request.events]
    if len(set(keys)) != len(keys):
        raise ApiError(422, "duplicate_idempotency_key", "Batch contains repeated idempotency keys.")

    results: list[SyncPushResult] = []
    try:
        for event in request.events:
            ctx = SyncContext(source=source, device_id=request.device_id, occurred_at=event.occurred_at, device=device)
            results.append(_apply_event(db, ctx, event, settings))
        db.commit()
    except SyncRejected as exc:
        db.rollback()
        raise ApiError(
            422,
            "sync_rejected",
            exc.message,
            details={"idempotency_key": event.idempotency_key},
        ) from exc
    except ApiError:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        logger.exception("Sync batch conflicted with stored data.")
        raise ApiError(409, "conflict", "The batch conflicts with existing data.") from exc
    return SyncPushResponse(results=results)


def _apply_event(db: Session, ctx: SyncContext, event: SyncEventIn, settings: Settings) -> SyncPushResult:
    digest = canonical_hash(event.payload)
    statement = select(SyncEvent).where(SyncEvent.idempotency_key == event.idempotency_key)
    if db.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    existing = db.scalar(statement)
    if existing is not None:
        if existing.payload_hash != digest:
            raise ApiError(
                409,
                "idempotency_conflict",
                "Idempotency key was already used with a different payload.",
                details={"idempotency_key": event.idempotency_key},
            )
        return SyncPushResult(idempotency_key=event.idempotency_key, status="duplicate")

    _reject_practice_replay(db, event)
    entity_id = _dispatch(db, settings, event, ctx)
    db.add(
        SyncEvent(
            idempotency_key=event.idempotency_key,
            device_id=ctx.device_id,
            entity_type=event.entity_type,
            entity_id=entity_id,
            payload_hash=digest,
            occurred_at=event.occurred_at,
            applied_at=utcnow(),
        )
    )
    db.flush()
    return SyncPushResult(idempotency_key=event.idempotency_key, status="applied")


def _reject_practice_replay(db: Session, event: SyncEventIn) -> None:
    """A store that went live from practice does not accept activity dated before that moment.

    The idempotency row for an already-applied practice sale is kept, so a retry is a duplicate and never reaches
    here. Stores that were live from the start are unchanged: their tills still sync earlier offline events.
    """
    from app.services.settings_service import cached_settings

    snapshot = cached_settings(db)
    if not snapshot.promoted_from_practice or snapshot.live_at is None:
        return
    occurred = event.occurred_at if event.occurred_at.tzinfo else event.occurred_at.replace(tzinfo=UTC)
    live_at = snapshot.live_at if snapshot.live_at.tzinfo else snapshot.live_at.replace(tzinfo=UTC)
    if occurred < live_at:
        raise SyncRejected("This was recorded during practice and was not kept when the store went live.")


def _check_device_scope(event: SyncEventIn, ctx: SyncContext) -> None:
    if ctx.device is None:
        return
    own = str(ctx.device.store_id)
    if event.entity_type == "store" and str(event.payload.get("id")) != own:
        raise SyncRejected("A register can only upsert its own store.")
    if event.entity_type in STORE_BOUND and str(event.payload.get("store_id")) != own:
        raise SyncRejected("This register can only record activity for its own store.")


ENTITY_CAPABILITIES: dict[str, Capability] = {
    "repair_ticket": Capability.REPAIRS,
    "serial_number": Capability.SERIAL_TRACKING,
    "open_order": Capability.OPEN_ORDERS,
}
TENDER_CAPABILITIES: dict[str, Capability] = {
    "on_account": Capability.B2B_CREDIT,
    "cheque": Capability.CHEQUES,
    "loyalty": Capability.LOYALTY,
    "trade_in": Capability.TRADE_IN,
    "channel": Capability.DELIVERY_CHANNELS,
}


def _modules_used(event: SyncEventIn) -> set[Capability]:
    used: set[Capability] = set()
    if event.entity_type in ENTITY_CAPABILITIES:
        used.add(ENTITY_CAPABILITIES[event.entity_type])
    if event.entity_type == "sale":
        methods = {str(event.payload.get("payment_method") or "")}
        tenders = event.payload.get("tenders")
        if isinstance(tenders, list):
            methods |= {str(tender.get("method") or "") for tender in tenders if isinstance(tender, dict)}
        used |= {TENDER_CAPABILITIES[method] for method in methods if method in TENDER_CAPABILITIES}
    return used


def _note_disabled_modules(db: Session, event: SyncEventIn, ctx: SyncContext, record_id: uuid.UUID) -> None:
    """A register may sync work captured offline before a module was switched off. That is real money, so it is
    applied, and the audit trail records which disabled modules it used."""
    disabled = sorted(capability.value for capability in _modules_used(event) - enabled_capabilities(db))
    if not disabled:
        return
    logger.warning("Sync %s used disabled modules %s", event.idempotency_key, ", ".join(disabled))
    audit.record(
        db,
        action_type="UPDATE",
        action="sync.capability_disabled",
        target_entity=event.entity_type,
        target_entity_id=record_id,
        details={"modules": disabled, "device_id": ctx.device_id, "idempotency_key": event.idempotency_key},
    )


def _dispatch(db: Session, settings: Settings, event: SyncEventIn, ctx: SyncContext) -> uuid.UUID:
    record_id = _apply(db, settings, event, ctx)
    _note_disabled_modules(db, event, ctx, record_id)
    return record_id


def _apply(db: Session, settings: Settings, event: SyncEventIn, ctx: SyncContext) -> uuid.UUID:
    _check_device_scope(event, ctx)
    handlers: dict[str, Callable[[], uuid.UUID]] = {
        "store": lambda: apply_store(db, event.payload, ctx.source),
        "product": lambda: apply_product(db, event.payload, ctx.source),
        "serial_number": lambda: apply_serial(db, settings, event.payload),
        "sale": lambda: apply_sale(db, settings, event.payload, ctx),
        "repair_ticket": lambda: apply_repair(db, settings, event.payload),
        "sale_return": lambda: apply_sale_return(db, settings, event.payload, ctx),
    }
    handler = handlers.get(event.entity_type)
    if handler is None:
        extra = EXTRA_HANDLERS.get(event.entity_type)
        if extra is None:
            raise SyncRejected("Entity type is not supported.")
        return extra(db, settings, event.payload, ctx)
    return handler()


def ingest_one(
    db: Session,
    settings: Settings,
    *,
    device_id: str,
    idempotency_key: str,
    entity_type: EntityType,
    payload: PayloadModel,
    source: SyncSource = "portal",
    device: Device | None = None,
) -> SyncPushResponse:
    event = SyncEventIn(
        idempotency_key=idempotency_key,
        entity_type=entity_type,
        operation="upsert",
        payload=payload.model_dump(mode="json"),
        occurred_at=datetime.now(UTC),
    )
    return push_batch(db, SyncPushRequest(device_id=device_id, events=[event]), settings, source=source, device=device)
