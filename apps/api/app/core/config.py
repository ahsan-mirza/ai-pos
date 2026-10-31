import ipaddress
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PIN_PATTERN = re.compile(r"\d{4,6}")
API_ROOT = Path(__file__).resolve().parents[2]
# apps/api -> repository root. On the server this is /opt/ai-pos, next to apps/.
REPO_ROOT = API_ROOT.parent.parent
AppEnv = Literal["development", "dev", "production", "test"]
APP_ENVS: tuple[str, ...] = ("development", "dev", "production", "test")


def is_ip_host(value: str) -> bool:
    """True for an IPv4 or IPv6 address, which cannot carry a store subdomain."""
    host = value.strip().removeprefix("[").removesuffix("]")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def current_app_env() -> str:
    """APP_ENV picks a repo-root env file: .env (your machine), .env.dev, .env.production, or .env.test."""
    value = os.environ.get("APP_ENV", "").strip().lower() or "development"
    if value not in APP_ENVS:
        raise RuntimeError(f"APP_ENV must be one of {', '.join(APP_ENVS)}; got {value!r}.")
    return value


def env_file_name(app_env: str | None = None) -> str:
    """development is `.env`; dev and production are `.env.dev` and `.env.production`."""
    name = app_env or current_app_env()
    return ".env" if name == "development" else f".env.{name}"


def env_file_path(app_env: str | None = None) -> Path:
    return REPO_ROOT / env_file_name(app_env)


