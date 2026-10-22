import base64
import struct
import uuid
import zlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Store
from test_returns import STORE_ID, STORE_MANAGER_ROLE, admin_token, bearer, device, seed_catalog
from test_settings import portal_user


def png(width: int, height: int, *, padding: int = 0) -> str:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", width, height, 1, 0, 0, 0, 0)
    rows = b"".join(b"\x00" + b"\xff" * ((width + 7) // 8) for _ in range(height))
    raw = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + (chunk(b"tEXt", b"x" * padding) if padding else b"")
        + chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(raw).decode()


def put_receipt(client, token: str, **fields):
    return client.put("/api/v1/settings/receipt", headers=bearer(token), json=fields)


def test_receipt_defaults_are_empty(client) -> None:
    body = client.get("/api/v1/settings/receipt", headers=device()).json()
    assert body["settings"] == {
        "logo_png": None,
        "header_text": None,
        "header_text_ar": None,
        "footer_text": None,
        "footer_text_ar": None,
        "email": None,
        "website": None,
    }
    assert body["store"] is None


def test_receipt_round_trips_and_includes_the_branch(client, session: Session) -> None:
    seed_catalog(client)
    store = session.get(Store, uuid.UUID(STORE_ID))
    assert store is not None
    store.address, store.phone = "Sheikh Zayed Road, Dubai", "+971 4 123 4567"
    session.commit()

    token = admin_token(client)
    logo = png(200, 80)
    saved = put_receipt(
        client,
        token,
        logo_png=logo,
        header_text="  Welcome!  ",
        footer_text="Exchanges within 7 days with receipt.",
        footer_text_ar="الاستبدال خلال 7 أيام",
        email="hello@shop.ae",
        website="",
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["settings"]["header_text"] == "Welcome!"
    assert saved.json()["settings"]["website"] is None

    body = client.get(f"/api/v1/settings/receipt?store_id={STORE_ID}", headers=device()).json()
    assert body["settings"]["logo_png"] == logo
    assert body["settings"]["footer_text_ar"] == "الاستبدال خلال 7 أيام"
    assert body["store"] == {
        "id": STORE_ID,
        "name": "Downtown",
        "address": "Sheikh Zayed Road, Dubai",
        "phone": "+971 4 123 4567",
    }

    log = session.scalars(select(AuditLog).where(AuditLog.action == "settings.receipt")).one()
    assert log.new_values["logo_png"] is True
    assert log.old_values["logo_png"] is False


def test_logo_must_be_a_small_png(client) -> None:
    token = admin_token(client)
    jpeg = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff" + b"0" * 30).decode()
    not_png = "data:image/png;base64," + base64.b64encode(b"GIF89a" + b"0" * 30).decode()
    oversized = png(100, 100, padding=70_000)
    for bad in (jpeg, not_png, "data:image/png;base64,***", png(800, 100), png(300, 500), oversized):
        response = put_receipt(client, token, logo_png=bad)
        assert response.status_code == 422, bad[:40]
    assert put_receipt(client, token, email="not-an-email").status_code == 422


def test_only_business_wide_admins_change_the_receipt(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    manager = portal_user(client, token, username="manager", role_id=STORE_MANAGER_ROLE, store_id=STORE_ID)
    assert put_receipt(client, manager, footer_text="Mine").status_code == 403
    assert client.put("/api/v1/settings/receipt", json={"footer_text": "x"}).status_code == 401
    assert client.put("/api/v1/settings/receipt", headers=device(), json={"footer_text": "x"}).status_code == 403
