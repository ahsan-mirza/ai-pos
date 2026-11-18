"""Public demo entry. Authentication is not required. The business code selects the tenant."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, require_device
from app.core.rate_limit import check_identity
from app.schemas.auth import DemoAccessResponse, DemoExchangeRequest, TokenResponse
from app.schemas.devices import PosEnrollRequest, PosEnrollResponse, PosExchangeRequest, TerminalActivation
from app.services.demo_access import exchange_demo_access
from app.services.demo_pos import enroll_pos_demo, exchange_pos_ticket, issue_demo_pos_session

router = APIRouter()


@router.post("/exchange", response_model=DemoAccessResponse)
def exchange(
    body: DemoExchangeRequest,
    http: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> DemoAccessResponse:
    """Signs a visitor into the Demo Explorer for one of the four public businesses.

    The body accepts a business code and nothing else. Host and X-Tenant-Domain are not read.
    """
    code = body.business_code.strip().lower()
    check_identity(
        http,
        "demo-exchange",
        code,
        ip_limit=settings.demo_exchange_ip_limit,
        identity_limit=settings.demo_exchange_code_limit,
        window_seconds=settings.demo_exchange_window_seconds,
    )
    client = http.client.host if http.client else "unknown"
    return exchange_demo_access(settings, code, client_host=client)


def _host(http: Request) -> str:
    return http.client.host if http.client else "unknown"


@router.post("/pos/enroll", response_model=PosEnrollResponse)
def enroll_pos(
    body: PosEnrollRequest,
    http: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> PosEnrollResponse:
    """Issues a single-use POS enrollment ticket for one of the four demo businesses."""
    code = body.business_code.strip().lower()
    check_identity(
        http,
        "demo-pos-enroll",
        code,
        ip_limit=settings.demo_pos_enroll_ip_limit,
        identity_limit=settings.demo_pos_enroll_code_limit,
        window_seconds=settings.demo_exchange_window_seconds,
    )
    return enroll_pos_demo(settings, code, client_host=_host(http))


@router.post("/pos/exchange", response_model=TerminalActivation)
def exchange_pos(
    body: PosExchangeRequest,
    http: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> TerminalActivation:
    """Consumes one enrollment ticket and returns the register device token for that demo."""
    ticket = body.enrollment_ticket.strip()
    code = ticket.split(".", 1)[0] if "." in ticket else "invalid"
    check_identity(
        http,
        "demo-pos-exchange",
        code,
        ip_limit=settings.demo_pos_exchange_ip_limit,
        identity_limit=settings.demo_pos_exchange_code_limit,
        window_seconds=settings.demo_exchange_window_seconds,
    )
    return exchange_pos_ticket(settings, ticket, body.machine_name, client_host=_host(http))


@router.post("/pos/session", response_model=TokenResponse)
def demo_pos_session(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(require_device)],
) -> TokenResponse:
    """Opens the Demo Explorer POS session for a register enrolled as a demo terminal.

    A device token is required. A portal token is not accepted. Production registers are refused.
    """
    if principal.device is None:
        from app.core.errors import ApiError

        raise ApiError(403, "pos_demo_unavailable", "This register cannot open a demo session.")
    return issue_demo_pos_session(db, settings, principal.device)