def env_files(app_env: str | None = None) -> tuple[Path, ...]:
    """Public file first, then an optional `.local` overlay for secrets that must not be committed."""
    primary = env_file_path(app_env)
    return (primary, primary.with_name(f"{primary.name}.local"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        # The repo-root env file also holds Vite and register keys. Those are not API settings.
        extra="ignore",
        case_sensitive=False,
        # Validation errors would otherwise echo the settings (secrets included) into logs.
        hide_input_in_errors=True,
    )

    app_env: AppEnv = "development"
    database_url: str
    # Multi-tenancy. Unset CONTROL_DATABASE_URL keeps the API single-tenant on DATABASE_URL.
    control_database_url: str | None = None
    # Hosts like client1.axizpos.com or client1.localhost resolve to tenant "client1".
    tenant_base_domains: str = "axizpos.com,localhost"
    # Postgres URL for tenant databases; "{database}" is replaced by the tenant's database name.
    # Unset: DATABASE_URL with its database name swapped.
    tenant_database_url_template: str | None = None
    # Public base URL handed to activated registers; "{tenant}" is replaced by the subdomain.
    tenant_public_url_template: str = "https://{tenant}.axizpos.com"
    # Tenant used for requests that name none (plain localhost in development).
    default_tenant: str | None = None
    # Cache and rate limits. Required in production. Unset elsewhere uses an in-process stand-in.
    redis_url: str | None = None
    jwt_secret: str = Field(min_length=32)
    pin_salt: str = Field(min_length=16)
    encryption_secret: str = Field(min_length=32)
    api_key: str = Field(min_length=16)
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: str
    access_token_expire_minutes: int = Field(default=30, ge=1, le=24 * 60)
    sync_max_batch_size: int = Field(default=100, ge=1, le=1000)
    login_max_attempts: int = Field(default=5, ge=1, le=50)
    login_lockout_minutes: int = Field(default=15, ge=1, le=24 * 60)
    # Offline sales older than this are refused and need a manual entry.
    sale_max_age_days: int = Field(default=30, ge=1, le=365)
    credit_hold_overdue_days: int = Field(default=30, ge=1, le=365)
    # Production sets this false so only per-device keys (devices table) authenticate registers.
    allow_shared_api_key: bool = True
    # Background jobs (expiry sweeps, forecasts, reminders, FX sync). Tests turn this off.
    scheduler_enabled: bool = True
    public_base_url: str = "http://localhost:8000"
    # Where tenants send business-type and module change requests.
    support_email: str = "info@axizpos.com"
    # POS-company console (apps/super-admin). Its tokens are signed with their own secret and audience, so no
    # store token ever opens it; unset, the console API answers 503.
    console_jwt_secret: str | None = Field(default=None, min_length=32)
    console_token_minutes: int = Field(default=60, ge=5, le=12 * 60)
    # Browser origins of the console app, e.g. https://console.axizpos.com,http://localhost:5174.
    console_origins: str = ""
    # Console Super Admin kept by `python -m app.tenancy.cli init` when email and password are both set.
    console_admin_email: str | None = None
    console_admin_name: str = "Ahsan Khalil"
    console_admin_password: str | None = None
    # POS-company billing. Empty uses the recorded-payment simulator for go-live checkout.
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None

    # Messaging provider credentials. Which provider each channel uses is chosen in Settings > Messaging.
    whatsapp_token: str | None = None
    whatsapp_phone_number_id: str | None = None
    whatsapp_api_version: str = "v20.0"
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_starttls: bool = True
    sms_http_url: str | None = None
    sms_http_token: str | None = None
    sms_sender: str | None = None

    # QR payments. "dev" simulates the customer paying; "emvco" renders a merchant-presented EMVCo QR whose
    # payment the acquirer confirms through the signed webhook.
    payment_provider: str = Field(default="dev", pattern="^(dev|emvco)$")
    payment_webhook_secret: str | None = None
    emvco_merchant_account: str | None = None
    emvco_merchant_name: str = "AI POS"
    emvco_merchant_city: str = "Dubai"
    emvco_mcc: str = Field(default="5732", pattern=r"^\d{4}$")
    payment_intent_minutes: int = Field(default=10, ge=1, le=60)

    # Integrated card terminals and buy-now-pay-later. Each provider falls back to its simulator until its
    # credentials are set, so a demo or practice tenant can run the whole flow without a merchant account.
    card_terminal_provider: str = Field(default="simulator", pattern="^(simulator|ngenius|geidea)$")
    # Comma-separated BNPL providers offered at the till, e.g. "tabby,tamara".
    bnpl_providers: str = "simulator"
    # Shared secret for HMAC-signed webhooks from adapters that sign with it (the simulator, Geidea).
    integration_webhook_secret: str | None = None
    integration_timeout_seconds: int = Field(default=15, ge=2, le=60)
    ngenius_api_key: str | None = None
    ngenius_outlet_ref: str | None = None
    ngenius_base_url: str = "https://api-gateway.sandbox.ngenius-payments.com"
    geidea_public_key: str | None = None
    geidea_api_password: str | None = None
    geidea_base_url: str = "https://api.merchant.geidea.net"
    tabby_secret_key: str | None = None
    tabby_merchant_code: str | None = None
    tabby_base_url: str = "https://api.tabby.ai"
    tamara_api_token: str | None = None
    tamara_notification_token: str | None = None
    tamara_base_url: str = "https://api-sandbox.tamara.co"

    # Exchange rates. "manual" keeps managers' rates for foreign cash; "open_er_api" refreshes those daily.
    fx_provider: str = Field(default="manual", pattern="^(manual|open_er_api)$")
    # Registers may use a cached rate up to this far from the latest one (basis points).
    fx_tolerance_bps: int = Field(default=300, ge=0, le=5000)
    # Informational conversion. The key, when the provider requires one, stays on the server.
    fx_api_url: str = "https://open.er-api.com/v6/latest"
    fx_api_key: str | None = None
    fx_quote_ttl_seconds: int = Field(default=3600, ge=60, le=86_400)
    fx_quote_stale_seconds: int = Field(default=604_800, ge=3600, le=2_592_000)
    fx_refresh_seconds: int = Field(default=30, ge=5, le=600)

    # AI assistant. "builtin" answers from the report tools with no model. "ollama" and "openai" only explain
    # those same tools. Ollama does not use ASSISTANT_API_KEY. OpenAI stays available and is not the default.
    assistant_provider: str = Field(default="builtin", pattern="^(builtin|openai|ollama)$")
    assistant_api_key: str | None = None
    assistant_model: str = "gpt-4o-mini"
    assistant_base_url: str = "https://api.openai.com/v1"
    assistant_timeout_seconds: int = Field(default=30, ge=5, le=120)
    assistant_fallback_provider: str = Field(default="builtin", pattern="^builtin$")
    assistant_fallback_enabled: bool = True
    assistant_cache_ttl_seconds: int = Field(default=90, ge=0, le=3600)
    # Hostname "ollama" is the Compose service. A host-run API uses the loopback publish instead.
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:8b"
    ollama_timeout_seconds: int = Field(default=45, ge=5, le=180)
    ollama_chat_timeout_seconds: int = Field(default=20, ge=5, le=60)
    ollama_keep_alive: str = "10m"
    ollama_temperature: float = Field(default=0.2, ge=0, le=1)
    ollama_num_ctx: int = Field(default=4096, ge=512, le=32768)
    ollama_num_predict: int = Field(default=192, ge=32, le=1024)
    ollama_max_retries: int = Field(default=1, ge=0, le=3)
    ollama_max_tool_rounds: int = Field(default=2, ge=1, le=8)

    # Self-service signup on the bare domain (multi-tenant mode only). The one-time code goes out on this channel
    # through the messaging adapters; "log" writes it to the API log and, outside production, returns it.
    signup_enabled: bool = True
    signup_otp_channel: str = Field(default="log", pattern="^(log|whatsapp|sms|email)$")
    # Fixed 6-digit code. Outside development, signup accepts only this code and does not send a message.
    # In development a fresh code is still emailed, and this code is accepted as well.
    signup_otp_code: str | None = Field(default=None, pattern=r"^\d{6}$")
    signup_otp_minutes: int = Field(default=3, ge=2, le=60)
    signup_max_per_hour: int = Field(default=5, ge=1, le=100)

    # Installers a Super Admin downloads from the portal. CI publishes each POS release to <dir>/pos/<version>/;
    # the folder is shared by every tenant on the server.
    downloads_dir: str = str(API_ROOT.parents[1] / "downloads")

    admin_username: str | None = None
    admin_email: str | None = None
    admin_full_name: str = "Super Admin"
    admin_password: str | None = Field(default=None, min_length=10, max_length=128)
    admin_pin: str | None = None

    @field_validator("database_url", "control_database_url")
    @classmethod
    def database_url_scheme(cls, value: str | None) -> str | None:
        if value == "":
            return None
        if value is not None and not (value.startswith("postgresql") or value.startswith("sqlite")):
            raise ValueError("Database URLs must start with postgresql or sqlite.")
        return value

    @field_validator("admin_pin")
    @classmethod
    def admin_pin_digits(cls, value: str | None) -> str | None:
        if value is not None and PIN_PATTERN.fullmatch(value) is None:
            raise ValueError("ADMIN_PIN must be 4 to 6 digits.")
        return value

    @field_validator("cors_origins")
    @classmethod
    def cors_origins_list(cls, value: str) -> str:
        origins = [item.strip() for item in value.split(",") if item.strip()]
        if not origins:
            raise ValueError("CORS_ORIGINS must list at least one origin.")
        for origin in origins:
            if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s,]+", origin):
                raise ValueError(f"CORS origin is invalid: {origin}")
        return ",".join(origins)

    @model_validator(mode="after")
    def console_secret_is_its_own(self) -> "Settings":
        if self.console_jwt_secret is not None and self.console_jwt_secret == self.jwt_secret:
            raise ValueError("CONSOLE_JWT_SECRET must differ from JWT_SECRET.")
        return self

    @model_validator(mode="after")
    def production_is_configured(self) -> "Settings":
        if self.app_env != "production":
            return self
        problems = [
            name.upper() for name, value in self.model_dump().items() if isinstance(value, str) and "change-me" in value
        ]
        if not self.tenancy_enabled:
            problems.append("CONTROL_DATABASE_URL (required: production is multi-tenant)")
        if self.default_tenant:
            problems.append("DEFAULT_TENANT (must be unset: every request names its store)")
        if not self.redis_url:
            problems.append("REDIS_URL (required for tenant-scoped cache and rate limits)")
        if self.signup_enabled and self.signup_otp_channel == "log" and not self.signup_otp_code:
            problems.append(
                "SIGNUP_OTP_CHANNEL (log delivers no code; pick whatsapp, sms or email, "
                "set SIGNUP_OTP_CODE, or SIGNUP_ENABLED=false)"
            )
        if problems:
            raise ValueError("Production settings are not ready: " + ", ".join(problems))
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [item.strip() for item in self.cors_origins.split(",") if item.strip()]
        return origins + [item.strip() for item in self.console_origins.split(",") if item.strip()]

    @property
    def tenancy_enabled(self) -> bool:
        return bool(self.control_database_url)

    @property
    def tenant_domain_list(self) -> list[str]:
        return [item.strip().lower().lstrip(".") for item in self.tenant_base_domains.split(",") if item.strip()]

    @property
    def tenant_origin_regex(self) -> str | None:
        """Browser origins of tenant portals (https://{tenant}.axizpos.com) and of signup on the bare domain itself;
        http(s) on localhost."""
        if not self.tenancy_enabled:
            return None
        parts = []
        for domain in self.tenant_domain_list:
            # A public IP is opened as http://<ip> until a domain and certificate exist.
            scheme = "https?" if domain == "localhost" or is_ip_host(domain) else "https"
            host = re.escape(domain) if is_ip_host(domain) else rf"([a-z0-9-]+\.)?{re.escape(domain)}"
            parts.append(rf"{scheme}://{host}(:\d+)?")
        return "^(" + "|".join(parts) + ")$" if parts else None


@lru_cache
def get_settings() -> Settings:
    app_env = current_app_env()
    return Settings(_env_file=env_files(app_env), app_env=app_env)
