"""Provider-independent card terminal boundary.

No adapter here talks to a bank. A missing acquirer refuses the charge.
The test adapter is only for automated tests and labels every result as a test.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TerminalCharge:
    status: str
    provider_reference: str
    test_adapter: bool
    detail: str


class TerminalAdapter(Protocol):
    code: str
    is_test: bool

    def initiate(self, *, amount_cents: int, currency: str, reference: str, idempotency_key: str) -> TerminalCharge: ...

    def status(self, reference: str) -> TerminalCharge: ...

    def cancel(self, reference: str) -> TerminalCharge: ...


class UnconfiguredTerminal:
    """No acquirer is selected. This never returns an approval."""

    code = ""
    is_test = False

    def initiate(self, *, amount_cents: int, currency: str, reference: str, idempotency_key: str) -> TerminalCharge:
        del amount_cents, currency, reference, idempotency_key
        raise TerminalNotConfigured("No payment terminal provider is configured. The card was not charged.")

    def status(self, reference: str) -> TerminalCharge:
        return TerminalCharge("UNKNOWN", reference, False, "The provider result is not available.")

    def cancel(self, reference: str) -> TerminalCharge:
        return TerminalCharge("CANCELLED", reference, False, "Nothing was sent to a terminal.")


class TerminalTestDouble:
    """Explicit test double. Callers must keep test_adapter visible and must not treat it as a live acquirer."""

    code = "test"
    is_test = True

    def __init__(self, outcome: str = "APPROVED") -> None:
        self.outcome = outcome

    def initiate(self, *, amount_cents: int, currency: str, reference: str, idempotency_key: str) -> TerminalCharge:
        del amount_cents, currency, idempotency_key
        return TerminalCharge(self.outcome, f"test-{reference}", True, "Test adapter. No card was charged.")

    def status(self, reference: str) -> TerminalCharge:
        return TerminalCharge(self.outcome, reference, True, "Test adapter. No card was charged.")

    def cancel(self, reference: str) -> TerminalCharge:
        return TerminalCharge("CANCELLED", reference, True, "Test adapter. No card was charged.")


class TerminalNotConfigured(Exception):
    pass


def live_adapter(provider: str, credentials_present: bool) -> TerminalAdapter:
    """A named acquirer with credentials still has no validated device protocol, so the charge is refused.

    The simulator and a provider with missing credentials take the same path.
    """
    del provider, credentials_present
    return UnconfiguredTerminal()
