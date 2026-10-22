"""A retail profile keeps birthday, sizes and notes, and the till can read recent purchases."""

from wholesale_support import admin, seed


def test_profile_fields_and_empty_history(client):
    seed(client)
    headers, _ = admin(client)
    created = client.post(
        "/api/v1/customers",
        headers=headers,
        json={
            "name": "Lina Noor",
            "customer_type": "RETAIL",
            "phone": "0501112233",
            "birthday": "1992-10-21",
            "gender": "women",
            "preferred_sizes": {"tops": "M", "bottoms": "32"},
            "notes": "Prefers navy",
            "tags": ["vip"],
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["birthday"] == "1992-10-21"
    assert body["preferred_sizes"] == {"tops": "M", "bottoms": "32"}
    assert body["notes"] == "Prefers navy"
    assert body["tags"] == ["vip"]
    history = client.get(f"/api/v1/customers/{body['id']}/history", headers=headers)
    assert history.status_code == 200, history.text
    assert history.json() == []
