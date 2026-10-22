"""Installers published for download from the portal.

CI copies each POS release to <DOWNLOADS_DIR>/pos/<version>/ together with a manifest.json:
    {"version": "0.2.0", "published_at": "2026-10-21T08:00:00Z", "notes": "...",
     "files": [{"name": "AI POS_0.2.0_x64-setup.exe", "sha256": "..."}]}
A folder copied by hand without a manifest still lists; its hashes are computed on first read.
"""

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from app.core.config import Settings
from app.core.errors import ApiError
from app.schemas.downloads import AppRelease, DownloadsOut, InstallerFile, InstallerKind

logger = logging.getLogger("ai_pos.downloads")

APP = "pos"
VERSION = re.compile(r"^\d+\.\d+\.\d+$")
KINDS: dict[str, InstallerKind] = {".exe": "exe", ".msi": "msi"}
MEDIA_TYPES: dict[InstallerKind, str] = {
    "exe": "application/vnd.microsoft.portable-executable",
    "msi": "application/x-msi",
}


def _app_dir(settings: Settings) -> Path:
    return Path(settings.downloads_dir) / APP


@lru_cache(maxsize=64)
def _hash(path: str, size: int, modified_ns: int) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _manifest(folder: Path) -> dict:
    path = folder / "manifest.json"
    if not path.is_file():
        return {}
    try:
        # utf-8-sig: manifests saved by Windows tools often start with a byte-order mark.
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        logger.warning("Ignoring unreadable %s", path)
        return {}
    return data if isinstance(data, dict) else {}


def _published_at(manifest: dict, folder: Path) -> datetime:
    raw = manifest.get("published_at")
    if isinstance(raw, str):
        try:
            stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.fromtimestamp(folder.stat().st_mtime, tz=UTC)


def _release(folder: Path) -> AppRelease | None:
    manifest = _manifest(folder)
    hashes = {
        entry.get("name"): entry.get("sha256")
        for entry in manifest.get("files", [])
        if isinstance(entry, dict) and isinstance(entry.get("sha256"), str)
    }
    files = []
    for path in sorted(folder.iterdir(), key=lambda item: item.name):
        kind = KINDS.get(path.suffix.lower())
        if kind is None or not path.is_file():
            continue
        stat = path.stat()
        files.append(
            InstallerFile(
                name=path.name,
                kind=kind,
                size_bytes=stat.st_size,
                sha256=hashes.get(path.name) or _hash(str(path), stat.st_size, stat.st_mtime_ns),
                download_path=f"/downloads/{APP}/{folder.name}/{path.name}",
            )
        )
    if not files:
        return None
    notes = manifest.get("notes")
    return AppRelease(
        app=APP,
        version=folder.name,
        published_at=_published_at(manifest, folder),
        notes=notes.strip() or None if isinstance(notes, str) else None,
        # The setup .exe first: it is what a store owner should run.
        files=sorted(files, key=lambda item: (item.kind != "exe", item.name)),
    )


def list_releases(settings: Settings) -> DownloadsOut:
    base = _app_dir(settings)
    if not base.is_dir():
        return DownloadsOut(releases=[])
    releases = [
        release
        for folder in base.iterdir()
        if folder.is_dir() and VERSION.match(folder.name)
        for release in [_release(folder)]
        if release is not None
    ]
    releases.sort(key=lambda release: tuple(int(part) for part in release.version.split(".")), reverse=True)
    return DownloadsOut(releases=releases)


def installer(settings: Settings, version: str, filename: str) -> tuple[Path, InstallerKind]:
    """Resolves a listed installer; anything else (unknown version, other files, path tricks) is a 404."""
    missing = ApiError(404, "not_found", "That installer is not available.")
    if not VERSION.match(version) or Path(filename).name != filename:
        raise missing
    kind = KINDS.get(Path(filename).suffix.lower())
    folder = (_app_dir(settings) / version).resolve()
    path = (folder / filename).resolve()
    if kind is None or path.parent != folder or not path.is_file():
        raise missing
    return path, kind
