import uuid

import jwt
import pytest

from app.core.config import get_settings
from app.core.deps import _user_from_token
from app.core.errors import ApiError
from app.core.security import create_access_token
from app.models.customer import Customer
from app.tenancy.context import TenantRef, use_tenant
from wholesale_support import CABLE, CASHIER_ID, admin, device, event, line, push, sale, seed


def _quick_add(**overrides) -> dict:
    body = {
        "id": str(uuid.uuid4()),
        "created_by_id": CASHIER_ID,
        "name": "Walk-in 0557526684",
        "phone": "0557526684",
        "customer_type": "RETAIL",
    }
    body.update(overrides)
    return body


def test_register_adds_a_customer_offline_and_sells_to_it_in_the_same_batch(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    customer = _quick_add()
    order = sale([line(CABLE, 1, 1500)], customer_id=customer["id"])
    pushed = push(
        client, [event("quick-add-customer-1", "customer", customer), event("quick-add-sale-1", "sale", order)]
    )
    assert pushed.status_code == 200, pushed.text
    assert [row["status"] for row in pushed.json()["results"]] == ["applied", "applied"]

    stored = session.get(Customer, uuid.UUID(customer["id"]))
    assert stored.phone == "0557526684" and stored.code.startswith("WALK-")
    listed = client.get("/api/v1/customers/sync", headers=device()).json()
    assert customer["id"] in {row["id"] for row in listed}

    replay = push(client, [event("quick-add-customer-2", "customer", {**customer, "name": "Renamed at till"})])
    assert replay.status_code == 200
    session.refresh(stored)
    assert stored.name == "Walk-in 0557526684"
    assert client.get(f"/api/v1/customers/{customer['id']}", headers=headers).status_code == 200


def test_cashier_cannot_grant_credit_terms_from_the_register(client, session) -> None:
    seed(client)
    wholesale = _quick_add(
        name="Ahmed Saleh",
        phone=None,
        customer_type="WHOLESALE",
        company_name="Saleh Mobiles LLC",
        trn_vat_number="100200300400003",
        price_tier="TIER_2",
        credit_limit_cents=500_000,
        payment_terms="NET_30",
    )
    assert push(client, [event("quick-add-b2b-1", "customer", wholesale)]).status_code == 200
    stored = session.get(Customer, uuid.UUID(wholesale["id"]))
    assert stored.customer_type == "WHOLESALE" and stored.company_name == "Saleh Mobiles LLC"
    assert (stored.price_tier, stored.credit_limit_cents, stored.payment_terms) == ("RETAIL", 0, "DUE_ON_RECEIPT")


def test_unknown_cashier_is_rejected(client) -> None:
    seed(client)
    result = push(client, [event("quick-add-ghost-1", "customer", _quick_add(created_by_id=str(uuid.uuid4())))])
    assert result.status_code == 422 and result.json()["error"]["code"] == "sync_rejected"


def test_access_tokens_are_bound_to_their_store(client) -> None:
    seed(client)
    headers, _ = admin(client)
    token = headers["Authorization"].split()[1]
    assert "tid" not in jwt.decode(token, options={"verify_signature": False})
    other = TenantRef(id="tenant-b", slug="b", name="Store B", database_url="sqlite://")
    with use_tenant(other), pytest.raises(ApiError) as refused:
        _user_from_token(token, None, get_settings())  # type: ignore[arg-type]
    assert refused.value.status_code == 401 and "another store" in refused.value.message
    issued, _ = create_access_token(
        subject=str(uuid.uuid4()), scope="portal", token_version=0, settings=get_settings(), tenant_id="tenant-b"
    )
    assert jwt.decode(issued, options={"verify_signature": False})["tid"] == "tenant-b"
