"""Warranty cover: registered automatically for serialized units sold, extended by plans sold on the same
sale, checked when a repair is booked, voided on return, and reminded before it ends."""

import calendar
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.security import decrypt_value
from app.models.customer import Customer
from app.models.product import Product
from app.models.repair_ticket import RepairTicket
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.serial_number import SerialNumber
from app.models.warranty import WarrantyPlan, WarrantyPolicy, WarrantyRegistration
from app.schemas.warranty import (
    PlanOut,
    PlanWrite,
    PolicyOut,
    PolicyWrite,
    RegistrationList,
    RegistrationOut,
)
from app.services import messaging_service
from app.services.category_service import resolve_by_name
from app.services.identifiers import identifier_hash, normalize_identifier
from app.services.settings_service import business_currency

REMIND_DAYS = 30


def add_months(moment: datetime, months: int) -> datetime:
    month = moment.month - 1 + months
    year = moment.year + month // 12
    month = month % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def policy_for(db: Session, product: Product) -> WarrantyPolicy | None:
    rows = list(db.scalars(select(WarrantyPolicy).where(WarrantyPolicy.is_active.is_(True))))
    for scope, matches in (
        ("PRODUCT", lambda row: row.product_id == product.id),
        ("CATEGORY", lambda row: product.category_id is not None and row.category_id == product.category_id),
        ("DEFAULT", lambda row: True),
    ):
        found = next((row for row in rows if row.scope == scope and matches(row)), None)
        if found is not None:
            return found
    return None


def register_sale(db: Session, sale: Sale, customer: Customer | None) -> int:
    """Creates registrations for the serialized units on a recorded sale and applies plans sold with them."""
    items = list(db.scalars(select(SaleItem).where(SaleItem.sale_id == sale.id)))
    plans_by_product = {
        row.product_id: row for row in db.scalars(select(WarrantyPlan).where(WarrantyPlan.is_active.is_(True)))
    }
    plan_units: list[WarrantyPlan] = []
    for item in items:
        plan = plans_by_product.get(item.product_id)
        if plan is not None:
            plan_units.extend([plan] * item.quantity)
    starts = _aware(sale.created_at)
    created = 0
    for item in items:
        if item.serial_number_id is None:
            continue
        product = db.get(Product, item.product_id)
        if product is None:
            continue
        policy = policy_for(db, product)
        plan = plan_units.pop(0) if plan_units else None
        months = (policy.months if policy is not None else 0) + (plan.extra_months if plan is not None else 0)
        if months <= 0:
            continue
        db.add(
            WarrantyRegistration(
                sale_id=sale.id,
                sale_item_id=item.id,
                serial_number_id=item.serial_number_id,
                product_id=item.product_id,
                customer_id=customer.id if customer is not None else None,
                store_id=sale.store_id,
                policy_id=policy.id if policy is not None else None,
                plan_id=plan.id if plan is not None else None,
                starts_at=starts,
                expires_at=add_months(starts, months),
                status="ACTIVE",
            )
        )
        created += 1
    db.flush()
    return created


def void_for_return(db: Session, sale_item_id: uuid.UUID) -> None:
    registration = db.scalar(select(WarrantyRegistration).where(WarrantyRegistration.sale_item_id == sale_item_id))
    if registration is not None:
        registration.status = "VOID"


def registration_for_identifier(db: Session, digest: str) -> WarrantyRegistration | None:
    """The cover that ends last for this device: sale cover on a unit sold here, or a repair warranty."""
    return db.scalar(
        select(WarrantyRegistration)
        .outerjoin(SerialNumber, SerialNumber.id == WarrantyRegistration.serial_number_id)
        .where(
            or_(SerialNumber.value_hash == digest, WarrantyRegistration.identifier_hash == digest),
            WarrantyRegistration.status != "VOID",
        )
        .order_by(WarrantyRegistration.expires_at.desc())
        .limit(1)
    )


def status_of(registration: WarrantyRegistration | None, now: datetime | None = None) -> str:
    if registration is None:
        return "NOT_FOUND"
    return "IN_WARRANTY" if _aware(registration.expires_at) > (now or datetime.now(UTC)) else "EXPIRED"


def expiry_by_sale_item(db: Session, sale_item_ids: list[uuid.UUID]) -> dict[uuid.UUID, datetime]:
    if not sale_item_ids:
        return {}
    return {
        row.sale_item_id: _aware(row.expires_at)
        for row in db.scalars(
            select(WarrantyRegistration).where(
                WarrantyRegistration.sale_item_id.in_(sale_item_ids), WarrantyRegistration.status != "VOID"
            )
        )
    }


