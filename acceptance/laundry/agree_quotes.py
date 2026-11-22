"""Compare catalog quotes on the disposable API with the browser results."""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
os.chdir(ROOT / "apps" / "api")

BASE = "http://127.0.0.1:18082"


def login(client: httpx.Client, domain: str) -> str:
    from app.core.config import get_settings

    settings = get_settings()
    response = client.post(
        "/api/v1/auth/login-password",
        json={"username": settings.admin_username, "password": settings.admin_password},
        headers={"X-Tenant-Domain": domain},
    )
    response.raise_for_status()
    return response.json()["access_token"]


def main() -> None:
    report: dict = {}
    with httpx.Client(base_url=BASE, timeout=30) as client:
        token = login(client, "laundry-a")
        headers = {"Authorization": f"Bearer {token}", "X-Tenant-Domain": "laundry-a"}
        services = {row["name"]: row for row in client.get("/api/v1/laundry/services", headers=headers).json()}
        lists = {row["name"]: row for row in client.get("/api/v1/laundry/price-lists", headers=headers).json()}
        stores = {row["name"]: row for row in client.get("/api/v1/stores", headers=headers).json()}
        customers = {row["name"]: row for row in client.get("/api/v1/customers?limit=100", headers=headers).json()}
        shirt = services["Dry clean shirt"]["id"]
        fold = services["Wash and fold"]["id"]
        today = date.today().isoformat()

        def quote(service_id: str, **extra: object) -> httpx.Response:
            body = {"service_id": service_id, "quantity": 1, "on": today}
            body.update(extra)
            return client.post("/api/v1/laundry/quotes", json=body, headers=headers)

        def money(response: httpx.Response) -> dict:
            if response.status_code >= 400:
                return {"status": response.status_code, "code": response.json()["error"]["code"]}
            body = response.json()
            return {
                "status": response.status_code,
                "total_cents": body["total_cents"],
                "tax_cents": body["tax_cents"],
                "rate_bps": body["rate_bps"],
                "minimum_charge_applied": body["minimum_charge_applied"],
            }

        report["piece_one"] = money(quote(shirt, quantity=1))
        report["piece_extras"] = money(quote(shirt, quantity=2, extras_cents=100, discount_cents=50, express=True))
        report["counter"] = money(quote(shirt, quantity=2, price_list_id=lists["Counter"]["id"]))
        report["branch_a"] = money(
            quote(
                shirt,
                quantity=1,
                price_list_id=lists["Branch A shirts"]["id"],
                store_id=stores["Branch A"]["id"],
            )
        )
        report["wrong_branch"] = money(
            quote(
                shirt,
                quantity=1,
                price_list_id=lists["Branch B shirts"]["id"],
                store_id=stores["Branch A"]["id"],
            )
        )
        report["hotel"] = money(
            quote(
                shirt,
                quantity=1,
                price_list_id=lists["Hotel shirts"]["id"],
                customer_id=customers["Hotel Account"]["id"],
            )
        )
        report["wrong_customer"] = money(
            quote(
                shirt,
                quantity=1,
                price_list_id=lists["Hotel shirts"]["id"],
                customer_id=customers["Walk-in Customer"]["id"],
            )
        )
        report["expired"] = money(quote(shirt, quantity=1, price_list_id=lists["Expired shirts"]["id"]))
        report["branch_b_express"] = money(
            quote(
                shirt,
                quantity=1,
                price_list_id=lists["Branch B shirts"]["id"],
                store_id=stores["Branch B"]["id"],
                express=True,
            )
        )
        report["kg_net"] = money(quote(fold, quantity=2250))
        report["kg_minimum"] = money(quote(fold, quantity=750))
        created = client.post(
            "/api/v1/laundry/price-lists",
            json={
                "code": "future_shirts",
                "name": "Future shirts",
                "kind": "standard",
                "valid_from": (date.today() + timedelta(days=1)).isoformat(),
            },
            headers=headers,
        )
        created.raise_for_status()
        future = created.json()
        rated = client.put(
            f"/api/v1/laundry/price-lists/{future['id']}/rates",
            json={"service_id": shirt, "unit_price_cents": 500},
            headers=headers,
        )
        rated.raise_for_status()
        report["future"] = money(quote(shirt, quantity=1, price_list_id=future["id"]))
        empty = client.post(
            "/api/v1/laundry/price-lists",
            json={"code": "unpriced", "name": "Unpriced", "kind": "standard"},
            headers=headers,
        )
        empty.raise_for_status()
        report["missing_rate"] = money(quote(shirt, quantity=1, price_list_id=empty.json()["id"]))
        grocery = login(client, "grocery-b")
        grocery_headers = {"Authorization": f"Bearer {grocery}", "X-Tenant-Domain": "grocery-b"}
        foreign = client.get("/api/v1/laundry/services", headers=grocery_headers)
        report["grocery_catalog"] = {"status": foreign.status_code}
        if foreign.status_code < 400:
            report["grocery_catalog"]["count"] = len(foreign.json())

    expected = {
        "piece_one": {"total_cents": 1050, "tax_cents": 50, "rate_bps": 500},
        "piece_extras": {"total_cents": 2415, "tax_cents": 115, "rate_bps": 500},
        "counter": {"total_cents": 3150, "tax_cents": 150, "rate_bps": 500},
        "branch_a": {"total_cents": 1890, "tax_cents": 90, "rate_bps": 500},
        "hotel": {"total_cents": 1260, "tax_cents": 60, "rate_bps": 500},
        "kg_net": {"total_cents": 2363, "tax_cents": 113, "rate_bps": 500, "minimum_charge_applied": False},
        "kg_minimum": {"total_cents": 2100, "tax_cents": 100, "rate_bps": 500, "minimum_charge_applied": True},
    }
    mismatches = {
        name: report[name]
        for name, want in expected.items()
        if any(report[name].get(key) != value for key, value in want.items())
    }
    codes = {
        name: report[name].get("code")
        for name in ("wrong_branch", "wrong_customer", "expired", "future", "missing_rate", "branch_b_express")
    }
    report["matches_browser"] = mismatches == {}
    report["restriction_codes"] = codes
    report["result"] = (
        "PASSED"
        if mismatches == {}
        and codes == {
            "wrong_branch": "expired_price_list",
            "wrong_customer": "expired_price_list",
            "expired": "expired_price_list",
            "future": "expired_price_list",
            "missing_rate": "missing_rate",
            "branch_b_express": "express_capacity",
        }
        and report["grocery_catalog"]["status"] in {403, 200}
        and report["grocery_catalog"].get("count", 0) == 0
        else "FAILED"
    )
    out = Path(__file__).resolve().parent / "evidence" / "quotes.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"result": report["result"], "mismatches": mismatches, "codes": codes, "grocery": report["grocery_catalog"]}))
    if report["result"] != "PASSED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
