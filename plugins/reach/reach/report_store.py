"""Campaign report files. Local disk is the supported backend. Object storage is not wired up."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from app.services.media_storage import ROOT, tenant_slug


class ReportStoreError(Exception):
    pass


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_key(key: str) -> Path:
    cleaned = key.replace("\\", "/").lstrip("/")
    if not cleaned or cleaned.startswith("../") or "/../" in f"/{cleaned}/" or ".." in Path(cleaned).parts:
        raise ReportStoreError("Report key is not allowed.")
    path = (ROOT / tenant_slug() / cleaned).resolve()
    root = (ROOT / tenant_slug()).resolve()
    if path != root and root not in path.parents:
        raise ReportStoreError("Report key is not allowed.")
    return path


def put(key: str, data: bytes) -> str:
    path = _safe_key(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)
    return checksum(data)


def get(key: str) -> bytes | None:
    path = _safe_key(key)
    if not path.is_file():
        return None
    return path.read_bytes()


def exists(key: str) -> bool:
    return _safe_key(key).is_file()