def send_reminders(db: Session, settings: Settings) -> int:
    now = datetime.now(UTC)
    due = db.scalars(
        select(WarrantyRegistration).where(
            WarrantyRegistration.status == "ACTIVE",
            WarrantyRegistration.customer_id.is_not(None),
            WarrantyRegistration.expires_at > now,
            WarrantyRegistration.expires_at <= now + timedelta(days=REMIND_DAYS),
        )
    ).all()
    queued = 0
    for registration in due:
        customer = db.get(Customer, registration.customer_id)
        product = db.get(Product, registration.product_id)
        serial = db.get(SerialNumber, registration.serial_number_id) if registration.serial_number_id else None
        if customer is None or product is None:
            continue
        message = messaging_service.enqueue(
            db,
            template_key="warranty_expiry",
            customer=customer,
            context={
                "product": product.name,
                "serial": decrypt_value(serial.value_encrypted, settings)[-4:].rjust(8, "•") if serial else "",
                "expires": f"{_aware(registration.expires_at):%d %b %Y}",
            },
            dedupe_key=f"warranty:{registration.id}:expiry",
        )
        queued += message is not None
    db.commit()
    return queued


# --- Portal ----------------------------------------------------------------------------------------


def _registration_out(db: Session, settings: Settings, rows: list[WarrantyRegistration]) -> list[RegistrationOut]:
    product_ids = {row.product_id for row in rows}
    customer_ids = {row.customer_id for row in rows if row.customer_id}
    plan_ids = {row.plan_id for row in rows if row.plan_id}
    sale_ids = {row.sale_id for row in rows}
    serial_ids = {row.serial_number_id for row in rows if row.serial_number_id}
    products = (
        {row.id: row.name for row in db.scalars(select(Product).where(Product.id.in_(product_ids)))} if rows else {}
    )
    customers = (
        {
            row.id: row.company_name or row.name
            for row in db.scalars(select(Customer).where(Customer.id.in_(customer_ids)))
        }
        if customer_ids
        else {}
    )
    plans = (
        {row.id: row.name for row in db.scalars(select(WarrantyPlan).where(WarrantyPlan.id.in_(plan_ids)))}
        if plan_ids
        else {}
    )
    invoices = (
        {
            row.id: row.invoice_number or row.client_sale_id[:8].upper()
            for row in db.scalars(select(Sale).where(Sale.id.in_(sale_ids)))
        }
        if sale_ids
        else {}
    )
    serials = (
        {
            row.id: decrypt_value(row.value_encrypted, settings)
            for row in db.scalars(select(SerialNumber).where(SerialNumber.id.in_(serial_ids)))
        }
        if serial_ids
        else {}
    )
    repair_ids = {row.repair_ticket_id for row in rows if row.repair_ticket_id}
    repairs = (
        {
            row.id: (f"Repair {str(row.id)[:8].upper()}: {row.device_model}", decrypt_value(row.identifier_encrypted, settings))
            for row in db.scalars(select(RepairTicket).where(RepairTicket.id.in_(repair_ids)))
        }
        if repair_ids
        else {}
    )
    now = datetime.now(UTC)
    return [
        RegistrationOut(
            id=row.id,
            sale_id=row.sale_id,
            invoice=invoices.get(row.sale_id, ""),
            kind=row.kind or "SALE",  # type: ignore[arg-type]
            product_name=repairs[row.repair_ticket_id][0]
            if row.repair_ticket_id in repairs
            else products.get(row.product_id, ""),
            serial=serials.get(row.serial_number_id)
            if row.serial_number_id
            else (repairs[row.repair_ticket_id][1] if row.repair_ticket_id in repairs else None),
            customer_id=row.customer_id,
            customer_name=customers.get(row.customer_id) if row.customer_id else None,
            plan_name=plans.get(row.plan_id) if row.plan_id else None,
            starts_at=_aware(row.starts_at),
            expires_at=_aware(row.expires_at),
            status=row.status,  # type: ignore[arg-type]
            coverage="VOID" if row.status == "VOID" else status_of(row, now),  # type: ignore[arg-type]
            claims=row.claims,
        )
        for row in rows
    ]


