"""Public pages a customer opens from a link: approve a repair estimate, or see where the job is. No login.
The token is the secret. Requests are rate limited per IP."""

import html
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ApiError
from app.core.rate_limit import check
from app.integrations.payments.base import money
from app.models.store import Store
from app.services import repair_workshop_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]

_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>body{{font-family:system-ui,sans-serif;background:#f4f4f5;margin:0;display:grid;place-items:center;
min-height:100vh;color:#18181b}}main{{background:#fff;border-radius:20px;padding:28px;max-width:400px;width:90%;
box-shadow:0 10px 30px #0001}}h1{{font-size:20px;margin:0 0 8px}}p{{color:#52525b;line-height:1.45}}
.amount{{font-size:28px;font-weight:700;margin:12px 0}}ol{{padding-left:1.2rem;margin:12px 0}}
li{{margin:6px 0;color:#52525b}}li.now{{color:#18181b;font-weight:650}}button{{width:100%;height:48px;
border-radius:14px;border:0;font-size:16px;font-weight:600;margin-top:10px;cursor:pointer}}
.ok{{background:#18181b;color:#fff}}.no{{background:#f4f4f5;color:#18181b}}</style>
</head><body><main>{body}</main></body></html>"""


def _page(title: str, body: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(_PAGE.format(title=html.escape(title), body=body), status_code=status_code)


def _limited(request: Request, bucket: str, limit: int) -> HTMLResponse | None:
    try:
        check(request, bucket, limit=limit, window_seconds=60)
    except ApiError as exc:
        return _page("Please wait", f"<h1>Too many tries</h1><p>{html.escape(exc.message)}</p>", 429)
    return None


@router.get("/repair/approve/{token}", response_class=HTMLResponse)
def approval_page(token: str, request: Request, db: Db) -> HTMLResponse:
    blocked = _limited(request, "repair-approve", 10)
    if blocked is not None:
        return blocked
    try:
        ticket = repair_workshop_service.ticket_for_approval_token(db, token)
    except ApiError as exc:
        return _page("Repair approval", f"<h1>Link not valid</h1><p>{html.escape(exc.message)}</p>", exc.status_code)
    device = html.escape(ticket.device_model)
    if not repair_workshop_service.approval_open(ticket):
        return _page(
            "Repair approval",
            f"<h1>{device}</h1><p>This approval link has expired. Contact the store to decide.</p>",
            410,
        )
    amount = ticket.approval_amount_cents or 0
    store = db.get(Store, ticket.store_id)
    note = f"<p>{html.escape(ticket.approval_note)}</p>" if ticket.approval_note else ""
    body = (
        f"<h1>Approve the repair?</h1><p>{html.escape(store.name if store else 'The store')} · {device}</p>"
        f"<div class='amount'>{html.escape(ticket.currency)} {money(amount)}</div>{note}"
        f"<form method='post'><button class='ok' name='outcome' value='approve'>Approve</button>"
        f"<button class='no' name='outcome' value='decline'>Decline</button></form>"
    )
    return _page("Approve the repair", body)


@router.post("/repair/approve/{token}", response_class=HTMLResponse)
def approval_decision(token: str, request: Request, db: Db, outcome: Annotated[str, Form()] = "") -> HTMLResponse:
    blocked = _limited(request, "repair-approve", 10)
    if blocked is not None:
        return blocked
    if outcome not in ("approve", "decline"):
        return _page("Repair approval", "<h1>Choose approve or decline</h1>", 422)
    try:
        ticket = repair_workshop_service.decide_by_link(db, token, outcome == "approve")
    except ApiError as exc:
        return _page(
            "Repair approval", f"<h1>Could not save that</h1><p>{html.escape(exc.message)}</p>", exc.status_code
        )
    device = html.escape(ticket.device_model)
    if outcome == "approve":
        return _page(
            "Approved", f"<h1>Approved</h1><p>We will repair your {device} and message you when it is ready.</p>"
        )
    return _page(
        "Declined", f"<h1>Declined</h1><p>Your {device} will be returned unrepaired. Collect it from the store.</p>"
    )


@router.get("/track/{token}", response_class=HTMLResponse)
def tracking_page(token: str, request: Request, db: Db) -> HTMLResponse:
    blocked = _limited(request, "repair-track", 30)
    if blocked is not None:
        return blocked
    try:
        view = repair_workshop_service.tracking(db, token)
    except ApiError as exc:
        return _page("Repair tracking", f"<h1>Not found</h1><p>{html.escape(exc.message)}</p>", exc.status_code)
    steps = "".join(
        f"<li class='{'now' if step.get('current') else ''}'>{html.escape(str(step.get('label', '')))}"
        f"{' · now' if step.get('current') else ''}</li>"
        for step in view.steps
    )
    promise = ""
    if view.promised_at is not None:
        promise = f"<p>Promised {html.escape(view.promised_at.strftime('%d %b %Y'))}</p>"
    balance = ""
    if view.balance_due_cents:
        balance = f"<p>Balance due {html.escape(view.currency)} {money(view.balance_due_cents)}</p>"
    body = (
        f"<h1>{html.escape(view.device_model)}</h1>"
        f"<p>{html.escape(view.store_name)} · job {html.escape(view.reference)}</p>"
        f"<div class='amount'>{html.escape(view.status_label)}</div>{promise}{balance}<ol>{steps}</ol>"
    )
    return _page(f"Repair {view.reference}", body)
