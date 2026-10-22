import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, require_capability
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.pagination import Offset, set_total
from app.core.permissions import Permission
from app.schemas.dunning import DunningResult, StatementSend
from app.schemas.payloads import CustomerType, SaleOut
from app.schemas.wholesale import (
    CreditHoldWrite,
    CreditRiskOut,
    CustomerHistoryLine,
    CustomerOut,
    CustomerUpdate,
    CustomerWrite,
    LedgerAdjustment,
    PaymentCreate,
    PaymentOut,
    StatementOut,
)
from app.services import (
    catalog_service,
    credit_risk_service,
    credit_service,
    customer_service,
    customer_sync,  # noqa: F401  registers the `customer` sync handler
    dunning_service,
)

router = APIRouter()
CreditModule = Depends(require_capability(Capability.B2B_CREDIT))

Db = Annotated[Session, Depends(get_db)]
CanManage = Annotated[Principal, Depends(authorize(Permission.CUSTOMERS_MANAGE))]
AtRegister = Annotated[
    Principal,
    Depends(authorize(Permission.POS_ACCESS, allow_device=True, scopes=("pos", "portal"))),
]


def _user_id(principal: Principal) -> uuid.UUID | None:
    return principal.user.id if principal.user is not None else None


@router.get("", response_model=list[CustomerOut])
def list_customers(
    db: Db,
    _: CanManage,
    response: Response,
    offset: Offset,
    q: Annotated[str | None, Query(max_length=80)] = None,
    customer_type: CustomerType | None = None,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[CustomerOut]:
    rows, total = customer_service.list_customers(
        db, query=q, customer_type=customer_type, include_inactive=include_inactive, limit=limit, offset=offset
    )
    set_total(response, total)
    return rows


@router.get("/sync", response_model=list[CustomerOut])
def sync_customers(db: Db, _: AtRegister) -> list[CustomerOut]:
    """Active accounts with balances for the register's offline customer cache."""
    return customer_service.sync_customers(db)


@router.get("/risk", response_model=list[CreditRiskOut], dependencies=[CreditModule])
def credit_risk_portfolio(db: Db, _: CanManage) -> list[CreditRiskOut]:
    """Wholesale accounts ranked by credit risk, with the factors behind each score."""
    return credit_risk_service.portfolio(db)


@router.get("/{customer_id}/risk", response_model=CreditRiskOut, dependencies=[CreditModule])
def credit_risk(customer_id: uuid.UUID, db: Db, _: CanManage) -> CreditRiskOut:
    return credit_risk_service.for_customer(db, customer_id)


@router.post("/statements/send", response_model=DunningResult)
def send_statements(payload: StatementSend, db: Db, _: CanManage) -> DunningResult:
    return dunning_service.send_statements(db, payload.customer_ids)


@router.get("/{customer_id}/statement.pdf", response_class=Response)
def statement_pdf(customer_id: uuid.UUID, db: Db, _: CanManage) -> Response:
    return Response(
        dunning_service.render_statement(db, customer_id),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="statement-{str(customer_id)[:8]}.pdf"'},
    )


@router.post("", response_model=CustomerOut, status_code=201)
def create_customer(payload: CustomerWrite, db: Db, _: CanManage) -> CustomerOut:
    return customer_service.create_customer(db, payload)


@router.get("/{customer_id}/history", response_model=list[CustomerHistoryLine])
def history(
    customer_id: uuid.UUID,
    db: Db,
    _: AtRegister,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> list[CustomerHistoryLine]:
    return customer_service.purchase_history(db, customer_id, limit)


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: uuid.UUID, db: Db, _: CanManage) -> CustomerOut:
    return customer_service.customer_detail(db, customer_id)


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: uuid.UUID, payload: CustomerUpdate, db: Db, _: CanManage) -> CustomerOut:
    return customer_service.update_customer(db, customer_id, payload)


@router.get("/{customer_id}/statement", response_model=StatementOut)
def statement(customer_id: uuid.UUID, db: Db, _: CanManage) -> StatementOut:
    return customer_service.statement(db, customer_id)


@router.get("/{customer_id}/sales", response_model=list[SaleOut])
def customer_sales(
    customer_id: uuid.UUID,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
    principal: CanManage,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[SaleOut]:
    customer_service.get_customer(db, customer_id)
    return catalog_service.list_sales(
        db, settings, limit=limit, store_scope=principal.store_id, customer_id=customer_id
    )


@router.post("/{customer_id}/payments", response_model=PaymentOut, status_code=201)
def receive_payment(customer_id: uuid.UUID, payload: PaymentCreate, db: Db, principal: CanManage) -> PaymentOut:
    return customer_service.receive_payment(db, customer_id, payload, _user_id(principal))


@router.post("/{customer_id}/credit-hold", response_model=CustomerOut)
def credit_hold(
    customer_id: uuid.UUID,
    payload: CreditHoldWrite,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
    _: CanManage,
) -> CustomerOut:
    customer = customer_service.get_customer(db, customer_id)
    credit_service.set_hold(db, settings, customer, hold=payload.hold, reason=payload.reason)
    db.commit()
    return customer_service.customer_detail(db, customer.id)


@router.post("/{customer_id}/adjustments", response_model=CustomerOut, status_code=201)
def adjust_balance(customer_id: uuid.UUID, payload: LedgerAdjustment, db: Db, principal: CanManage) -> CustomerOut:
    return customer_service.adjust_balance(db, customer_id, payload, _user_id(principal))
