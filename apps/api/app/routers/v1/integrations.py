"""Provider-facing endpoints: signed webhooks, the simulated BNPL checkout a customer's phone opens, and the
page a real checkout returns the customer to. None of them take a staff login."""

import html
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.errors import ApiError
from app.integrations.payments.base import money
from app.integrations.payments.registry import LABELS
from app.models.payment_intent import PaymentIntent
from app.schemas.payments import IntentOut
from app.services import integrated_payment_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]

_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>body{{font-family:system-ui,sans-serif;background:#f4f4f5;margin:0;display:grid;place-items:center;
min-height:100vh}}main{{background:#fff;border-radius:20px;padding:28px;max-width:360px;width:90%;
box-shadow:0 10px 30px #0001;text-align:center}}h1{{font-size:20px;margin:0 0 4px}}p{{color:#52525b}}
.amount{{font-size:32px;font-weight:700;color:#18181b;margin:16px 0}}button{{width:100%;height:48px;
border-radius:14px;border:0;font-size:16px;font-weight:600;margin-top:10px;cursor:pointer}}
.ok{{background:#18181b;color:#fff}}.no{{background:#f4f4f5;color:#18181b}}small{{color:#a1a1aa}}</style>
</head><body><main>{body}</main></body></html>"""


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(_PAGE.format(title=html.escape(title), body=body))


def _simulated_intent(db: Session, settings: Settings, intent_id: uuid.UUID) -> PaymentIntent:
    intent = db.get(PaymentIntent, intent_id)
    if (
        intent is None
        or intent.channel != "BNPL"
        or not (intent.provider == "simulator" or (intent.provider_ref or "").startswith("sim-"))
        or not integrated_payment_service.simulator_controls(db, settings)
    ):
        raise ApiError(404, "not_found", "Checkout was not found.")
    return intent


def _checkout_body(intent: PaymentIntent, note: str = "") -> str:
    label = html.escape(LABELS.get(intent.provider, intent.provider))
    amount = html.escape(f"{intent.currency} {money(intent.amount_cents)}")
    quarter = html.escape(f"{intent.currency} {money(-(-intent.amount_cents // 4))}")
    if intent.status not in ("PENDING", "AUTHORIZED"):
        state = {"PAID": "Approved. You can return to the till.", "DECLINED": "Not approved."}.get(
            intent.status, f"This checkout is {intent.status.lower()}."
        )
        return f"<h1>{label}</h1><div class='amount'>{amount}</div><p>{html.escape(state)}</p>"
    return (
        f"<h1>{label} checkout</h1><p>Simulated pay later. No real money moves.</p>"
        f"<div class='amount'>{amount}</div><p>4 payments of {quarter}</p>"
        "<form method='post'><button class='ok' name='outcome' value='approve'>Approve plan</button>"
        "<button class='no' name='outcome' value='decline'>Decline</button></form>"
        f"<small>{html.escape(note)}</small>"
    )


@router.get("/payments/simulator/checkout/{intent_id}", response_class=HTMLResponse)
def simulator_checkout(intent_id: uuid.UUID, db: Db, settings: Config) -> HTMLResponse:
    intent = _simulated_intent(db, settings, intent_id)
    return _page("Pay later checkout", _checkout_body(intent, f"Reference {intent.reference}"))


@router.post("/payments/simulator/checkout/{intent_id}", response_class=HTMLResponse)
def simulator_decide(
    intent_id: uuid.UUID, db: Db, settings: Config, outcome: Annotated[str, Form(pattern="^(approve|decline)$")]
) -> HTMLResponse:
    intent = _simulated_intent(db, settings, intent_id)
    integrated_payment_service.simulate(db, settings, intent.id, outcome, None)
    db.refresh(intent)
    return _page("Pay later checkout", _checkout_body(intent))


@router.get("/payments/return/{intent_id}", response_class=HTMLResponse)
def checkout_return(intent_id: uuid.UUID, db: Db) -> HTMLResponse:
    intent = db.get(PaymentIntent, intent_id)
    if intent is None:
        raise ApiError(404, "not_found", "Checkout was not found.")
    return _page("Thank you", "<h1>Thank you</h1><p>Your payment is being confirmed. Please return to the till.</p>")


@router.post("/payments/{provider}/webhook", response_model=IntentOut)
async def payments_webhook(provider: str, request: Request, db: Db, settings: Config) -> IntentOut:
    body = await request.body()
    headers = {key.lower(): value for key, value in request.headers.items()}
    return integrated_payment_service.handle_webhook(db, settings, provider, body, headers, dict(request.query_params))
