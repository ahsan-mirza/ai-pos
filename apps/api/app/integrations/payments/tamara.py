"""Tamara instalments at the till. Checkout opens on the customer's phone; once Tamara approves the order we
authorise and capture it at once, since the customer leaves with the goods.

API (Bearer API token): POST /checkout, GET /orders/{id}, POST /orders/{id}/authorise, POST /payments/capture,
POST /payments/simplified-refund/{order_id}, POST /orders/{id}/cancel. Notifications carry a `tamaraToken`
(query string or Bearer header): an HS256 JWT signed with the notification token."""

from datetime import UTC, datetime

import jwt

from app.integrations.http import ProviderError, call, client
from app.integrations.payments.base import (
    PaymentRef,
    ProviderState,
    ProviderStatus,
    RefundResult,
    StartRequest,
    WebhookEvent,
    cents,
)

STATES: dict[str, ProviderState] = {
    "NEW": "PENDING",
    "APPROVED": "AUTHORIZED",
    "AUTHORISED": "AUTHORIZED",
    "PARTIALLY_CAPTURED": "AUTHORIZED",
    "FULLY_CAPTURED": "PAID",
    "PARTIALLY_REFUNDED": "PAID",
    "FULLY_REFUNDED": "PAID",
    "DECLINED": "DECLINED",
    "EXPIRED": "EXPIRED",
    "CANCELED": "CANCELLED",
    "CANCELLED": "CANCELLED",
}


def _amount(cents_value: int, currency: str) -> dict:
    return {"amount": round(cents_value / 100, 2), "currency": currency}


class TamaraAdapter:
    name = "tamara"
    label = "Tamara"
    channel = "BNPL"
    simulated = False

    def __init__(self, *, api_token: str, notification_token: str | None, base_url: str, timeout: float) -> None:
        self._headers = {"Authorization": f"Bearer {api_token}", "Accept": "application/json"}
        self._notification = notification_token
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def _http(self):
        return client(self._base, timeout=self._timeout, headers=self._headers)

    @staticmethod
    def _order_status(body: dict) -> ProviderStatus:
        raw = str(body.get("status") or body.get("order_status") or "").upper()
        state = STATES.get(raw, "PENDING")
        total = body.get("total_amount") or {}
        return ProviderStatus(
            status=state,
            provider_ref=body.get("order_id"),
            amount_cents=cents(total.get("amount")) if total else None,
            failure_reason="Tamara declined the customer." if state == "DECLINED" else None,
        )

    def start(self, request: StartRequest) -> ProviderStatus:
        if not request.customer_phone:
            raise ProviderError("Tamara needs the customer's mobile number.")
        first, _, last = (request.customer_name or "Walk-in Customer").partition(" ")
        payload = {
            "order_reference_id": request.reference,
            "order_number": request.reference,
            "total_amount": _amount(request.amount_cents, request.currency),
            "description": request.description or f"In-store purchase {request.reference}",
            "country_code": "SA" if request.currency == "SAR" else "AE",
            "payment_type": "PAY_BY_INSTALMENTS",
            "platform": "AI POS in-store",
            "locale": "en_US",
            "items": [
                {
                    "name": item.name[:120],
                    "type": "Physical",
                    "reference_id": item.sku or item.name[:40],
                    "sku": item.sku or item.name[:40],
                    "quantity": item.quantity,
                    "unit_price": _amount(item.unit_cents, request.currency),
                    "total_amount": _amount(item.unit_cents * item.quantity, request.currency),
                }
                for item in request.items
            ],
            "consumer": {
                "first_name": first,
                "last_name": last or first,
                "phone_number": request.customer_phone,
                "email": request.customer_email or "customer@example.com",
            },
            "shipping_amount": _amount(0, request.currency),
            "tax_amount": _amount(0, request.currency),
            "merchant_url": {
                "success": request.return_url,
                "failure": request.return_url,
                "cancel": request.return_url,
                "notification": request.webhook_url,
            },
        }
        with self._http() as http:
            body = call(lambda: http.post("/checkout", json=payload), "Tamara")
        return ProviderStatus(
            status="PENDING", provider_ref=body.get("order_id"), customer_url=body.get("checkout_url")
        )

    def fetch(self, ref: PaymentRef) -> ProviderStatus:
        with self._http() as http:
            return self._order_status(call(lambda: http.get(f"/orders/{ref.provider_ref}"), "Tamara"))

    def capture(self, ref: PaymentRef) -> ProviderStatus:
        with self._http() as http:
            order = call(lambda: http.get(f"/orders/{ref.provider_ref}"), "Tamara")
            if str(order.get("status") or "").upper() == "FULLY_CAPTURED":
                return ProviderStatus(status="PAID", provider_ref=ref.provider_ref)
            if str(order.get("status") or "").upper() == "APPROVED":
                call(lambda: http.post(f"/orders/{ref.provider_ref}/authorise"), "Tamara")
            payload = {
                "order_id": ref.provider_ref,
                "total_amount": _amount(ref.amount_cents, ref.currency),
                "shipping_info": {"shipped_at": datetime.now(UTC).isoformat(), "shipping_company": "In store"},
            }
            body = call(lambda: http.post("/payments/capture", json=payload), "Tamara")
        return ProviderStatus(status="PAID", provider_ref=ref.provider_ref, auth_code=body.get("capture_id"))

    def cancel(self, ref: PaymentRef) -> None:
        if not ref.provider_ref:
            return
        payload = {"total_amount": _amount(ref.amount_cents, ref.currency)}
        try:
            with self._http() as http:
                call(lambda: http.post(f"/orders/{ref.provider_ref}/cancel", json=payload), "Tamara")
        except ProviderError:
            return

    def refund(self, ref: PaymentRef, amount_cents: int, reason: str) -> RefundResult:
        payload = {"total_amount": _amount(amount_cents, ref.currency), "comment": reason[:120] or "Customer return"}
        try:
            with self._http() as http:
                body = call(
                    lambda: http.post(f"/payments/simplified-refund/{ref.provider_ref}", json=payload), "Tamara"
                )
        except ProviderError as exc:
            return RefundResult(ok=False, error=str(exc))
        return RefundResult(ok=True, provider_ref=body.get("refund_id") or ref.provider_ref)

    def verify_webhook(self, body: bytes, headers: dict[str, str], query: dict[str, str]) -> bool:
        token = query.get("tamaraToken") or headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not self._notification or not token:
            return False
        try:
            jwt.decode(token, self._notification, algorithms=["HS256"], options={"verify_aud": False})
        except jwt.PyJWTError:
            return False
        return True

    def parse_webhook(self, payload: dict) -> WebhookEvent:
        return WebhookEvent(
            status=self._order_status(payload),
            provider_ref=payload.get("order_id"),
            reference=payload.get("order_reference_id"),
        )

    def check(self, terminal_ref: str | None) -> str:
        with self._http() as http:
            call(lambda: http.get("/merchants/configs"), "Tamara")
        return "Connected to Tamara"
