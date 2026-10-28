"""A signed-in user can edit their own name and password, and nothing else."""


def _login(client) -> dict[str, str]:
    response = client.post("/api/v1/auth/login-password", json={"username": "admin", "password": "root-password-123"})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_profile_name_saves_and_privileged_fields_are_rejected(client):
    headers = _login(client)
    renamed = client.patch("/api/v1/auth/me", headers=headers, json={"full_name": "Amina Noor"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["full_name"] == "Amina Noor"
    assert renamed.json()["role"]["name"] == "Super Admin"

    again = client.get("/api/v1/auth/me", headers=headers)
    assert again.json()["full_name"] == "Amina Noor"

    blocked = client.patch(
        "/api/v1/auth/me",
        headers=headers,
        json={"full_name": "Amina Noor", "role_id": "00000000-0000-4000-8000-000000000001"},
    )
    assert blocked.status_code == 422


def test_password_change_keeps_this_token_and_rejects_the_old_one(client):
    headers = _login(client)
    wrong = client.post(
        "/api/v1/auth/me/password",
        headers=headers,
        json={"current_password": "not-the-password", "password": "another-password"},
    )
    assert wrong.status_code == 400

    changed = client.post(
        "/api/v1/auth/me/password",
        headers=headers,
        json={"current_password": "root-password-123", "password": "another-password"},
    )
    assert changed.status_code == 200, changed.text
    fresh = changed.json()["access_token"]
    assert fresh
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {fresh}"}).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401

    old = client.post(
        "/api/v1/auth/login-password",
        json={"username": "admin", "password": "root-password-123"},
    )
    assert old.status_code == 401
    new = client.post(
        "/api/v1/auth/login-password",
        json={"username": "admin", "password": "another-password"},
    )
    assert new.status_code == 200
