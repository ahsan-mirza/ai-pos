from datetime import UTC, datetime, timedelta

from test_foundations import set_tax, taxed_line, taxed_sale
from wholesale_support import STORE, admin, event, push, seed


def test_vat_return_groups_standard_supplies_by_emirate(client) -> None:
    seed(client)
    headers, _ = admin(client)
    set_tax(client, headers)
    assert client.patch(f"/api/v1/stores/{STORE}", headers=headers, json={"emirate": "SHJ"}).status_code == 200
    body = taxed_sale([taxed_line(10_000, 2, inclusive=False)], sold_at=datetime.now(UTC).isoformat())
    assert push(client, [event("vat-report-sale", "sale", body)]).status_code == 200

    today = datetime.now(UTC).date()
    params = {"from": str(today - timedelta(days=1)), "to": str(today)}
    report = client.get("/api/v1/reports/vat", headers=headers, params=params)
    assert report.status_code == 200, report.text
    data = report.json()
    sharjah = next(row for row in data["emirates"] if row["emirate"] == "SHJ")
    assert (sharjah["amount_cents"], sharjah["vat_cents"]) == (20_000, 1_000)
    assert data["output_vat_cents"] == 1_000
    assert data["simplified_invoices"] == 1
    assert data["trn"] == "100123456700003"

    csv = client.get("/api/v1/reports/vat/export", headers=headers, params={**params, "format": "csv"})
    assert csv.status_code == 200
    assert "Sharjah" in csv.text and "200.00" in csv.text
    pdf = client.get("/api/v1/reports/vat/export", headers=headers, params={**params, "format": "pdf"})
    assert pdf.content.startswith(b"%PDF")


def test_vat_report_requires_permission(client) -> None:
    seed(client)
    today = datetime.now(UTC).date()
    response = client.get("/api/v1/reports/vat", params={"from": str(today), "to": str(today)})
    assert response.status_code == 401
