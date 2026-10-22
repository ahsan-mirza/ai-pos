"""Which adapter serves each provider. A vendor without credentials falls back to the simulator, so settings
can name the real provider before the merchant account is live."""

from dataclasses import dataclass

from app.core.config import Settings
from app.integrations.payments.base import Channel, PaymentAdapter
from app.integrations.payments.geidea import GeideaAdapter
from app.integrations.payments.ngenius import NGeniusAdapter
from app.integrations.payments.simulator import SimulatorAdapter
from app.integrations.payments.tabby import TabbyAdapter
from app.integrations.payments.tamara import TamaraAdapter

CARD_PROVIDERS = ("simulator", "ngenius", "geidea")
BNPL_PROVIDERS = ("simulator", "tabby", "tamara")
LABELS = {
    "simulator": "Simulator",
    "ngenius": "N-Genius (Network International)",
    "geidea": "Geidea",
    "tabby": "Tabby",
    "tamara": "Tamara",
}


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    label: str
    channel: Channel
    configured: bool
    simulated: bool
    missing: tuple[str, ...]


def _simulator(settings: Settings, channel: Channel) -> SimulatorAdapter:
    base = f"{settings.public_base_url.rstrip('/')}/api/v1/integrations/payments/simulator/checkout"
    return SimulatorAdapter(channel, checkout_base=base, webhook_secret=settings.integration_webhook_secret)


def _missing(settings: Settings, provider: str) -> tuple[str, ...]:
    required = {
        "ngenius": ("ngenius_api_key", "ngenius_outlet_ref"),
        "geidea": ("geidea_public_key", "geidea_api_password"),
        "tabby": ("tabby_secret_key", "tabby_merchant_code"),
        "tamara": ("tamara_api_token",),
    }.get(provider, ())
    return tuple(key.upper() for key in required if not getattr(settings, key))


def adapter(settings: Settings, provider: str, channel: Channel) -> PaymentAdapter:
    """The adapter for `provider`; the simulator stands in while its credentials are missing."""
    timeout = float(settings.integration_timeout_seconds)
    if provider == "simulator" or _missing(settings, provider):
        return _simulator(settings, channel)
    if provider == "ngenius":
        return NGeniusAdapter(
            api_key=settings.ngenius_api_key or "",
            outlet_ref=settings.ngenius_outlet_ref or "",
            base_url=settings.ngenius_base_url,
            timeout=timeout,
            secret=settings.integration_webhook_secret,
        )
    if provider == "geidea":
        return GeideaAdapter(
            public_key=settings.geidea_public_key or "",
            api_password=settings.geidea_api_password or "",
            base_url=settings.geidea_base_url,
            timeout=timeout,
        )
    if provider == "tabby":
        return TabbyAdapter(
            secret_key=settings.tabby_secret_key or "",
            merchant_code=settings.tabby_merchant_code or "",
            base_url=settings.tabby_base_url,
            timeout=timeout,
            secret=settings.integration_webhook_secret,
        )
    if provider == "tamara":
        return TamaraAdapter(
            api_token=settings.tamara_api_token or "",
            notification_token=settings.tamara_notification_token,
            base_url=settings.tamara_base_url,
            timeout=timeout,
        )
    return _simulator(settings, channel)


def bnpl_names(settings: Settings) -> list[str]:
    names = [name.strip().lower() for name in settings.bnpl_providers.split(",") if name.strip()]
    return [name for name in dict.fromkeys(names) if name in BNPL_PROVIDERS]


def _label(name: str, channel: Channel) -> str:
    if name == "simulator":
        return "Card terminal simulator" if channel == "CARD" else "Pay-later simulator"
    return LABELS[name]


def providers(settings: Settings) -> list[ProviderInfo]:
    rows: list[ProviderInfo] = []
    card = settings.card_terminal_provider
    missing = _missing(settings, card)
    rows.append(
        ProviderInfo(card, _label(card, "CARD"), "CARD", not missing, card == "simulator" or bool(missing), missing)
    )
    for name in bnpl_names(settings):
        missing = _missing(settings, name)
        rows.append(
            ProviderInfo(name, _label(name, "BNPL"), "BNPL", not missing, name == "simulator" or bool(missing), missing)
        )
    return rows
