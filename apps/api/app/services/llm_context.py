"""TOON for text a model reads. API bodies, webhooks, and stored JSON stay on the json module.

Counts use the o200k_base tokenizer. The store's Ollama model is not loaded here, so these counts
are a measurement of the prompt text, not that model's own tokenizer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import tiktoken
import toon_format

_RESTRICTED = frozenset(
    {
        "purchase_cost",
        "default_cost_cents",
        "last_purchase_cost_cents",
        "cost_cents",
        "margin",
        "revenue",
        "salary",
        "payroll",
        "supplier_price",
        "bank_balance",
    }
)
_ENCODER = tiktoken.get_encoding("o200k_base")


@dataclass(frozen=True)
class ContextDocument:
    text: str
    format: str
    json_text: str
    toon_text: str | None
    valid: bool
    fallback: bool
    json_tokens: int | None
    toon_tokens: int | None

    def public(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "json_chars": len(self.json_text),
            "toon_chars": 0 if self.toon_text is None else len(self.toon_text),
            "json_tokens": self.json_tokens,
            "toon_tokens": self.toon_tokens,
            "fallback": self.fallback,
            "valid": self.valid,
        }


def encode_llm_context_to_toon(data: Any) -> str:
    return toon_format.dumps(_plain(customer_safe(data)), default=str)


def decode_toon_context(text: str) -> Any:
    return toon_format.loads(text)


def validate_toon_document(text: str) -> bool:
    if not text.strip():
        return False
    try:
        toon_format.loads(text)
    except (toon_format.ToonDecodeError, ValueError):
        return False
    return True


def estimate_context_tokens(text: str) -> int:
    return len(_ENCODER.encode(text))


def get_context_serialization_format(data: Any) -> str:
    return prepare_llm_context(data).format


def prepare_llm_context(data: Any) -> ContextDocument:
    """Use TOON when it is valid and smaller. Otherwise keep compact JSON."""
    plain = _plain(customer_safe(data))
    json_text = json.dumps(plain, ensure_ascii=False, separators=(",", ":"), default=str)
    json_tokens = estimate_context_tokens(json_text)
    try:
        toon_text = toon_format.dumps(plain, default=str)
    except (TypeError, ValueError):
        return ContextDocument(json_text, "json", json_text, None, False, True, json_tokens, None)
    valid = validate_toon_document(toon_text)
    if not valid or decode_toon_context(toon_text) != plain:
        return ContextDocument(json_text, "json", json_text, toon_text, valid, True, json_tokens, None)
    toon_tokens = estimate_context_tokens(toon_text)
    if toon_tokens >= json_tokens:
        return ContextDocument(json_text, "json", json_text, toon_text, True, True, json_tokens, toon_tokens)
    return ContextDocument(toon_text, "toon", json_text, toon_text, True, False, json_tokens, toon_tokens)


def customer_safe(value: Any) -> Any:
    """Drop restricted keys. Values that remain are unchanged."""
    if isinstance(value, dict):
        return {str(key): customer_safe(item) for key, item in value.items() if str(key) not in _RESTRICTED}
    if isinstance(value, (list, tuple)):
        return [customer_safe(item) for item in value]
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