def list_registrations(
    db: Session,
    settings: Settings,
    *,
    query: str | None,
    expiring_days: int | None,
    store_scope: uuid.UUID | None,
    limit: int,
) -> RegistrationList:
    now = datetime.now(UTC)
    scope = []
    if store_scope is not None:
        scope.append(WarrantyRegistration.store_id == store_scope)
    statement = select(WarrantyRegistration).where(*scope).order_by(WarrantyRegistration.starts_at.desc()).limit(limit)
    if expiring_days is not None:
        statement = statement.where(
            WarrantyRegistration.status == "ACTIVE",
            WarrantyRegistration.expires_at > now,
            WarrantyRegistration.expires_at <= now + timedelta(days=expiring_days),
        )
    if query:
        cleaned = query.strip()
        digits = "".join(ch for ch in cleaned if ch.isalnum())
        hashes = [identifier_hash(normalize_identifier(kind, digits)) for kind in ("imei", "serial") if digits]
        like = f"%{cleaned.lower()}%"
        statement = (
            statement.outerjoin(SerialNumber, SerialNumber.id == WarrantyRegistration.serial_number_id)
            .outerjoin(Customer, Customer.id == WarrantyRegistration.customer_id)
            .where(
                or_(
                    SerialNumber.value_hash.in_(hashes),
                    WarrantyRegistration.identifier_hash.in_(hashes),
                    func.lower(Customer.name).like(like),
                    func.lower(func.coalesce(Customer.company_name, "")).like(like),
                    func.coalesce(Customer.phone, "").like(like),
                )
            )
        )
    rows = list(db.scalars(statement).unique())
    active = db.scalar(
        select(func.count())
        .select_from(WarrantyRegistration)
        .where(*scope, WarrantyRegistration.status != "VOID", WarrantyRegistration.expires_at > now)
    )
    expiring = db.scalar(
        select(func.count())
        .select_from(WarrantyRegistration)
        .where(
            *scope,
            WarrantyRegistration.status == "ACTIVE",
            WarrantyRegistration.expires_at > now,
            WarrantyRegistration.expires_at <= now + timedelta(days=REMIND_DAYS),
        )
    )
    with_plan = db.scalar(
        select(func.count()).select_from(WarrantyRegistration).where(*scope, WarrantyRegistration.plan_id.is_not(None))
    )
    return RegistrationList(
        active_count=int(active or 0),
        expiring_count=int(expiring or 0),
        extended_count=int(with_plan or 0),
        registrations=_registration_out(db, settings, rows),
    )


def lookup(db: Session, settings: Settings, value: str) -> RegistrationOut | None:
    cleaned = "".join(ch for ch in value if ch.isalnum())
    for kind in ("imei", "serial"):
        try:
            digest = identifier_hash(normalize_identifier(kind, cleaned))
        except ValueError:
            continue
        found = registration_for_identifier(db, digest)
        if found is not None:
            return _registration_out(db, settings, [found])[0]
    return None


def list_policies(db: Session) -> list[PolicyOut]:
    return [PolicyOut.model_validate(row) for row in db.scalars(select(WarrantyPolicy).order_by(WarrantyPolicy.scope))]


def save_policy(db: Session, data: PolicyWrite, policy_id: uuid.UUID | None = None) -> list[PolicyOut]:
    row = db.get(WarrantyPolicy, policy_id) if policy_id else None
    if policy_id and row is None:
        raise ApiError(404, "not_found", "Policy was not found.")
    if row is None:
        row = WarrantyPolicy()
        db.add(row)
    row.name = data.name.strip()
    row.scope = data.scope
    row.category_id = data.category_id if data.scope == "CATEGORY" else None
    row.product_id = data.product_id if data.scope == "PRODUCT" else None
    row.months = data.months
    row.terms = data.terms
    row.is_active = data.is_active
    db.commit()
    return list_policies(db)


def list_plans(db: Session) -> list[PlanOut]:
    rows = list(db.scalars(select(WarrantyPlan).order_by(WarrantyPlan.extra_months)))
    products = (
        {row.id: row for row in db.scalars(select(Product).where(Product.id.in_([plan.product_id for plan in rows])))}
        if rows
        else {}
    )
    return [
        PlanOut(
            id=row.id,
            name=row.name,
            extra_months=row.extra_months,
            product_id=row.product_id,
            sku=products[row.product_id].sku if row.product_id in products else "",
            price_cents=products[row.product_id].price_cents if row.product_id in products else 0,
            terms=row.terms,
            is_active=row.is_active,
        )
        for row in rows
    ]


def create_plan(db: Session, data: PlanWrite) -> list[PlanOut]:
    """A plan is sold through its own service product, so registers ring it up like anything else."""
    category, sub = resolve_by_name(db, "Services", "Warranty")
    sku = f"WTY-{data.extra_months}M-{uuid.uuid4().hex[:4].upper()}"
    product = Product(
        sku=sku,
        barcode=f"9{uuid.uuid4().int % 10**12:012d}",
        name=data.name.strip(),
        category=category.name,
        category_id=category.id,
        sub_category_id=sub.id if sub is not None else None,
        price_cents=data.price_cents,
        currency=business_currency(db),
        is_serialized=False,
        is_service=True,
    )
    db.add(product)
    db.flush()
    db.add(
        WarrantyPlan(name=data.name.strip(), extra_months=data.extra_months, product_id=product.id, terms=data.terms)
    )
    db.commit()
    return list_plans(db)
