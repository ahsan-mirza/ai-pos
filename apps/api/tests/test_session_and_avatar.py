"""Access tokens renew while they are still valid. Profile photos reuse tenant media storage."""

import io
import uuid
from datetime import timedelta

import jwt
import pytest
from PIL import Image
from sqlalchemy import select
from tests.test_auth import API_KEY, CASHIER_PIN, bearer, login

from app.core.config import get_settings
from app.core.permissions import SUPER_ADMIN_ROLE_ID
from app.core.security import create_access_token, hash_password
from app.models.user import User
from app.services import media_storage


@pytest.fixture(autouse=True)
def media_root(tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "ROOT", tmp_path)
    return tmp_path


def _headers(client) -> dict[str, str]:
    response = login(client)
    assert response.status_code == 200, response.text
    return bearer(response.json()["access_token"])


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "navy").save(buffer, "PNG")
    return buffer.getvalue()


def test_a_live_session_renews_and_an_expired_one_does_not(client):
    first = login(client)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["user"]["avatar_url"] is None
    headers = bearer(body["access_token"])

    renewed = client.post("/api/v1/auth/refresh", headers=headers)
    assert renewed.status_code == 200, renewed.text
    fresh = renewed.json()["access_token"]
    assert fresh
    assert client.get("/api/v1/auth/me", headers=bearer(fresh)).status_code == 200

    claims = jwt.decode(body["access_token"], options={"verify_signature": False}, algorithms=["HS256"])
    expired, _ = create_access_token(
        subject=str(claims["sub"]),
        scope="portal",
        token_version=int(claims["ver"]),
        settings=get_settings(),
        expires_in=timedelta(minutes=-5),
        tenant_id=str(claims["tid"]) if claims.get("tid") else None,
    )
    rejected = client.post("/api/v1/auth/refresh", headers=bearer(expired))
    assert rejected.status_code == 401
    assert client.get("/api/v1/auth/me", headers=bearer(expired)).status_code == 401

    recent, _ = create_access_token(
        subject=str(claims["sub"]),
        scope="portal",
        token_version=int(claims["ver"]),
        settings=get_settings(),
        expires_in=timedelta(seconds=-30),
        tenant_id=str(claims["tid"]) if claims.get("tid") else None,
    )
    caught_up = client.post("/api/v1/auth/refresh", headers=bearer(recent))
    assert caught_up.status_code == 200, caught_up.text
    assert client.get("/api/v1/auth/me", headers=bearer(recent)).status_code == 401


def test_password_change_and_a_disabled_account_stop_renewal(client, session):
    headers = _headers(client)
    changed = client.post(
        "/api/v1/auth/me/password",
        headers=headers,
        json={"current_password": "root-password-123", "password": "another-password"},
    )
    assert changed.status_code == 200, changed.text
    assert client.post("/api/v1/auth/refresh", headers=headers).status_code == 401
    kept = bearer(changed.json()["access_token"])
    assert client.post("/api/v1/auth/refresh", headers=kept).status_code == 200

    user = session.scalar(select(User).where(User.username == "admin"))
    assert user is not None
    user.is_active = False
    session.commit()
    assert client.post("/api/v1/auth/refresh", headers=kept).status_code == 401


def test_a_forbidden_request_leaves_the_session_usable(client):
    signed = client.post(
        "/api/v1/auth/login-pin",
        json={"username": "cashier", "pin": CASHIER_PIN},
        headers={"X-Api-Key": API_KEY},
    )
    assert signed.status_code == 200, signed.text
    headers = bearer(signed.json()["access_token"])
    forbidden = client.get("/api/v1/users", headers=headers)
    assert forbidden.status_code == 403
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/refresh", headers=headers).status_code == 200


def test_profile_photo_is_stored_replaced_and_kept_when_the_name_changes(client, session):
    headers = _headers(client)
    missing = client.get("/api/v1/auth/me", headers=headers)
    assert missing.json()["avatar_url"] is None

    refused = client.post(
        "/api/v1/auth/me/avatar", headers=headers, files={"file": ("note.txt", b"hello", "text/plain")}
    )
    assert refused.status_code == 415
    huge = b"x" * (5 * 1024 * 1024 + 1)
    oversized = client.post("/api/v1/auth/me/avatar", headers=headers, files={"file": ("big.png", huge, "image/png")})
    assert oversized.status_code == 413
    assert client.post("/api/v1/auth/me/avatar", files={"file": ("a.png", _png(), "image/png")}).status_code == 401

    uploaded = client.post("/api/v1/auth/me/avatar", headers=headers, files={"file": ("me.png", _png(), "image/png")})
    assert uploaded.status_code == 200, uploaded.text
    first_url = uploaded.json()["avatar_url"]
    assert first_url
    assert "/media/" in first_url
    assert "/avatars/" in first_url
    key = first_url.split("/media/", 1)[1]
    assert client.get(f"/media/{key}").status_code == 200
    assert client.get("/media/other-store/" + key.split("/", 1)[1]).status_code == 404

    renamed = client.patch("/api/v1/auth/me", headers=headers, json={"full_name": "Amina Noor"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["full_name"] == "Amina Noor"
    assert renamed.json()["avatar_url"] == first_url

    replaced = client.post("/api/v1/auth/me/avatar", headers=headers, files={"file": ("next.png", _png(), "image/png")})
    assert replaced.status_code == 200, replaced.text
    second_url = replaced.json()["avatar_url"]
    assert second_url != first_url
    assert client.get(f"/media/{key}").status_code == 404
    second_key = second_url.split("/media/", 1)[1]
    assert client.get(f"/media/{second_key}").status_code == 200

    session.add(
        User(
            id=uuid.uuid4(),
            username="other",
            email="other@example.com",
            full_name="Other Person",
            hashed_password=hash_password("other-password-1"),
            is_active=True,
            store_id=None,
            role_id=uuid.UUID(SUPER_ADMIN_ROLE_ID),
            has_pos_access=False,
            has_portal_access=True,
            failed_login_attempts=0,
            token_version=0,
        )
    )
    session.commit()
    other = login(client, "other", "other-password-1")
    assert other.status_code == 200, other.text
    other_headers = bearer(other.json()["access_token"])
    theirs = client.post(
        "/api/v1/auth/me/avatar", headers=other_headers, files={"file": ("them.png", _png(), "image/png")}
    )
    assert theirs.status_code == 200, theirs.text
    assert theirs.json()["id"] != uploaded.json()["id"]
    still = client.get("/api/v1/auth/me", headers=headers)
    assert still.json()["avatar_url"] == second_url

    cleared = client.delete("/api/v1/auth/me/avatar", headers=headers)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["avatar_url"] is None
    assert cleared.json()["full_name"] == "Amina Noor"
    assert client.get(f"/media/{second_key}").status_code == 404
    assert client.get("/api/v1/auth/me", headers=headers).json()["avatar_url"] is None


def test_login_lists_the_saved_photo(client):
    headers = _headers(client)
    uploaded = client.post("/api/v1/auth/me/avatar", headers=headers, files={"file": ("me.png", _png(), "image/png")})
    assert uploaded.status_code == 200, uploaded.text
    again = login(client)
    assert again.status_code == 200, again.text
    assert again.json()["user"]["avatar_url"] == uploaded.json()["avatar_url"]
    listed = client.get("/api/v1/users", headers=headers)
    assert listed.status_code == 200, listed.text
    admin = next(user for user in listed.json() if user["username"] == "admin")
    assert admin["avatar_url"] == uploaded.json()["avatar_url"]
