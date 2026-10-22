import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.pagination import Offset, set_total
from app.core.permissions import Permission
from app.schemas.accounting import (
    AccountingSettings,
    AccountLedger,
    BalanceSheet,
    CloseYearRequest,
    CorporateTaxEstimate,
    GlAccountRow,
    GlAccountWrite,
    IncomeStatement,
    JournalEntryOut,
    LockWrite,
    ManualJournalCreate,
    PostRequest,
    PostResult,
    ProvisionRequest,
    ReverseRequest,
    TrialBalance,
)
from app.services import gl_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanAccount = Annotated[Principal, Depends(authorize(Permission.ACCOUNTING_MANAGE))]
From = Annotated[date, Query(alias="from")]
To = Annotated[date, Query(alias="to")]


@router.get("/settings", response_model=AccountingSettings)
def get_settings(db: Db, _: CanAccount) -> AccountingSettings:
    return gl_service.settings(db)


@router.put("/settings", response_model=AccountingSettings)
def put_settings(payload: AccountingSettings, db: Db, _: CanAccount) -> AccountingSettings:
    return gl_service.update_settings(db, payload.fiscal_year_start_month)


@router.post("/lock", response_model=AccountingSettings)
def lock(payload: LockWrite, db: Db, _: CanAccount) -> AccountingSettings:
    return gl_service.lock(db, payload.locked_until)


@router.get("/accounts", response_model=list[GlAccountRow])
def accounts(db: Db, _: CanAccount) -> list[GlAccountRow]:
    return gl_service.list_accounts(db)


@router.post("/accounts", response_model=GlAccountRow, status_code=201)
def create_account(payload: GlAccountWrite, db: Db, _: CanAccount) -> GlAccountRow:
    return gl_service.save_account(db, payload)


@router.put("/accounts/{account_id}", response_model=GlAccountRow)
def update_account(account_id: uuid.UUID, payload: GlAccountWrite, db: Db, _: CanAccount) -> GlAccountRow:
    return gl_service.save_account(db, payload, account_id)


@router.get("/accounts/{account_id}/ledger", response_model=AccountLedger)
def ledger(account_id: uuid.UUID, db: Db, _: CanAccount, start: From, end: To) -> AccountLedger:
    return gl_service.account_ledger(db, account_id, start, end)


@router.post("/post", response_model=PostResult)
def post(payload: PostRequest, db: Db, principal: CanAccount) -> PostResult:
    return gl_service.post_range(db, principal, payload.start, payload.end)


@router.get("/journals", response_model=list[JournalEntryOut])
def journals(
    db: Db,
    _: CanAccount,
    response: Response,
    offset: Offset,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
    journal: Annotated[str | None, Query(max_length=12)] = None,
    q: Annotated[str | None, Query(max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[JournalEntryOut]:
    rows, total = gl_service.list_journals(
        db, start=start, end=end, journal=journal, query=q, offset=offset, limit=limit
    )
    set_total(response, total)
    return rows


@router.post("/journals", response_model=JournalEntryOut, status_code=201)
def create_journal(payload: ManualJournalCreate, db: Db, principal: CanAccount) -> JournalEntryOut:
    return gl_service.create_manual(db, principal, payload)


@router.post("/journals/{entry_id}/reverse", response_model=JournalEntryOut)
def reverse(entry_id: uuid.UUID, payload: ReverseRequest, db: Db, principal: CanAccount) -> JournalEntryOut:
    return gl_service.reverse_manual(db, principal, entry_id, payload.entry_date, payload.memo)


@router.get("/trial-balance", response_model=TrialBalance)
def trial_balance(db: Db, _: CanAccount, start: From, end: To) -> TrialBalance:
    return gl_service.trial_balance(db, start, end)


@router.get("/balance-sheet", response_model=BalanceSheet)
def balance_sheet(db: Db, _: CanAccount, as_of: date | None = None) -> BalanceSheet:
    return gl_service.balance_sheet(db, as_of or datetime.now(UTC).date())


@router.get("/income-statement", response_model=IncomeStatement)
def income_statement(db: Db, _: CanAccount, start: From, end: To) -> IncomeStatement:
    return gl_service.income_statement(db, start, end)


@router.post("/close-year", response_model=JournalEntryOut | None)
def close_year(payload: CloseYearRequest, db: Db, principal: CanAccount) -> JournalEntryOut | None:
    return gl_service.close_year(db, principal, payload.year_end)


@router.get("/corporate-tax", response_model=CorporateTaxEstimate)
def corporate_tax(
    db: Db,
    _: CanAccount,
    year: Annotated[int, Query(ge=2023, le=2100)],
    add_backs_cents: Annotated[int, Query(ge=0, le=100_000_000_000)] = 0,
    deductions_cents: Annotated[int, Query(ge=0, le=100_000_000_000)] = 0,
) -> CorporateTaxEstimate:
    return gl_service.corporate_tax(db, year, add_backs_cents, deductions_cents)


@router.post("/corporate-tax/provision", response_model=JournalEntryOut, status_code=201)
def provision(payload: ProvisionRequest, db: Db, principal: CanAccount) -> JournalEntryOut:
    return gl_service.post_provision(db, principal, payload.fiscal_year, payload.amount_cents)
