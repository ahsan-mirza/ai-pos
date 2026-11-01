"""Prepaid credits. One credit is one provider-accepted campaign submission, not a delivery."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from reach.models import ReachCreditAccount, ReachCreditTransaction


def snapshot(db: Session) -> dict | None:
    account = _account(db)
    if account is None:
        return None
    available = account.balance - account.reserved
    return {"balance": account.balance, "reserved": account.reserved, "available": available}


def transactions(db: Session, limit: int = 50) -> list[ReachCreditTransaction]:
    account = _account(db)
    if account is None:
        return []
    return list(
        db.scalars(
            select(ReachCreditTransaction)
            .where(ReachCreditTransaction.account_id == account.id)
            .order_by(ReachCreditTransaction.created_at.desc())
            .limit(limit)
        )
    )


def allocate(db: Session, *, units: int, note: str, idempotency_key: str) -> dict:
    account = _account(db) or _open(db)
    existing = db.scalar(
        select(ReachCreditTransaction).where(ReachCreditTransaction.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return snapshot(db) or {"balance": 0, "reserved": 0, "available": 0}
    db.execute(
        update(ReachCreditAccount)
        .where(ReachCreditAccount.id == account.id)
        .values(balance=ReachCreditAccount.balance + units)
    )
    db.add(
        ReachCreditTransaction(
            account_id=account.id,
            kind="allocate",
            units=units,
            idempotency_key=idempotency_key,
            note=note[:300],
        )
    )
    db.flush()
    db.refresh(account)
    found = snapshot(db)
    assert found is not None
    return found


def reserve(db: Session, campaign_id: uuid.UUID, units: int) -> None:
    """Holds units for a campaign. A missing account means this store is not on prepaid credits."""
    if units <= 0:
        return
    account = _account(db)
    if account is None:
        raise ApiError(422, "credits_required", "Ask AxizPOS to allocate Reach credits before sending on Evolution.")
    key = f"reserve:{campaign_id}"
    if db.scalar(select(ReachCreditTransaction.id).where(ReachCreditTransaction.idempotency_key == key)):
        return
    updated = db.execute(
        update(ReachCreditAccount)
        .where(
            ReachCreditAccount.id == account.id,
            ReachCreditAccount.balance - ReachCreditAccount.reserved >= units,
        )
        .values(reserved=ReachCreditAccount.reserved + units)
    )
    if updated.rowcount != 1:
        raise ApiError(422, "insufficient_credits", "Not enough Reach credits for this campaign.")
    db.add(
        ReachCreditTransaction(
            account_id=account.id,
            kind="reserve",
            units=units,
            idempotency_key=key,
            campaign_id=campaign_id,
            note="Held for campaign",
        )
    )
    db.flush()


def consume(db: Session, message_id: uuid.UUID, campaign_id: uuid.UUID | None) -> None:
    _settle(db, message_id, campaign_id, kind="consume")


def release(db: Session, message_id: uuid.UUID, campaign_id: uuid.UUID | None) -> None:
    _settle(db, message_id, campaign_id, kind="release")


def _settle(db: Session, message_id: uuid.UUID, campaign_id: uuid.UUID | None, *, kind: str) -> None:
    account = _account(db)
    if account is None:
        return
    key = f"{kind}:{message_id}"
    if db.scalar(select(ReachCreditTransaction.id).where(ReachCreditTransaction.idempotency_key == key)):
        return
    if account.reserved < 1:
        return
    values = {"reserved": ReachCreditAccount.reserved - 1}
    if kind == "consume":
        values["balance"] = ReachCreditAccount.balance - 1
    updated = db.execute(
        update(ReachCreditAccount).where(ReachCreditAccount.id == account.id, ReachCreditAccount.reserved >= 1).values(**values)
    )
    if updated.rowcount != 1:
        return
    try:
        with db.begin_nested():
            db.add(
                ReachCreditTransaction(
                    account_id=account.id,
                    kind=kind,
                    units=1,
                    idempotency_key=key,
                    campaign_id=campaign_id,
                    outbound_message_id=message_id,
                    note="Provider accepted" if kind == "consume" else "Released before acceptance",
                )
            )
            db.flush()
    except IntegrityError:
        return


def _account(db: Session) -> ReachCreditAccount | None:
    return db.scalar(select(ReachCreditAccount).where(ReachCreditAccount.purpose == "marketing"))


def _open(db: Session) -> ReachCreditAccount:
    account = ReachCreditAccount(purpose="marketing", balance=0, reserved=0)
    db.add(account)
    db.flush()
    return account
