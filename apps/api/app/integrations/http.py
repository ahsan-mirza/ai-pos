"""Shared HTTP plumbing for vendor adapters: one client factory (tests swap in a MockTransport) and HMAC checks."""

import hashlib
import hmac
from collections.abc import Callable

import httpx

_transport: httpx.BaseTransport | None = None


class ProviderError(Exception):
    """The provider refused or could not be reached; the message is safe to show staff."""


def use_transport(transport: httpx.BaseTransport | None) -> None:
    """Route every adapter call through `transport` (tests); None restores real network access."""
    global _transport
    _transport = transport


def client(base_url: str, *, timeout: float, headers: dict[str, str] | None = None) -> httpx.Client:
    return httpx.Client(base_url=base_url, timeout=timeout, headers=headers or {}, transport=_transport)


def call(send: Callable[[], httpx.Response], provider: str) -> dict:
    """Run one request and return its JSON body, turning transport and HTTP failures into ProviderError."""
    try:
        response = send()
    except httpx.HTTPError as exc:
        raise ProviderError(f"{provider} could not be reached: {exc.__class__.__name__}.") from exc
    if response.status_code >= 400:
        detail = ""
        try:
            body = response.json()
            detail = str(body.get("message") or body.get("error") or body.get("errors") or "")[:160]
        except ValueError:
            detail = response.text[:160]
        raise ProviderError(f"{provider} refused ({response.status_code}){': ' + detail if detail else ''}.")
    if not response.content:
        return {}
    try:
        data = response.json()
    except ValueError as exc:
        raise ProviderError(f"{provider} sent an unreadable reply.") from exc
    return data if isinstance(data, dict) else {"items": data}


def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def signature_matches(secret: str | None, body: bytes, signature: str | None) -> bool:
    if not secret or not signature:
        return False
    return hmac.compare_digest(sign(secret, body), signature.lower().removeprefix("sha256="))
