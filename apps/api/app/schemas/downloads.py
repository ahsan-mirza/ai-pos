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


class LatestInstaller(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    notes: str | None = None
    pub_date: datetime
    sha256: str
    # Public file. The register joins this to its API host.
    path: str = "/api/download/installer/win"


class DownloadsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Newest first; the first entry is what new registers should install.
    releases: list[AppRelease]
