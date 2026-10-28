"""Media files (product photos), kept apart per tenant under storage/{tenant_slug}/media/. Keys are random, so a
URL cannot be guessed; files are served without sign-in at /media/{tenant}/{key} with long cache headers.

LocalStorage is the only backend today; anything implementing MediaStorage (S3, Oracle Object Storage) can replace
it in storage_for() without touching callers."""

import re
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings
from app.tenancy.context import current_tenant

ROOT = Path(__file__).resolve().parents[2] / "storage"
KEY = re.compile(r"^[a-z]+/[0-9a-f]{32}(-thumb)?\.webp$")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
SINGLE_TENANT = "default"


class MediaStorage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...

    def path(self, key: str) -> Path | None: ...

    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path, tenant: str) -> None:
        if not SLUG.fullmatch(tenant):
            raise ValueError("Invalid tenant slug.")
        self.base = root / tenant / "media"

    def _file(self, key: str) -> Path:
        if not KEY.fullmatch(key):
            raise ValueError("Invalid media key.")
        return self.base / key

    def put(self, key: str, data: bytes) -> None:
        target = self._file(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(".part")
        partial.write_bytes(data)
        partial.replace(target)

    def path(self, key: str) -> Path | None:
        try:
            target = self._file(key)
        except ValueError:
            return None
        return target if target.is_file() else None

    def delete(self, key: str) -> None:
        try:
            self._file(key).unlink(missing_ok=True)
        except ValueError:
            return


def tenant_slug() -> str:
    tenant = current_tenant()
    return tenant.slug if tenant is not None else SINGLE_TENANT


def storage_for(tenant: str | None = None) -> MediaStorage:
    return LocalStorage(ROOT, tenant or tenant_slug())


def place(key: str) -> None:
    """Copy a photo that was saved with no store into the store this request is bound to.

    Older uploads wrote under storage/default while the gallery asked for /media/{store}/.
    The bytes are copied forward so the existing row's URL loads.
    """
    try:
        slug = tenant_slug()
        if slug == SINGLE_TENANT:
            return
        current = storage_for(slug)
        if current.path(key) is not None:
            return
        legacy = storage_for(SINGLE_TENANT).path(key)
        if legacy is None:
            return
        current.put(key, legacy.read_bytes())
    except (OSError, ValueError):
        return


def url(key: str) -> str:
    place(key)
    return f"{get_settings().public_base_url.rstrip('/')}/media/{tenant_slug()}/{key}"
