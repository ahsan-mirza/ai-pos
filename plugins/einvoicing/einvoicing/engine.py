"""Classification, immutable snapshots, and the mock ASP. VAT figures are copied, not recomputed."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

PROFILE_VERSION = "pint-ae-billing-1@ae-1"
TRN_RE = re.compile(r"^\d{15}$")
MAX_ATTEMPTS = 5

TRANSITIONS: dict[str, set[str]] = {
    "CREATED": {"VALIDATION_PENDING", "VALIDATION_FAILED"},
    "VALIDATION_PENDING": {"VALIDATION_FAILED", "QUEUED"},
    "VALIDATION_FAILED": set(),
    "QUEUED": {"SUBMISSION_IN_PROGRESS"},
    "SUBMISSION_IN_PROGRESS": {"SUBMITTED", "RETRY_PENDING", "PROCESSING_ERROR"},
    "SUBMITTED": {"ACCEPTED", "REJECTED"},
    "ACCEPTED": set(),
    "REJECTED": {"RETRY_PENDING"},
    "RETRY_PENDING": {"SUBMISSION_IN_PROGRESS", "PROCESSING_ERROR"},
    "PROCESSING_ERROR": {"RETRY_PENDING"},
}


class TransitionError(Exception):
    pass


def transition(current: str, target: str) -> str:
    allowed = TRANSITIONS.get(current)
    if allowed is None or target not in allowed:
        raise TransitionError(f"{current} cannot move to {target}")
    return target


def classify(buyer_trn: str | None, customer_id: uuid.UUID | None, government_ids: list[str]) -> str:
    """B2C is outside the mandatory scope in MD 244 of 2025 until a later ministerial decision."""
    if customer_id is not None and str(customer_id) in set(government_ids):
        return "B2G"
    if (buyer_trn or "").strip():
        return "B2B"
    return "B2C"


def trn_error(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return "Buyer TRN is required for an in-scope tax invoice."
    if not TRN_RE.fullmatch(text):
        return "Buyer TRN must be the 15-digit FTA number."
    return None


def money(cents: int) -> str:
    """Two decimal places from integer fils/cents already stored on the sale. No second rounding."""
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(int(cents)), 100)
    return f"{sign}{whole}.{frac:02d}"


def payload_hash(document: dict) -> str:
    raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class SourceLine:
    description: str
    quantity: int
    net_cents: int
    tax_cents: int
    tax_rate_bps: int


@dataclass(frozen=True)
class SourceDocument:
    tenant_id: uuid.UUID
    sale_id: uuid.UUID
    store_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    number: str
    currency: str
    issue_date: str
    seller_name: str
    seller_trn: str | None
    buyer_name: str
    buyer_trn: str | None
    kind: str
    net_cents: int
    tax_cents: int
    total_cents: int
    lines: tuple[SourceLine, ...]


def canonical(source: SourceDocument) -> dict:
    return {
        "profile": PROFILE_VERSION,
        "document_type": "380" if source.kind != "credit_note" else "381",
        "number": source.number,
        "issue_date": source.issue_date,
        "currency": source.currency,
        "transaction": source.kind,
        "seller": {"name": source.seller_name, "trn": source.seller_trn or ""},
        "buyer": {"name": source.buyer_name, "trn": source.buyer_trn or ""},
        "lines": [
            {
                "description": line.description,
                "quantity": line.quantity,
                "net": money(line.net_cents),
                "tax": money(line.tax_cents),
                "rate_bps": line.tax_rate_bps,
            }
            for line in source.lines
        ],
        "net": money(source.net_cents),
        "tax": money(source.tax_cents),
        "total": money(source.total_cents),
        "source_sale_id": str(source.sale_id),
    }


def validate_snapshot(source: SourceDocument) -> str | None:
    if source.kind not in {"B2B", "B2G"}:
        return "This transaction is outside the e-invoice scope."
    if not source.seller_name.strip():
        return "Seller legal name is missing."
    seller = trn_error(source.seller_trn)
    if seller:
        return seller.replace("Buyer", "Seller")
    if not source.buyer_name.strip():
        return "Buyer name is missing."
    buyer = trn_error(source.buyer_trn)
    if buyer:
        return buyer
    line_net = sum(line.net_cents for line in source.lines)
    line_tax = sum(line.tax_cents for line in source.lines)
    if line_net != source.net_cents or line_tax != source.tax_cents:
        return "Line amounts do not match the posted sale totals."
    if source.net_cents + source.tax_cents != source.total_cents:
        return "Posted net and VAT do not add up to the posted total."
    return None


@dataclass(frozen=True)
class ProviderResult:
    outcome: str
    provider_status: str
    reference: str
    detail: str


class MockAsp:
    """Test double. The name `mock` is reserved so it cannot be described as an accredited provider."""

    code = "mock"

    def test_connection(self) -> ProviderResult:
        return ProviderResult("ok", "MOCK_CONNECTED", "", "Mock sandbox responded. This is not an accredited ASP.")

    def submit(self, document: dict) -> ProviderResult:
        buyer = str(document.get("buyer", {}).get("name", ""))
        if buyer == "TIMEOUT":
            return ProviderResult("timeout", "MOCK_TIMEOUT", "", "Mock provider timed out.")
        if buyer == "RATELIMIT":
            return ProviderResult("rate_limited", "MOCK_RATE_LIMIT", "", "Mock provider asked for a retry.")
        if buyer == "REJECT":
            return ProviderResult("rejected", "MOCK_REJECTED", "", "Mock provider rejected the document.")
        reference = "mock-" + payload_hash(document)[:16]
        return ProviderResult("accepted", "MOCK_ACCEPTED", reference, "Mock provider accepted the document.")


def provider_for(code: str) -> MockAsp:
    if code != MockAsp.code:
        raise KeyError(code)
    return MockAsp()


def sign_body(secret: str, body: bytes, timestamp: str) -> str:
    return hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def webhook_fresh(timestamp: str, *, now: datetime | None = None, window_seconds: int = 300) -> bool:
    try:
        sent = datetime.fromisoformat(timestamp)
    except ValueError:
        return False
    if sent.tzinfo is None:
        sent = sent.replace(tzinfo=UTC)
    current = now or datetime.now(UTC)
    return abs((current - sent).total_seconds()) <= window_seconds
