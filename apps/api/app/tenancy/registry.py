"""Looks tenants up in the control database and keeps one engine per tenant database."""

import os
import re
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings, is_ip_host
from app.core.database import build_engine
from app.core.security import decrypt_value, encrypt_value
from app.tenancy.context import CONTROL_SESSION, TenantRef
from app.tenancy.models import Tenant

SLUG = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?")
# "console" is the POS-company console's own host; no store may claim it.
RESERVED = frozenset({"www", "api", "admin", "app", "control", "status", "mail", "console", "support"})
CACHE_SECONDS = 30.0


@dataclass(frozen=True)
class Lookup:
    tenant: TenantRef | None
    status: str | None


_lookups: dict[str, tuple[float, Lookup]] = {}
_engines: dict[str, Engine] = {}
_factories: dict[str, sessionmaker[Session]] = {}
_lock = threading.Lock()


def valid_slug(slug: str) -> bool:
    return SLUG.fullmatch(slug) is not None and slug not in RESERVED


def slug_from_domain(value: str | None, settings: Settings) -> str | None:
    """'client1', 'client1.axizpos.com', 'https://client1.axizpos.com/x' or 'client1.localhost:5173' -> 'client1'."""
    if not value:
        return None
    host = value.strip().lower()
    host = re.sub(r"^[a-z]+://", "", host).split("/", 1)[0].split(":", 1)[0].rstrip(".")
    if host in settings.tenant_domain_list:
        return None
    if "." not in host:
        return host if valid_slug(host) else None
    for domain in settings.tenant_domain_list:
        suffix = "." + domain
        if host.endswith(suffix):
            label = host[: -len(suffix)]
            return label if "." not in label and valid_slug(label) else None
    return None


@lru_cache
def _control_factory(url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=build_engine(url), expire_on_commit=False, info={CONTROL_SESSION: True})


def _database_exists(url: str) -> bool:
    engine = build_engine(url)
    try:
        with engine.connect():
            return True
    except OperationalError as exc:
        if "does not exist" in str(exc).lower():
            return False
        raise
    finally:
        engine.dispose()


@lru_cache
def _resolve_control_url(control_url: str, operational_url: str) -> str:
    """Use the operational database when the named control database was never created."""
    if control_url == operational_url or _database_exists(control_url):
        return control_url
    return operational_url


def control_url(settings: Settings) -> str:
    if not settings.control_database_url:
        raise RuntimeError("CONTROL_DATABASE_URL is not configured.")
    return _resolve_control_url(settings.control_database_url, settings.database_url)


def control_session(settings: Settings | None = None) -> Session:
    settings = settings or get_settings()
    return _control_factory(control_url(settings))()


def _ref(row: Tenant, settings: Settings) -> TenantRef:
    plane = row.data_plane if row.data_plane in ("legacy", "shared") else "legacy"
    # Shared stores all use the one operational database. The encrypted URL is only for legacy stores.
    url = settings.database_url if plane == "shared" else decrypt_value(row.database_url_encrypted, settings)
    return TenantRef(
        id=str(row.id),
        slug=row.slug,
        name=row.name,
        database_url=url,
        data_plane=plane,
    )


def ref_for(row: Tenant, settings: Settings | None = None) -> TenantRef:
    """The connection details of a tenant row, whatever its status (the console reaches suspended stores too)."""
    return _ref(row, settings or get_settings())


def _remember(slug: str, result: Lookup) -> Lookup:
    _lookups[slug] = (time.monotonic() + CACHE_SECONDS, result)
    from app.core.cache import set_value

    tenant = result.tenant
    if tenant is None:
        set_value(f"registry:{slug}", "missing", int(CACHE_SECONDS))
        return result
    import json

    set_value(
        f"registry:{slug}",
        json.dumps(
            {
                "id": tenant.id,
                "slug": tenant.slug,
                "name": tenant.name,
                "status": result.status,
                "data_plane": tenant.data_plane,
                "database_url": tenant.database_url,
            }
        ),
        int(CACHE_SECONDS),
    )
    return result


def _from_cache(slug: str, settings: Settings) -> Lookup | None:
    from app.core.cache import get_value

    raw = get_value(f"registry:{slug}")
    if raw is None:
        return None
    if raw == "missing":
        return Lookup(tenant=None, status=None)
    import json

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    plane = data.get("data_plane") or "legacy"
    url = settings.database_url if plane == "shared" else data.get("database_url") or ""
    tenant = TenantRef(
        id=data["id"],
        slug=data["slug"],
        name=data["name"],
        database_url=url,
        data_plane=plane,
    )
    return Lookup(tenant=tenant, status=data.get("status"))


