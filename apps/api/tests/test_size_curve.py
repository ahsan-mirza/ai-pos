"""The size-curve report lists every size of a model with sell-through shares."""

from datetime import UTC, datetime, timedelta

from tests.test_fashion import tee_model
from tests.test_returns import admin_token, bearer, seed_catalog


def test_size_curve_lists_the_grid(client):
    seed_catalog(client)
    token = admin_token(client)
    model_id = tee_model(client, token)
    created = client.post(
        f"/api/v1/product-models/{model_id}/matrix",
        headers=bearer(token),
        json={
            "axes": [{"key": "size", "values": ["S", "M"]}, {"key": "color", "values": ["Black", "White"]}],
            "price_cents": 4900,
        },
    )
    assert created.status_code == 200, created.text
    start = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
    end = datetime.now(UTC).date().isoformat()
    report = client.get(
        f"/api/v1/reports/size-curve?model_id={model_id}&from={start}&to={end}",
        headers=bearer(token),
    )
    assert report.status_code == 200, report.text
    cells = report.json()["cells"]
    assert len(cells) == 4
    assert {cell["size"] for cell in cells} == {"S", "M"}
    assert report.json()["broken_runs"] == []
