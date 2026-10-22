"""Store-credit vouchers: issued by returns, spent as a sale tender. Vouchers work at every branch."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import ApiError, SyncRejected
from app.models.customer import Customer
from app.models.sale import Sale
from app.models.store import Store
from app.models.store_credit import StoreCredit, StoreCreditRedemption
from app.schemas.store_credit import StoreCreditList, StoreCreditOut, StoreCreditUseOut


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _out(db: Session, credit: StoreCredit) -> StoreCreditOut:
    uses = db.execute(
        select(StoreCreditRedemption, Sale.invoice_number)
        .join(Sale, Sale.id == StoreCreditRedemption.sale_id)
        .where(StoreCreditRedemption.store_credit_id == credit.id)
        .order_by(StoreCreditRedemption.created_at)
    ).all()
    store = db.get(Store, credit.store_id)
    customer = db.get(Customer, credit.customer_id) if credit.customer_id is not None else None
    expired = credit.expires_at is not None and _aware(credit.expires_at) < datetime.now(UTC)
    return StoreCreditOut(
        id=credit.id,
        code=credit.code,
        store_id=credit.store_id,
        store_name=store.name if store is not None else "",
        currency=credit.currency,
        initial_cents=credit.initial_cents,
        balance_cents=credit.balance_cents,
        issued_at=_aware(credit.created_at),
        return_id=credit.return_id,
        kind=credit.kind,  # type: ignore[arg-type]
        issued_sale_id=credit.issued_sale_id,
        customer_id=credit.customer_id,
        customer_name=customer.name if customer is not None else None,
        expires_at=_aware(credit.expires_at) if credit.expires_at is not None else None,
        voided_at=_aware(credit.voided_at) if credit.voided_at is not None else None,
        note=credit.note or "",
        usable=credit.voided_at is None and not expired and credit.balance_cents > 0,
        uses=[
            StoreCreditUseOut(
                sale_id=use.sale_id,
                invoice_number=invoice,
                amount_cents=use.amount_cents,
                used_at=_aware(use.created_at),
            )
            for use, invoice in uses
        ],
    )


def lookup(db: Session, code: str) -> StoreCreditOut:
    credit = db.scalar(select(StoreCredit).where(StoreCredit.code == code.strip().upper()))
    if credit is None:
        raise ApiError(
            404,
            "not_found",
            "No store credit with that code. A voucher from an offline return appears once that register syncs.",
        )
    return _out(db, credit)


def list_credits(
    db: Session, *, open_only: bool, store_scope: uuid.UUID | None, limit: int, kind: str = "VOUCHER"
) -> StoreCreditList:
    query = select(StoreCredit).where(StoreCredit.kind == kind).order_by(StoreCredit.created_at.desc()).limit(limit)
    totals = select(func.coalesce(func.sum(StoreCredit.balance_cents), 0), func.count()).where(
        StoreCredit.balance_cents > 0, StoreCredit.kind == kind, StoreCredit.voided_at.is_(None)
    )
    if open_only:
        query = query.where(StoreCredit.balance_cents > 0, StoreCredit.voided_at.is_(None))
    if store_scope is not None:
        query = query.where(StoreCredit.store_id == store_scope)
        totals = totals.where(StoreCredit.store_id == store_scope)
    outstanding, open_count = db.execute(totals).one()
    return StoreCreditList(
        items=[_out(db, credit) for credit in db.scalars(query)],
        outstanding_cents=int(outstanding),
        open_count=int(open_count),
    )


def redeem(
    db: Session,
    *,
    code: str | None,
    sale_id: uuid.UUID,
    store_id: uuid.UUID,
    amount_cents: int,
    currency: str,
    kind: str = "VOUCHER",
    at: datetime | None = None,
) -> None:
    """Spend part of a voucher or gift card on a sale. Rejecting keeps the sale in the register's Sync Center."""
    label = "Gift card" if kind == "GIFT_CARD" else "Store credit"
    if code is None:
        raise SyncRejected(f"{label} tenders must carry the {'card' if kind == 'GIFT_CARD' else 'voucher'} code.")
    credit = db.scalar(select(StoreCredit).where(StoreCredit.code == code))
    if credit is None:
        raise SyncRejected(f"{label} {code} does not exist.")
    if credit.kind != kind:
        raise SyncRejected(f"{code} is a {'gift card' if credit.kind == 'GIFT_CARD' else 'store credit voucher'}.")
    if credit.voided_at is not None:
        raise SyncRejected(f"{label} {code} was voided.")
    if credit.expires_at is not None and _aware(credit.expires_at) < (at or datetime.now(UTC)):
        raise SyncRejected(f"{label} {code} expired on {_aware(credit.expires_at):%d %b %Y}.")
    if credit.currency != currency:
        raise SyncRejected(f"{label} {code} is in {credit.currency}, not {currency}.")
    # Conditional decrement so two registers spending the same voucher cannot both succeed.
    spent = db.execute(
        update(StoreCredit)
        .where(StoreCredit.id == credit.id, StoreCredit.balance_cents >= amount_cents)
        .values(balance_cents=StoreCredit.balance_cents - amount_cents)
        .execution_options(synchronize_session=False)
    )
    if spent.rowcount != 1:
        db.refresh(credit)
        raise SyncRejected(
            f"{label} {code} has only {credit.balance_cents / 100:,.2f} {currency} left; "
            f"the sale used {amount_cents / 100:,.2f}."
        )
    db.refresh(credit)
    db.add(
        StoreCreditRedemption(store_credit_id=credit.id, sale_id=sale_id, store_id=store_id, amount_cents=amount_cents)
    )
