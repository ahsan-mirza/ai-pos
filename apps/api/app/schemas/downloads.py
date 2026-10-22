from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

InstallerKind = Literal["exe", "msi"]


class InstallerFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: InstallerKind
    size_bytes: int
    sha256: str
    # Relative to /api/v1; the portal fetches it with the admin's token.
    download_path: str


class AppRelease(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app: Literal["pos"]
    version: str
    published_at: datetime
    notes: str | None = None
    files: list[InstallerFile]


class DownloadsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Newest first; the first entry is what new registers should install.
    releases: list[AppRelease]
