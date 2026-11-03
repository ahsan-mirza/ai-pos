"""Evolution API (Baileys) client. The global key never leaves the server."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from app.services.messaging_providers import ProviderError

Handler = Callable[[str, str, dict | None], dict]


class EvolutionError(ProviderError):
    """Evolution rejected the call or is not configured."""


class EvolutionClient:
    def __init__(self, base_url: str, api_key: str, handler: Handler | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.handler = handler

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
            raise EvolutionError("Evolution API could not be reached.", permanent=False) from exc
        if response.status_code >= 400:
            raise EvolutionError(
                f"Evolution {response.status_code}: {response.text[:180]}",
                permanent=response.status_code < 500,
            )
        data = response.json() if response.content else {}
        return data if isinstance(data, dict) else {"data": data}


_handler: Handler | None = None


def set_handler(handler: Handler | None) -> None:
    """Tests install a fake. Production leaves this unset."""
    global _handler
    _handler = handler


def client_for(base_url: str | None, api_key: str | None) -> EvolutionClient:
    return EvolutionClient(base_url or "", api_key or "", _handler)
