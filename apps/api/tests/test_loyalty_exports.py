import csv
import io
import uuid
import zipfile
from collections import defaultdict
from datetime import UTC, datetime
from xml.etree import ElementTree as ET

from app.models.customer import Customer
from test_foundations import set_tax, taxed_line, taxed_sale
from wholesale_support import CABLE, admin, event, line, push, sale, seed


def test_points_earn_redeem_and_reverse(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    rules = client.put(
        "/api/v1/loyalty/settings",
        headers=headers,
        json={"enabled": True, "earn_per_unit": 2, "redeem_cents": 1, "min_redeem": 50},
    )
    assert rules.status_code == 200, rules.text
    customer = client.post("/api/v1/customers", headers=headers, json={"name": "Sara"}).json()

    first = sale([line(CABLE, 4, 1500)], customer_id=customer["id"], sale_type="RETAIL")
    assert push(client, [event("loyalty-earn-sale", "sale", first)]).status_code == 200
    assert client.get(f"/api/v1/customers/{customer['id']}", headers=headers).json()["loyalty_points"] == 120

    greedy = sale(
        [line(CABLE, 1, 1500)],
        customer_id=customer["id"],
        sale_type="RETAIL",
        payment_method="cash",
        loyalty_points_redeemed=200,
        tenders=[{"method": "loyalty", "amount_cents": 200}, {"method": "cash", "amount_cents": 1300}],
    )
    assert push(client, [event("loyalty-greedy-sale", "sale", greedy)]).status_code == 422

    spend = sale(
        [line(CABLE, 1, 1500)],
        customer_id=customer["id"],
        sale_type="RETAIL",
        payment_method="cash",
        loyalty_points_redeemed=100,
        tenders=[{"method": "loyalty", "amount_cents": 100}, {"method": "cash", "amount_cents": 1400}],
    )
    response = push(client, [event("loyalty-spend-sale", "sale", spend)])
    assert response.status_code == 200, response.text
    # 120 earned, 100 spent, then 2 points per unit on the 14.00 paid in cash.
    ledger = client.get(f"/api/v1/loyalty/customers/{customer['id']}", headers=headers).json()
    assert sorted(row["entry_type"] for row in ledger) == ["EARN", "EARN", "REDEEM"]
    stored = session.get(Customer, uuid.UUID(customer["id"]))
    session.refresh(stored)
    assert stored.loyalty_points == 120 - 100 + 28


def test_tiers_raise_the_earn_rate_and_old_points_lapse(client, session) -> None:
    from datetime import timedelta

    from app.core.config import get_settings
    from app.jobs.runner import run_job
    from app.models.loyalty import LoyaltyEntry

    seed(client)
    headers, _ = admin(client)
    tiers = [
        {"name": "Silver", "min_spend_cents": 5000, "multiplier_pct": 150},
        {"name": "Gold", "min_spend_cents": 50000, "multiplier_pct": 200},
    ]
    unordered = client.put(
        "/api/v1/loyalty/settings",
        headers=headers,
        json={"enabled": True, "earn_per_unit": 1, "redeem_cents": 1, "min_redeem": 50, "tiers": tiers[::-1]},
    )
    assert unordered.status_code == 422
    rules = {"enabled": True, "earn_per_unit": 1, "redeem_cents": 1, "min_redeem": 50, "expiry_months": 12}
    assert client.put("/api/v1/loyalty/settings", headers=headers, json={**rules, "tiers": tiers}).status_code == 200
    customer = client.post("/api/v1/customers", headers=headers, json={"name": "Sara"}).json()

    # 60.00 paid crosses Silver on this very sale: 60 points x 1.5.
    first = sale([line(CABLE, 4, 1500)], customer_id=customer["id"], sale_type="RETAIL")
    assert push(client, [event("tier-sale", "sale", first)]).status_code == 200
    standing = client.get(f"/api/v1/loyalty/customers/{customer['id']}/standing", headers=headers).json()
    assert (standing["points"], standing["tier"], standing["next_tier"]) == (90, "Silver", "Gold")
    assert standing["next_tier_gap_cents"] == 50000 - 6000

    entry = session.query(LoyaltyEntry).filter(LoyaltyEntry.customer_id == uuid.UUID(customer["id"])).one()
    entry.created_at = datetime.now(UTC) - timedelta(days=400)
    session.commit()
    assert (
        client.get(f"/api/v1/loyalty/customers/{customer['id']}/standing", headers=headers).json()["expiring_soon"]
        == 90
    )
    assert run_job(session, get_settings(), "loyalty_expiry") == "ok"
    stored = session.get(Customer, uuid.UUID(customer["id"]))
    session.refresh(stored)
    assert stored.loyalty_points == 0
    lapsed = session.query(LoyaltyEntry).filter(LoyaltyEntry.entry_type == "EXPIRE").one()
    assert lapsed.points == -90


def test_gl_journal_balances_and_pint_ae_is_well_formed(client) -> None:
    seed(client)
    headers, _ = admin(client)
    set_tax(client, headers)
    customer = client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Ali", "company_name": "Ali LLC", "trn_vat_number": "100200300400003"},
    ).json()
    body = taxed_sale([taxed_line(10_000, 1, inclusive=False)], customer_id=customer["id"], sale_type="RETAIL")
    assert push(client, [event("export-sale-key", "sale", body)]).status_code == 200

    today = datetime.now(UTC).date().isoformat()
    # wholesale_support stamps every sync event 2026-10-19, which becomes the sale date.
    period = {"from": "2026-10-19", "to": today}
    exported = client.get("/api/v1/exports/gl.csv", headers=headers, params=period)
    assert exported.status_code == 200
    rows = list(csv.DictReader(io.StringIO(exported.text)))
    balance: dict[str, float] = defaultdict(float)
    for row in rows:
        balance[row["reference"]] += float(row["debit"] or 0) - float(row["credit"] or 0)
    assert rows and all(abs(value) < 0.001 for value in balance.values())
    assert {"4000", "2100"} <= {row["account"] for row in rows}

    xml = client.get(f"/api/v1/exports/einvoices/{body['id']}.xml", headers=headers)
    assert xml.status_code == 200
    root = ET.fromstring(xml.content)
    ns = {
        "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
        "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    }
    assert root.find("cbc:CustomizationID", ns).text == "urn:peppol:pint:billing-1@ae-1"
    assert root.find("cbc:InvoiceTypeCode", ns).text == "380"
    assert root.find("cac:TaxTotal/cbc:TaxAmount", ns).text == "5.00"
    assert root.find("cac:AccountingCustomerParty/cac:Party/cbc:EndpointID", ns).text == "100200300400003"

    bundle = client.get("/api/v1/exports/einvoices.zip", headers=headers, params=period)
    assert len(zipfile.ZipFile(io.BytesIO(bundle.content)).namelist()) == 1

    mapped = client.put(
        "/api/v1/exports/accounts",
        headers=headers,
        json={"accounts": {"revenue": {"code": "41000", "name": "Retail sales"}, "vat": {"code": "", "name": ""}}},
    )
    assert mapped.status_code == 200, mapped.text
    revenue = next(row for row in mapped.json() if row["key"] == "revenue")
    assert (revenue["code"], revenue["default_code"]) == ("41000", "4000")
    remapped = client.get("/api/v1/exports/gl.csv", headers=headers, params=period)
    accounts = {row["account"]: row["account_name"] for row in csv.DictReader(io.StringIO(remapped.text))}
    assert accounts.get("41000") == "Retail sales" and "4000" not in accounts and "2100" in accounts
    bad = client.put("/api/v1/exports/accounts", headers=headers, json={"accounts": {"nope": {"code": "1"}}})
    assert bad.status_code == 422
