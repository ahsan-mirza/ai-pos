"""Simulated card terminal and BNPL provider. The intent row holds the state; staff approve or decline from the
till (or the customer from the simulated checkout page), so demos and practice mode run end to end."""

import secrets

from app.integrations.http import signature_matches
from app.integrations.payments.base import (
    Channel,
    PaymentRef,
    ProviderStatus,
    RefundResult,
    StartRequest,
    WebhookEvent,
)

# Refunds of this exact amount fail, so the retry path can be exercised in a demo.
FAILING_REFUND_CENTS = 13_13


class SimulatorAdapter:
    simulated = True

    def __init__(self, channel: Channel, *, checkout_base: str, webhook_secret: str | None) -> None:
        self.channel = channel
        self.name = "simulator"
        self.label = "Simulated card terminal" if channel == "CARD" else "Simulated pay later"
        self._checkout_base = checkout_base
        self._secret = webhook_secret

    def start(self, request: StartRequest) -> ProviderStatus:
        ref = f"sim-{secrets.token_hex(6)}"
        url = f"{self._checkout_base}/{request.intent_id}" if self.channel == "BNPL" else None
        return ProviderStatus(status="PENDING", provider_ref=ref, customer_url=url)

    def fetch(self, ref: PaymentRef) -> ProviderStatus:
        return ProviderStatus(status="PENDING", provider_ref=ref.provider_ref)

    def capture(self, ref: PaymentRef) -> ProviderStatus:
        return ProviderStatus(status="PAID", provider_ref=ref.provider_ref, amount_cents=ref.amount_cents)

    def cancel(self, ref: PaymentRef) -> None:
        return None

    def refund(self, ref: PaymentRef, amount_cents: int, reason: str) -> RefundResult:
        if amount_cents == FAILING_REFUND_CENTS:
            return RefundResult(ok=False, error="Simulated refund failure; retry succeeds once the amount changes.")
        return RefundResult(ok=True, provider_ref=f"simrf-{secrets.token_hex(5)}")

    def verify_webhook(self, body: bytes, headers: dict[str, str], query: dict[str, str]) -> bool:
        return signature_matches(self._secret, body, headers.get("x-signature"))

    def parse_webhook(self, payload: dict) -> WebhookEvent:
        status = str(payload.get("status", "")).upper()
        state = status if status in ("PAID", "AUTHORIZED", "DECLINED", "EXPIRED", "CANCELLED") else "PENDING"
        return WebhookEvent(
            status=ProviderStatus(status=state, auth_code=payload.get("auth_code")),  # type: ignore[arg-type]
            provider_ref=payload.get("provider_ref"),
            reference=payload.get("reference"),
        )

    def check(self, terminal_ref: str | None) -> str:
        return "Simulator ready" + (f" for terminal {terminal_ref}" if terminal_ref else "")

    @staticmethod
    def approval(channel: Channel) -> ProviderStatus:
        if channel == "BNPL":
            return ProviderStatus(status="AUTHORIZED")
        return ProviderStatus(
            status="PAID",
            auth_code=f"{secrets.randbelow(10**6):06d}",
            card_brand="VISA",
            card_last4=f"{secrets.randbelow(10**4):04d}",
        )
