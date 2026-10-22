"""Geidea card terminals through the Geidea cloud POS API (HTTP Basic: merchant public key and API password).

Paths follow Geidea's terminal-integration guide; confirm them and the callback signature with Geidea at
merchant onboarding. Callbacks are signed with HMAC-SHA256 of the body using the API password."""

import base64

from app.integrations.http import ProviderError, call, client, signature_matches
from app.integrations.payments.base import (
    PaymentRef,
    ProviderState,
    ProviderStatus,
    RefundResult,
    StartRequest,
    WebhookEvent,
    cents,
    money,
)

STATES: dict[str, ProviderState] = {
    "INITIATED": "PENDING",
    "PENDING": "PENDING",
    "INPROGRESS": "PENDING",
    "SUCCESS": "PAID",
    "APPROVED": "PAID",
    "PAID": "PAID",
    "FAILED": "DECLINED",
    "DECLINED": "DECLINED",
    "TIMEOUT": "EXPIRED",
    "EXPIRED": "EXPIRED",
    "CANCELLED": "CANCELLED",
    "VOIDED": "CANCELLED",
}


class GeideaAdapter:
    name = "geidea"
    label = "Geidea card terminal"
    channel = "CARD"
    simulated = False

    def __init__(self, *, public_key: str, api_password: str, base_url: str, timeout: float) -> None:
        token = base64.b64encode(f"{public_key}:{api_password}".encode()).decode()
        self._headers = {"Authorization": f"Basic {token}", "Accept": "application/json"}
        self._password = api_password
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def _http(self):
        return client(self._base, timeout=self._timeout, headers=self._headers)

    @staticmethod
    def _status(body: dict) -> ProviderStatus:
        order = body.get("order") or body.get("transaction") or body
        state = STATES.get(str(order.get("status") or "").upper().replace(" ", ""), "PENDING")
        card = order.get("paymentMethod") or {}
        masked = str(card.get("maskedCardNumber") or "")
        return ProviderStatus(
            status=state,
            provider_ref=order.get("orderId") or order.get("transactionId"),
            auth_code=order.get("authorizationCode"),
            card_brand=card.get("brand"),
            card_last4=masked[-4:] if len(masked) >= 4 else None,
            failure_reason=(order.get("detailedResponseMessage") or body.get("responseMessage"))
            if state == "DECLINED"
            else None,
            amount_cents=cents(order.get("amount")) if order.get("amount") is not None else None,
        )

    def start(self, request: StartRequest) -> ProviderStatus:
        if not request.terminal_ref:
            raise ProviderError("Choose the card terminal for this till.")
        payload = {
            "terminalId": request.terminal_ref,
            "amount": money(request.amount_cents),
            "currency": request.currency,
            "merchantReferenceId": request.reference,
            "callbackUrl": request.webhook_url,
        }
        with self._http() as http:
            return self._status(call(lambda: http.post("/pos/api/v1/terminal/sale", json=payload), "Geidea"))

    def fetch(self, ref: PaymentRef) -> ProviderStatus:
        with self._http() as http:
            return self._status(call(lambda: http.get(f"/pos/api/v1/transactions/{ref.provider_ref}"), "Geidea"))

    def capture(self, ref: PaymentRef) -> ProviderStatus:
        return ProviderStatus(status="PAID", provider_ref=ref.provider_ref)

    def cancel(self, ref: PaymentRef) -> None:
        if not ref.provider_ref:
            return
        with self._http() as http:
            call(lambda: http.post(f"/pos/api/v1/transactions/{ref.provider_ref}/cancel"), "Geidea")

    def refund(self, ref: PaymentRef, amount_cents: int, reason: str) -> RefundResult:
        payload = {"orderId": ref.provider_ref, "refundAmount": money(amount_cents), "currency": ref.currency}
        try:
            with self._http() as http:
                body = call(lambda: http.post("/pgw/api/v1/direct/refund", json=payload), "Geidea")
        except ProviderError as exc:
            return RefundResult(ok=False, error=str(exc))
        code = str(body.get("responseCode") or "000")
        if code != "000":
            return RefundResult(ok=False, error=str(body.get("responseMessage") or f"Geidea code {code}")[:200])
        return RefundResult(ok=True, provider_ref=(body.get("order") or {}).get("orderId") or ref.provider_ref)

    def verify_webhook(self, body: bytes, headers: dict[str, str], query: dict[str, str]) -> bool:
        return signature_matches(self._password, body, headers.get("x-signature") or headers.get("signature"))

    def parse_webhook(self, payload: dict) -> WebhookEvent:
        status = self._status(payload)
        order = payload.get("order") or payload
        return WebhookEvent(status=status, provider_ref=status.provider_ref, reference=order.get("merchantReferenceId"))

    def check(self, terminal_ref: str | None) -> str:
        with self._http() as http:
            if terminal_ref:
                body = call(lambda: http.get(f"/pos/api/v1/terminals/{terminal_ref}"), "Geidea")
                return f"Connected; terminal {terminal_ref} is {str(body.get('status') or 'reachable').lower()}"
            call(lambda: http.get("/pgw/api/v1/config"), "Geidea")
        return "Connected to Geidea"
