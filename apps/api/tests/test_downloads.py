import hashlib
import json
import os

import pytest

from app.core.config import get_settings
from app.main import app
from test_returns import STORE_MANAGER_ROLE, admin_token, bearer, device
from test_settings import portal_user


@pytest.fixture()
def downloads(tmp_path, client):
    settings = get_settings().model_copy(update={"downloads_dir": str(tmp_path)})
    app.dependency_overrides[get_settings] = lambda: settings
    yield tmp_path / "pos"
    app.dependency_overrides.pop(get_settings, None)


def publish(root, version: str, files: dict[str, bytes], manifest: dict | None = None) -> None:
    folder = root / version
    folder.mkdir(parents=True)
    for name, data in files.items():
        (folder / name).write_bytes(data)
    if manifest is not None:
        (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_lists_releases_newest_first_with_hashes(client, downloads) -> None:
    exe = b"MZ setup 0.10.0"
    publish(
        downloads,
        "0.10.0",
        {"AI POS_0.10.0_x64_en-US.msi": b"msi", "AI POS_0.10.0_x64-setup.exe": exe, "notes.txt": b"x"},
        {
            "published_at": "2026-10-21T08:00:00Z",
            "notes": "Receipt branding",
            "files": [{"name": "AI POS_0.10.0_x64-setup.exe", "sha256": hashlib.sha256(exe).hexdigest()}],
        },
    )
    publish(downloads, "0.9.2", {"AI POS_0.9.2_x64-setup.exe": b"old"})
    (downloads / "latest").mkdir()
    publish(downloads, "0.11.0", {"readme.txt": b"no installer here"})

    response = client.get("/api/v1/downloads", headers=bearer(admin_token(client)))
    assert response.status_code == 200, response.text
    releases = response.json()["releases"]
    assert [release["version"] for release in releases] == ["0.10.0", "0.9.2"]
    newest = releases[0]
    assert newest["notes"] == "Receipt branding"
    assert newest["published_at"].startswith("2026-10-21T08:00:00")
    assert [file["kind"] for file in newest["files"]] == ["exe", "msi"]
    assert newest["files"][0]["sha256"] == hashlib.sha256(exe).hexdigest()
    assert newest["files"][1]["sha256"] == hashlib.sha256(b"msi").hexdigest()
    assert newest["files"][0]["download_path"] == "/downloads/pos/0.10.0/AI POS_0.10.0_x64-setup.exe"


def test_super_admin_downloads_the_installer(client, downloads) -> None:
    publish(downloads, "1.0.0", {"AI POS_1.0.0_x64-setup.exe": b"MZ installer bytes"})
    response = client.get(
        "/api/v1/downloads/pos/1.0.0/AI POS_1.0.0_x64-setup.exe", headers=bearer(admin_token(client))
    )
    assert response.status_code == 200
    assert response.content == b"MZ installer bytes"
    assert "attachment" in response.headers["content-disposition"]


def test_manifest_with_byte_order_mark_is_read(client, downloads) -> None:
    publish(downloads, "1.2.0", {"AI POS_1.2.0_x64-setup.exe": b"MZ"})
    manifest = json.dumps({"notes": "Saved by Notepad", "published_at": "2026-10-01T00:00:00Z"})
    (downloads / "1.2.0" / "manifest.json").write_bytes(b"\xef\xbb\xbf" + manifest.encode())
    release = client.get("/api/v1/downloads", headers=bearer(admin_token(client))).json()["releases"][0]
    assert release["notes"] == "Saved by Notepad"


def test_nothing_published_is_an_empty_list(client, downloads) -> None:
    assert client.get("/api/v1/downloads", headers=bearer(admin_token(client))).json() == {"releases": []}


def test_latest_installer_downloads_without_a_portal_login(client, downloads):
    exe = b"MZ latest"
    publish(downloads, "0.9.0", {"AI POS_0.9.0_x64-setup.exe": b"old"})
    publish(
        downloads,
        "1.4.0",
        {"AI POS_1.4.0_x64-setup.exe": exe},
        {"files": [{"name": "AI POS_1.4.0_x64-setup.exe", "sha256": hashlib.sha256(exe).hexdigest()}]},
    )
    feed = client.get("/api/v1/downloads/latest.json")
    assert feed.status_code == 200
    body = feed.json()
    assert body["version"] == "1.4.0"
    assert body["sha256"] == hashlib.sha256(exe).hexdigest()
    assert body["path"] == "/api/download/installer/win"
    downloaded = client.get(body["path"])
    assert downloaded.status_code == 200
    assert downloaded.content == exe
    assert "AI-POS-Setup-latest.exe" in downloaded.headers["content-disposition"]


def test_missing_installer_is_not_found(client, downloads):
    assert client.get("/api/v1/downloads/latest.json").status_code == 404
    assert client.get("/api/download/installer/win").status_code == 404


def test_only_super_admins_see_downloads(client, downloads) -> None:
    publish(downloads, "1.0.0", {"AI POS_1.0.0_x64-setup.exe": b"MZ"})
    token = admin_token(client)
    manager = portal_user(client, token, username="manager", role_id=STORE_MANAGER_ROLE, store_id=None)
    for path in ("/api/v1/downloads", "/api/v1/downloads/pos/1.0.0/AI POS_1.0.0_x64-setup.exe"):
        assert client.get(path, headers=bearer(manager)).status_code == 403
        assert client.get(path, headers=device()).status_code == 403
        assert client.get(path).status_code == 401


def test_only_listed_installers_can_be_fetched(client, downloads, tmp_path) -> None:
    publish(downloads, "1.0.0", {"AI POS_1.0.0_x64-setup.exe": b"MZ", "manifest.json": b"{}"})
    (tmp_path / "secret.exe").write_bytes(b"not for download")
    token = admin_token(client)
    for path in (
        "/api/v1/downloads/pos/1.0.0/manifest.json",
        "/api/v1/downloads/pos/1.0.0/missing.exe",
        "/api/v1/downloads/pos/latest/AI POS_1.0.0_x64-setup.exe",
        "/api/v1/downloads/pos/1.0.0/..%2F..%2Fsecret.exe",
        f"/api/v1/downloads/pos/1.0.0/{os.path.join('..', '..', 'secret.exe')}",
    ):
        assert client.get(path, headers=bearer(token)).status_code == 404, path
