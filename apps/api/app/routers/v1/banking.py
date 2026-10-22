import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.errors import ApiError
from app.core.pagination import Offset, set_total
from app.core.permissions import Permission
from app.schemas.banking import (
    AutoMatchOut,
    BankAccountOut,
    BankAccountWrite,
    BookChargeWrite,
    CandidateOut,
    IgnoreWrite,
    LineStatus,
    MatchWrite,
    ReconciliationSummary,
    StatementImportOut,
    StatementLineOut,
    StatementOut,
)
from app.services import bank_service
from app.services.bank_statement_parser import MAX_STATEMENT_BYTES

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanBank = Annotated[Principal, Depends(authorize(Permission.BANKING_MANAGE))]


@router.get("/accounts", response_model=list[BankAccountOut])
def accounts(db: Db, _: CanBank) -> list[BankAccountOut]:
    return bank_service.list_accounts(db)


@router.post("/accounts", response_model=BankAccountOut, status_code=201)
def create_account(payload: BankAccountWrite, db: Db, _: CanBank) -> BankAccountOut:
    return bank_service.save_account(db, payload)


@router.put("/accounts/{account_id}", response_model=BankAccountOut)
def update_account(account_id: uuid.UUID, payload: BankAccountWrite, db: Db, _: CanBank) -> BankAccountOut:
    return bank_service.save_account(db, payload, account_id)


@router.post("/accounts/{account_id}/statements", response_model=StatementImportOut, status_code=201)
async def import_statement(
    account_id: uuid.UUID, db: Db, principal: CanBank, file: Annotated[UploadFile, File()]
) -> StatementImportOut:
    data = await file.read(MAX_STATEMENT_BYTES + 1)
    if len(data) > MAX_STATEMENT_BYTES:
        raise ApiError(413, "file_too_large", "Statement files are limited to 5 MB.")
    return bank_service.import_statement(db, principal, account_id, file.filename or "statement.csv", data)


@router.get("/accounts/{account_id}/statements", response_model=list[StatementOut])
def statements(account_id: uuid.UUID, db: Db, _: CanBank) -> list[StatementOut]:
    return bank_service.list_statements(db, account_id)


@router.get("/accounts/{account_id}/lines", response_model=list[StatementLineOut])
def lines(
    account_id: uuid.UUID,
    db: Db,
    _: CanBank,
    response: Response,
    offset: Offset,
    status: LineStatus | None = None,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[StatementLineOut]:
    rows, total = bank_service.list_lines(
        db, account_id, status=status, start=start, end=end, offset=offset, limit=limit
    )
    set_total(response, total)
    return rows


@router.get("/accounts/{account_id}/summary", response_model=ReconciliationSummary)
def summary(account_id: uuid.UUID, db: Db, _: CanBank) -> ReconciliationSummary:
    return bank_service.summary(db, account_id)


@router.post("/accounts/{account_id}/auto-match", response_model=AutoMatchOut)
def auto_match(account_id: uuid.UUID, db: Db, _: CanBank) -> AutoMatchOut:
    return bank_service.auto_match(db, account_id)


@router.get("/lines/{line_id}/candidates", response_model=list[CandidateOut])
def candidates(line_id: uuid.UUID, db: Db, _: CanBank) -> list[CandidateOut]:
    return bank_service.candidates(db, line_id)


@router.post("/lines/{line_id}/match", response_model=StatementLineOut)
def match(line_id: uuid.UUID, payload: MatchWrite, db: Db, principal: CanBank) -> StatementLineOut:
    return bank_service.match(db, principal, line_id, payload.key, payload.note)


@router.post("/lines/{line_id}/book-charge", response_model=StatementLineOut)
def book_charge(line_id: uuid.UUID, payload: BookChargeWrite, db: Db, principal: CanBank) -> StatementLineOut:
    return bank_service.book_charge(db, principal, line_id, payload.store_id)


@router.post("/lines/{line_id}/unmatch", response_model=StatementLineOut)
def unmatch(line_id: uuid.UUID, db: Db, principal: CanBank) -> StatementLineOut:
    return bank_service.unmatch(db, principal, line_id)


@router.post("/lines/{line_id}/ignore", response_model=StatementLineOut)
def ignore(line_id: uuid.UUID, payload: IgnoreWrite, db: Db, principal: CanBank) -> StatementLineOut:
    return bank_service.ignore(db, principal, line_id, payload.note)
