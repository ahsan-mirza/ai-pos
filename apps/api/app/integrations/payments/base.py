"""The contract every card-terminal and BNPL provider implements. Adapters are stateless: the intent row is the
state, and each call gets what it needs in a `PaymentRef`."""

from dataclasses import dataclass, field
from typing import Literal, Protocol

Channel = Literal["CARD", "BNPL"]
ProviderState = Literal["PENDING", "AUTHORIZED", "PAID", "DECLINED", "EXPIRED", "CANCELLED"]


@dataclass(frozen=True)
class LineItem:
    name: str
    quantity: int
    unit_cents: int
    sku: str = ""


@dataclass(frozen=True)
class StartRequest:
    intent_id: str
    reference: str
    amount_cents: int
    currency: str
    terminal_ref: str | None = None
    customer_phone: str | None = None
    customer_name: str = ""
    customer_email: str = ""
    description: str = ""
    items: tuple[LineItem, ...] = ()
    # Where a BNPL checkout returns the customer; the till polls, so this is only a courtesy page.
    return_url: str = ""
    webhook_url: str = ""


@dataclass(frozen=True)
class PaymentRef:
    provider_ref: str | None
    reference: str
    amount_cents: int
    currency: str
    terminal_ref: str | None = None


@dataclass
class ProviderStatus:
    status: ProviderState
    provider_ref: str | None = None
    customer_url: str | None = None
    auth_code: str | None = None
    card_brand: str | None = None
    card_last4: str | None = None
    failure_reason: str | None = None
    amount_cents: int | None = None


@dataclass
class RefundResult:
    ok: bool
    provider_ref: str | None = None
    error: str | None = None


@dataclass
class WebhookEvent:
    status: ProviderStatus
    provider_ref: str | None = None
    reference: str | None = None
    extra: dict = field(default_factory=dict)


class PaymentAdapter(Protocol):
    name: str
    label: str
    channel: Channel
    simulated: bool

    def start(self, request: StartRequest) -> ProviderStatus:
        """Push the amount to the terminal, or open the BNPL checkout (returns its customer_url)."""
        ...

    def fetch(self, ref: PaymentRef) -> ProviderStatus:
        """The provider's current view of the payment, for polling."""
        ...

    def capture(self, ref: PaymentRef) -> ProviderStatus:
        """Settle an AUTHORIZED payment (BNPL). Card terminals capture on approval and return PAID unchanged."""
        ...

    def cancel(self, ref: PaymentRef) -> None: ...

    def refund(self, ref: PaymentRef, amount_cents: int, reason: str) -> RefundResult: ...

    def verify_webhook(self, body: bytes, headers: dict[str, str], query: dict[str, str]) -> bool: ...

    def parse_webhook(self, payload: dict) -> WebhookEvent: ...

    def check(self, terminal_ref: str | None) -> str:
        """Test the connection (and terminal, if given); returns a short status line or raises ProviderError."""
        ...


def money(cents: int) -> str:
    return f"{cents / 100:.2f}"


def cents(value: object) -> int | None:
    try:
        return round(float(str(value)) * 100)
    except (TypeError, ValueError):
        return None
