"""Markdown events drop the retail price, remember the was price, and restore it when they end."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from tests.test_returns import admin_token, bearer

from app.models import PriceChange, Product
from wholesale_support import CABLE, seed


def _window(start_delta: timedelta, days: int = 7) -> dict[str, str]:
    start = datetime.now(UTC) + start_delta
    return {"starts_at": start.isoformat(), "ends_at": (start + timedelta(days=days)).isoformat()}


def test_markdown_applies_and_restores(client, session):
    seed(client)
    token = admin_token(client)
    created = client.post(
        "/api/v1/markdowns",
        headers=bearer(token),
        json={
            "name": "Cable sale",
            "scope": {"product_ids": [CABLE]},
            "percent_bps": 2000,
            "final_sale": True,
            **_window(timedelta(minutes=-1)),
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["status"] == "ACTIVE"
    assert body["applied_count"] == 1

    session.expire_all()
    product = session.get(Product, uuid.UUID(CABLE))
    assert product is not None
    assert product.price_cents == 1200
    assert product.compare_at_cents == 1500
    assert product.is_final_sale is True
    assert session.scalar(select(PriceChange).where(PriceChange.product_id == product.id)) is not None

    again = client.post(
        "/api/v1/markdowns",
        headers=bearer(token),
        json={
            "name": "Second cut",
            "scope": {"product_ids": [CABLE]},
            "percent_bps": 1000,
            **_window(timedelta(minutes=-1)),
        },
    )
    assert again.status_code == 200, again.text
    assert again.json()["applied_count"] == 0
    assert again.json()["skipped_count"] == 1

    ended = client.post(f"/api/v1/markdowns/{body['id']}/end", headers=bearer(token))
    assert ended.status_code == 200, ended.text
    session.expire_all()
    assert product.price_cents == 1500
    assert product.compare_at_cents is None
    assert product.is_final_sale is False


def test_future_markdown_stays_scheduled(client, session):
    seed(client)
    token = admin_token(client)
    created = client.post(
        "/api/v1/markdowns",
        headers=bearer(token),
        json={
            "name": "Next week",
            "scope": {"product_ids": [CABLE]},
            "price_cents": 900,
            **_window(timedelta(days=3)),
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["status"] == "SCHEDULED"
    session.expire_all()
    product = session.get(Product, uuid.UUID(CABLE))
    assert product is not None
    assert product.price_cents == 1500
