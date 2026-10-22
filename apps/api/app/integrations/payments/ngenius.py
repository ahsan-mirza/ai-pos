"""Network International N-Genius card terminals through its cloud terminal API.

Auth is the N-Genius identity flow (API key -> short-lived bearer token). The terminal paths below follow the
cloud-terminal integration guide; confirm them, and the webhook signing, with Network International at
merchant onboarding, since terminal APIs are enabled per outlet."""

import time

from app.integrations.http import ProviderError, call, client, signature_matches
from app.integrations.payments.base import (
    PaymentRef,
    ProviderState,
    ProviderStatus,
    RefundResult,
    StartRequest,
    WebhookEvent,
)

STATES: dict[str, ProviderState] = {
    "PENDING": "PENDING",
    "STARTED": "PENDING",
    "AWAITING_CARD": "PENDING",
    "AUTHORISED": "PAID",
    "CAPTURED": "PAID",
    "PURCHASED": "PAID",
    "SUCCESS": "PAID",
    "DECLINED": "DECLINED",
    "FAILED": "DECLINED",
    "TIMEOUT": "EXPIRED",
    "CANCELLED": "CANCELLED",
    "REVERSED": "CANCELLED",
}


class NGeniusAdapter:
    name = "ngenius"
    label = "N-Genius card terminal"
    channel = "CARD"
    simulated = False

    def __init__(self, *, api_key: str, outlet_ref: str, base_url: str, timeout: float, secret: str | None) -> None:
        self._api_key = api_key
        self._outlet = outlet_ref
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._secret = secret
        self._token: tuple[str, float] | None = None

    def _bearer(self) -> str:
        if self._token and self._token[1] > time.monotonic() + 30:
            return self._token[0]
        with client(self._base, timeout=self._timeout) as http:
            body = call(
                lambda: http.post(
                    "/identity/auth/access-token",
                    headers={
                        "Authorization": f"Basic {self._api_key}",
                        "Content-Type": "application/vnd.ni-identity.v1+json",
                    },
                ),
                "N-Genius",
            )
        token = body.get("access_token")
        if not token:
            raise ProviderError("N-Genius did not issue an access token; check NGENIUS_API_KEY.")
        self._token = (str(token), time.monotonic() + float(body.get("expires_in") or 300))
        return self._token[0]

    def _http(self):
        return client(
            self._base,
            timeout=self._timeout,
            headers={"Authorization": f"Bearer {self._bearer()}", "Accept": "application/json"},
        )

    def _terminal(self, terminal_ref: str | None) -> str:
        if not terminal_ref:
            raise ProviderError("Choose the card terminal for this till.")
        return f"/transactions/outlets/{self._outlet}/terminals/{terminal_ref}"

    @staticmethod
    def _status(body: dict) -> ProviderStatus:
        state = STATES.get(str(body.get("state") or body.get("status") or "").upper(), "PENDING")
        card = body.get("paymentMethod") or {}
        pan = str(card.get("pan") or "")
        return ProviderStatus(
            status=state,
            provider_ref=body.get("reference") or body.get("transactionId"),
            auth_code=body.get("authCode") or body.get("authorizationCode"),
            card_brand=card.get("name") or card.get("brand"),
            card_last4=pan[-4:] if len(pan) >= 4 else None,
            failure_reason=body.get("message") if state == "DECLINED" else None,
            amount_cents=(body.get("amount") or {}).get("value"),
        )

    def start(self, request: StartRequest) -> ProviderStatus:
        path = f"{self._terminal(request.terminal_ref)}/sales"
        payload = {
            "action": "SALE",
            "amount": {"currencyCode": request.currency, "value": request.amount_cents},
            "merchantOrderReference": request.reference,
            "callbackUrl": request.webhook_url,
        }
        with self._http() as http:
            return self._status(call(lambda: http.post(path, json=payload), "N-Genius"))

    def fetch(self, ref: PaymentRef) -> ProviderStatus:
        path = f"{self._terminal(ref.terminal_ref)}/sales/{ref.provider_ref}"
        with self._http() as http:
            return self._status(call(lambda: http.get(path), "N-Genius"))

    def capture(self, ref: PaymentRef) -> ProviderStatus:
        return ProviderStatus(status="PAID", provider_ref=ref.provider_ref)

    def cancel(self, ref: PaymentRef) -> None:
        if not ref.provider_ref:
            return
        path = f"{self._terminal(ref.terminal_ref)}/sales/{ref.provider_ref}/cancel"
        with self._http() as http:
            call(lambda: http.put(path), "N-Genius")

    def refund(self, ref: PaymentRef, amount_cents: int, reason: str) -> RefundResult:
        path = f"/transactions/outlets/{self._outlet}/payments/{ref.provider_ref}/refund"
        payload = {"amount": {"currencyCode": ref.currency, "value": amount_cents}, "reason": reason[:120]}
        try:
            with self._http() as http:
                body = call(lambda: http.post(path, json=payload), "N-Genius")
        except ProviderError as exc:
            return RefundResult(ok=False, error=str(exc))
        return RefundResult(ok=True, provider_ref=body.get("reference") or body.get("refundId"))

    def verify_webhook(self, body: bytes, headers: dict[str, str], query: dict[str, str]) -> bool:
        return signature_matches(self._secret, body, headers.get("x-signature"))

    def parse_webhook(self, payload: dict) -> WebhookEvent:
        status = self._status(payload)
        return WebhookEvent(
            status=status, provider_ref=status.provider_ref, reference=payload.get("merchantOrderReference")
        )

    def check(self, terminal_ref: str | None) -> str:
        self._bearer()
        if terminal_ref:
            with self._http() as http:
                body = call(lambda: http.get(self._terminal(terminal_ref)), "N-Genius")
            return f"Connected; terminal {terminal_ref} is {str(body.get('status') or 'reachable').lower()}"
        return "Connected to N-Genius"