def lookup(slug: str, settings: Settings | None = None) -> Lookup:
    settings = settings or get_settings()
    now = time.monotonic()
    cached = _lookups.get(slug)
    if cached is not None and cached[0] > now:
        return cached[1]
    shared = _from_cache(slug, settings)
    if shared is not None:
        _lookups[slug] = (now + CACHE_SECONDS, shared)
        return shared
    with control_session(settings) as db:
        row = db.scalar(select(Tenant).where(Tenant.slug == slug))
        result = (
            Lookup(tenant=None, status=None) if row is None else Lookup(tenant=_ref(row, settings), status=row.status)
        )
    return _remember(slug, result)


def invalidate(slug: str | None = None) -> None:
    from app.core.cache import clear_prefix, delete

    if slug is None:
        _lookups.clear()
        _resolve_control_url.cache_clear()
        clear_prefix("registry:")
    else:
        _lookups.pop(slug, None)
        delete(f"registry:{slug}")


def active_tenants(settings: Settings | None = None) -> list[TenantRef]:
    settings = settings or get_settings()
    with control_session(settings) as db:
        rows = db.scalars(select(Tenant).where(Tenant.status == "active").order_by(Tenant.slug)).all()
        return [_ref(row, settings) for row in rows]


def session_factory_for(tenant: TenantRef) -> sessionmaker[Session]:
    with _lock:
        factory = _factories.get(tenant.database_url)
        if factory is None:
            engine = build_engine(tenant.database_url)
            _engines[tenant.database_url] = engine
            factory = sessionmaker(bind=engine, expire_on_commit=False)
            _factories[tenant.database_url] = factory
        return factory


def tenant_database_url(database: str, settings: Settings | None = None) -> str:
    """URL of a tenant database on the same server as DATABASE_URL (or TENANT_DATABASE_URL_TEMPLATE)."""
    settings = settings or get_settings()
    if settings.tenant_database_url_template:
        return settings.tenant_database_url_template.replace("{database}", database)
    url = make_url(settings.database_url)
    if url.get_backend_name() == "sqlite":
        raise RuntimeError("Set TENANT_DATABASE_URL_TEMPLATE to create tenants on SQLite.")
    return url.set(database=database).render_as_string(hide_password=False)


def resolve_cli_database_url(settings: Settings | None = None, slug: str | None = None) -> str:
    """Database for a command-line tool (seed, Alembic): the TENANT's database, or DATABASE_URL if single-tenant."""
    settings = settings or get_settings()
    slug = slug or os.environ.get("TENANT")
    if not settings.tenancy_enabled:
        return settings.database_url
    if not slug:
        raise RuntimeError("Multi-tenant mode: set TENANT=<slug> (or pass -x tenant=<slug> to Alembic).")
    found = lookup(slug, settings)
    if found.tenant is None:
        raise RuntimeError(f"Tenant '{slug}' is not registered in the control database.")
    return found.tenant.database_url


@dataclass(frozen=True)
class Identity:
    slug: str
    name: str
    domain: str
    url: str


def current_identity(settings: Settings | None = None) -> Identity:
    """The tenant serving this request (single-tenant installs report the API's own address)."""
    from app.tenancy.context import current_tenant

    settings = settings or get_settings()
    ref = current_tenant()
    if ref is None:
        host = urlparse(settings.public_base_url).hostname or "localhost"
        return Identity(slug="default", name="AI POS", domain=host, url=settings.public_base_url.rstrip("/"))
    return Identity(
        slug=ref.slug,
        name=ref.name,
        domain=tenant_domain_for(ref.slug, settings),
        url=tenant_public_url(ref.slug, settings),
    )


def tenant_domain_for(slug: str, settings: Settings | None = None) -> str:
    """client1.example.com, or just the store code when the server is reached by a public IP."""
    settings = settings or get_settings()
    base = settings.tenant_domain_list[0] if settings.tenant_domain_list else "axizpos.com"
    if is_ip_host(base):
        return slug
    return f"{slug}.{base}"


def tenant_public_url(slug: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return settings.tenant_public_url_template.replace("{tenant}", slug).rstrip("/")


def encrypt_database_url(url: str, settings: Settings | None = None) -> str:
    return encrypt_value(url, settings or get_settings())
