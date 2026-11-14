"""Evolution API (Baileys) client. The global key never leaves the server."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from app.services.messaging_providers import ProviderError

Handler = Callable[[str, str, dict | None], dict]


class EvolutionError(ProviderError):
    """Evolution rejected the call or is not configured."""

    def __init__(self, message: str, *, permanent: bool = False, code: str = "unreachable", ambiguous: bool = False) -> None:
        super().__init__(message, permanent=permanent, ambiguous=ambiguous)
        self.code = code


class EvolutionClient:
    def __init__(self, base_url: str, api_key: str, handler: Handler | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.handler = handler

    def health(self) -> None:
        """Confirms the server can authenticate. This does not create a store instance."""
        if self.handler is None and (not self.base_url or not self.api_key):
            raise EvolutionError("Evolution API is not configured on the server.", permanent=True, code="not_configured")
        self._call("GET", "/instance/fetchInstances", None, timeout=5)

    def create_instance(self, name: str) -> dict:
        return self._call("POST", "/instance/create", {"instanceName": name, "integration": "WHATSAPP-BAILEYS", "qrcode": True})

    def connect(self, name: str) -> dict:
        return self._call("GET", f"/instance/connect/{name}", None)

    def status(self, name: str) -> dict:
        return self._call("GET", f"/instance/connectionState/{name}", None)

    def logout(self, name: str) -> dict:
        return self._call("DELETE", f"/instance/logout/{name}", None)

    def set_webhook(self, name: str, url: str, secret: str) -> dict:
        """Registers delivery and connection callbacks. The secret is the webhook header, not the global key."""
        return self._call(
            "POST",
            f"/webhook/set/{name}",
            {
                "webhook": {
                    "enabled": True,
                    "url": url,
                    "headers": {"apikey": secret},
                    "byEvents": False,
                    "base64": False,
                    "events": ["CONNECTION_UPDATE", "MESSAGES_UPDATE", "MESSAGES_UPSERT", "SEND_MESSAGE"],
                }
            },
        )

    def send_text(self, name: str, number: str, text: str) -> str:
        payload = self._call("POST", f"/message/sendText/{name}", {"number": number, "text": text})
        key = payload.get("key") if isinstance(payload.get("key"), dict) else {}
        message_id = str(key.get("id") or payload.get("messageId") or payload.get("id") or "")
        if not message_id:
            raise EvolutionError("Evolution accepted no message id.", permanent=False)
        return message_id

    def send_media(
        self,
        name: str,
        number: str,
        *,
        mediatype: str,
        mimetype: str,
        caption: str,
        media_b64: str,
        file_name: str,
    ) -> str:
        """Evolution v2 sendMedia. mediatype is image, video, or document."""
        payload = self._call(
            "POST",
            f"/message/sendMedia/{name}",
            {
                "number": number,
                "mediatype": mediatype,
                "mimetype": mimetype,
                "caption": caption,
                "media": media_b64,
                "fileName": file_name,
            },
            timeout=60,
        )
        key = payload.get("key") if isinstance(payload.get("key"), dict) else {}
        message_id = str(key.get("id") or payload.get("messageId") or payload.get("id") or "")
        if not message_id:
            raise EvolutionError("Evolution accepted no message id.", permanent=False)
        return message_id

    def _call(self, method: str, path: str, body: dict | None, timeout: int = 20) -> dict[str, Any]:
        if self.handler is not None:
            return self.handler(method, path, body)
        if not self.base_url or not self.api_key:
            raise EvolutionError("Evolution API is not configured on the server.", permanent=True)
        try:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                headers={"apikey": self.api_key},
                json=body,
                timeout=timeout,
            )
        except httpx.HTTPError as exc:
            timed_out = isinstance(exc, httpx.TimeoutException)
            raise EvolutionError(
                "Evolution API could not be reached.",
                permanent=False,
                code="timeout" if timed_out else "unreachable",
                ambiguous=timed_out,
            ) from exc
        if response.status_code in {401, 403}:
            raise EvolutionError("Evolution API rejected the server key.", permanent=True, code="authentication_error")
        if response.status_code >= 400:
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            raise EvolutionError(
                evolution_failure_message(response.status_code, payload),
                permanent=response.status_code < 500,
                code="unreachable",
            )
        data = response.json() if response.content else {}
        return data if isinstance(data, dict) else {"data": data}


def evolution_failure_message(status: int, payload: object) -> str:
    """A store-facing reason. The HTTP status and the server key stay out of this text."""
    text = _message_text(payload).lower()
    if _number_missing(payload) or any(
        phrase in text
        for phrase in ("not registered", "not on whatsapp", "number does not exist", "number not exist", "not exists")
    ):
        return "That number is not on WhatsApp. Check the country code and try again."
    if any(phrase in text for phrase in ("connection closed", "not connected", "session is closed")):
        return "WhatsApp is not connected. Scan the QR code, then try again."
    if status == 404 or "instance not found" in text:
        return "This store's WhatsApp connection was not found. Connect the number again."
    if "invalid" in text and "number" in text:
        return "Enter the full WhatsApp number with its country code, for example +923104433311."
    if status == 429:
        return "WhatsApp is busy. Wait a moment and try again."
    if status >= 500:
        return "WhatsApp could not send the message. Try again in a moment."
    return "WhatsApp could not send to that number. Check the number and try again."


def _number_missing(payload: object) -> bool:
    if isinstance(payload, dict):
        if payload.get("exists") is False:
            return True
        return any(_number_missing(value) for value in payload.values())
    if isinstance(payload, list):
        return any(_number_missing(item) for item in payload)
    return False


def _message_text(payload: object) -> str:
    if isinstance(payload, dict):
        source = payload.get("response") if isinstance(payload.get("response"), dict) else payload
        raw = source.get("message") if isinstance(source, dict) else None
        if isinstance(raw, list):
            parts: list[str] = []
            for item in raw[:3]:
                if isinstance(item, dict):
                    parts.append(str(item.get("message") or ""))
                else:
                    parts.append(str(item))
            return " ".join(parts)
        if raw is not None:
            return str(raw)
    return ""


_handler: Handler | None = None


def set_handler(handler: Handler | None) -> None:
    """Tests install a fake. Production leaves this unset."""
    global _handler
    _handler = handler


def client_for(base_url: str | None, api_key: str | None) -> EvolutionClient:
    return EvolutionClient(base_url or "", api_key or "", _handler)
