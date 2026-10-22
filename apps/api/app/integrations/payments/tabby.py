"""Tabby pay-in-4 at the till. The register opens a checkout session for the customer's phone; the customer
completes it on Tabby's page (QR on the customer display, or Tabby's SMS). An AUTHORIZED payment is captured
straight away, since the goods leave the store with the customer.

API: https://api.tabby.ai (Bearer secret key). Sessions POST /api/v2/checkout; payments GET /api/v2/payments/{id},
captures and refunds under it. Webhooks are registered with a custom header the merchant chooses; we expect
`X-Signature` to equal HMAC-SHA256(body, INTEGRATION_WEBHOOK_SECRET) and always re-fetch the payment anyway."""

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
    "CREATED": "PENDING",
    "AUTHORIZED": "AUTHORIZED",
    "CLOSED": "PAID",
    "REJECTED": "DECLINED",
    "EXPIRED": "EXPIRED",
}


class TabbyAdapter:
    name = "tabby"
    label = "Tabby"
    channel = "BNPL"
    simulated = False

    def __init__(self, *, secret_key: str, merchant_code: str, base_url: str, timeout: float, secret: str | None):
        self._headers = {"Authorization": f"Bearer {secret_key}", "Accept": "application/json"}
        self._merchant = merchant_code
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._secret = secret

    def _http(self):
        return client(self._base, timeout=self._timeout, headers=self._headers)

    @staticmethod
    def _payment_status(payment: dict) -> ProviderStatus:
        state = STATES.get(str(payment.get("status") or "").upper(), "PENDING")
        captured = sum(cents(c.get("amount")) or 0 for c in payment.get("captures") or [])
        if state == "AUTHORIZED" and captured and captured >= (cents(payment.get("amount")) or 0):
            state = "PAID"
        return ProviderStatus(
            status=state,
            provider_ref=payment.get("id"),
            amount_cents=cents(payment.get("amount")),
            failure_reason="Tabby declined the customer." if state == "DECLINED" else None,
        )

    def start(self, request: StartRequest) -> ProviderStatus:
        if not request.customer_phone:
            raise ProviderError("Tabby needs the customer's mobile number.")
        payload = {
            "payment": {
                "amount": money(request.amount_cents),
                "currency": request.currency,
                "description": request.description or f"In-store purchase {request.reference}",
                "buyer": {
                    "phone": request.customer_phone,
                    "email": request.customer_email or None,
                    "name": request.customer_name or None,
                },
                "order": {
                    "reference_id": request.reference,
                    "items": [
                        {
                            "title": item.name[:120],
                            "quantity": item.quantity,
                            "unit_price": money(item.unit_cents),
                            "reference_id": item.sku or None,
                            "category": "Electronics",
                        }
                        for item in request.items
                    ],
                },
            },
            "lang": "en",
            "merchant_code": self._merchant,
            "merchant_urls": {
                "success": request.return_url,
                "cancel": request.return_url,
                "failure": request.return_url,
            },
        }
        with self._http() as http:
            body = call(lambda: http.post("/api/v2/checkout", json=payload), "Tabby")
        if str(body.get("status") or "").lower() == "rejected":
            reason = (
                (body.get("configuration") or {}).get("products", {}).get("installments", {}).get("rejection_reason")
            )
            return ProviderStatus(status="DECLINED", failure_reason=f"Tabby declined: {reason or 'not eligible'}.")
        installments = ((body.get("configuration") or {}).get("available_products") or {}).get("installments") or []
        url = installments[0].get("web_url") if installments else None
        payment = body.get("payment") or {}
        return ProviderStatus(status="PENDING", provider_ref=payment.get("id"), customer_url=url)

    def fetch(self, ref: PaymentRef) -> ProviderStatus:
        with self._http() as http:
            return self._payment_status(call(lambda: http.get(f"/api/v2/payments/{ref.provider_ref}"), "Tabby"))

    def capture(self, ref: PaymentRef) -> ProviderStatus:
        payload = {"amount": money(ref.amount_cents), "reference_id": ref.reference}
        with self._http() as http:
            body = call(lambda: http.post(f"/api/v2/payments/{ref.provider_ref}/captures", json=payload), "Tabby")
        status = self._payment_status(body)
        if status.status == "AUTHORIZED":
            status.status = "PAID"
        return status

    def cancel(self, ref: PaymentRef) -> None:
        if not ref.provider_ref:
            return
        try:
            with self._http() as http:
                call(lambda: http.post(f"/api/v2/payments/{ref.provider_ref}/close"), "Tabby")
        except ProviderError:
            # A session the customer never opened has nothing to close.
            return

    def refund(self, ref: PaymentRef, amount_cents: int, reason: str) -> RefundResult:
        payload = {"amount": money(amount_cents), "reason": reason[:120] or "Customer return"}
        try:
            with self._http() as http:
                body = call(lambda: http.post(f"/api/v2/payments/{ref.provider_ref}/refunds", json=payload), "Tabby")
        except ProviderError as exc:
            return RefundResult(ok=False, error=str(exc))
        refunds = body.get("refunds") or []
        return RefundResult(ok=True, provider_ref=refunds[-1].get("id") if refunds else ref.provider_ref)

    def verify_webhook(self, body: bytes, headers: dict[str, str], query: dict[str, str]) -> bool:
        return signature_matches(self._secret, body, headers.get("x-signature"))

    def parse_webhook(self, payload: dict) -> WebhookEvent:
        status = self._payment_status(payload)
        return WebhookEvent(
            status=status, provider_ref=payload.get("id"), reference=(payload.get("order") or {}).get("reference_id")
        )

    def check(self, terminal_ref: str | None) -> str:
        with self._http() as http:
            call(lambda: http.get("/api/v1/payments", params={"limit": 1}), "Tabby")
        return "Connected to Tabby"
