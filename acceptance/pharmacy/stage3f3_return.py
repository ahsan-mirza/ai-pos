"""Seed and check the portal customer return through the real API.

Stock changes go through the purchase, sale, return, recall, and supplier-return
endpoints. This does not write quantities with SQL.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from urllib.error import HTTPError
from urllib.request import Request, urlopen

from exercise import Api, _login

EVIDENCE = Path(__file__).resolve().parent / "evidence" / "stage-3f.3"
STORE = "11111111-1111-4111-8111-111111111111"
MANAGER = "00000000-0000-4000-8000-0000000000a2"
CASHIER = "00000000-0000-4000-8000-0000000000a3"
EXPIRY = str((datetime.now(UTC) + timedelta(days=120)).date())


def main() -> None:
    phase = os.environ.get("ACCEPTANCE_PHASE", "seed")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if phase == "seed":
        seed()
    elif phase == "verify":
        verify()
    else:
        raise SystemExit(f"Unknown phase {phase}")


def seed() -> None:
    base = os.environ["ACCEPTANCE_API_URL"]
    admin_password = os.environ["ACCEPTANCE_ADMIN_PASSWORD"]
    staff_password = os.environ["ACCEPTANCE_STAFF_PASSWORD"]
    api = Api(base, "pharmacy-accept")
    _login(api, "admin", admin_password)
    results: list[dict] = []
    status, profile = api(
        "PUT",
        "/api/v1/settings/profile",
        {"business_profile": "pharmacy", "capabilities": None, "complete_onboarding": True},
    )
    record(results, "pharmacy-profile", status == 200 and "pharmacy_catalog" in set(profile.get("capabilities") or []))
    now = datetime.now(UTC).isoformat()
    api(
        "POST",
        "/api/v1/sync/push",
        {
            "device_id": "acceptance-bootstrap",
            "events": [
                {
                    "idempotency_key": "store-3f3",
                    "entity_type": "store",
                    "operation": "upsert",
                    "payload": {
                        "id": STORE,
                        "code": "P3F3",
                        "name": "Stage 3F.3 Pharmacy",
                        "currency": "USD",
                        "is_warehouse": True,
                    },
                    "occurred_at": now,
                }
            ],
        },
        auth="shared",
    )
    _, role = api(
        "POST",
        "/api/v1/roles",
        {
            "name": "Stage 3F.3 clerk",
            "description": "Nominates governance officers",
            "permissions": ["roles:manage", "portal:access", "users:read"],
        },
    )

    def user(username: str, name: str, role_id: str) -> str:
        _, created = api(
            "POST",
            "/api/v1/users",
            {
                "username": username,
                "email": f"{username}@acceptance.example",
                "full_name": name,
                "role_id": role_id,
                "store_id": STORE,
                "password": staff_password,
                "pin": "1357",
                "has_portal_access": True,
                "has_pos_access": True,
            },
        )
        return created["id"]

    clerk_a = user("clerk.a", "Clerk A", role["id"])
    clerk_b = user("clerk.b", "Clerk B", role["id"])
    officer_1 = user("officer.one", "Governance Officer 1", MANAGER)
    officer_2 = user("officer.two", "Governance Officer 2", MANAGER)
    pharmacist = user("pharmacist.one", "Pharmacist One", MANAGER)
    cashier = user("cashier.one", "Cashier One", CASHIER)
    appoint(base, staff_password, clerk_a, clerk_b, officer_1, officer_2, pharmacist)
    _, categories = api("GET", "/api/v1/categories")
    category_id = next(row["id"] for row in categories if row.get("code") == "OTC")
    _, device = api("POST", "/api/v1/devices", {"store_id": STORE, "code": "P3F3", "name": "Stage 3F.3 register"})
    api.device_key = device["key"]
    cases = {
        "valid": prepare_medicine(api, category_id, "Stage 3F.3 Return", "3F3-RET", "6291000003101", "LOT-RET", 4, pharmacist, base, staff_password),
        "excess": prepare_medicine(api, category_id, "Stage 3F.3 Excess", "3F3-EXCESS", "6291000003102", "LOT-EXCESS", 2, pharmacist, base, staff_password),
        "recalled": prepare_medicine(api, category_id, "Stage 3F.3 Recalled", "3F3-RECALL", "6291000003103", "LOT-RECALL", 4, pharmacist, base, staff_password),
        "supplier": prepare_medicine(api, category_id, "Stage 3F.3 Supplier", "3F3-SUP", "6291000003104", "LOT-SUP", 2, pharmacist, base, staff_password),
    }
    sales = {}
    for key, prepared in cases.items():
        sales[key] = sell(api, cashier, prepared["product_id"], 1)
        sales[key]["product_id"] = prepared["product_id"]
    runtime = Path(__file__).resolve().parent / ".env.stage3f3.device"
    runtime.write_text(device["key"], encoding="utf-8")
    recall(api, cases["recalled"])
    supplier_return_rest(api, cases["supplier"])
    cashier_api = Api(base, "pharmacy-accept")
    cashier_api.device_key = api.device_key
    pin_status, pin_body = cashier_api(
        "POST",
        "/api/v1/auth/login-pin",
        {"username": "cashier.one", "pin": "1357"},
        auth="device",
        ok=(200, 403),
    )
    if pin_status != 200 or not isinstance(pin_body, dict) or not pin_body.get("access_token"):
        raise RuntimeError(f"Cashier register sign-in failed: {pin_status}")
    cashier_api.token = pin_body["access_token"]
    denied, _ = cashier_api(
        "POST",
        f"/api/v1/pharmacy/lots/{cases['valid']['lot_id']}/release",
        {"reason": "Cashier tries to release", "confirm": True},
        ok=(403, 422),
    )
    record(results, "cashier-cannot-release", denied == 403)
    grocery = seed_grocery(base, admin_password, staff_password)
    payload = {"pharmacy": sales, "lots": {key: value["lot_id"] for key, value in cases.items()}, "grocery": grocery}
    (EVIDENCE / "invoices.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (EVIDENCE / "api-seed.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({"invoices": {key: value["invoice"] for key, value in sales.items()}, "grocery": grocery["invoice"]}))


def appoint(base: str, password: str, clerk_a: str, clerk_b: str, officer_1: str, officer_2: str, pharmacist: str) -> None:
    del clerk_a, clerk_b
    first = Api(base, "pharmacy-accept")
    second = Api(base, "pharmacy-accept")
    _login(first, "clerk.a", password)
    _login(second, "clerk.b", password)
    first(
        "POST",
        "/api/v1/pharmacy/governance-officers",
        {"user_id": officer_1, "reason": "Nominate the first governance officer", "confirm": True},
    )
    second(
        "POST",
        f"/api/v1/pharmacy/governance-officers/{officer_1}/confirm",
        {"reason": "Confirm the first governance officer", "confirm": True},
    )
    second(
        "POST",
        "/api/v1/pharmacy/governance-officers",
        {"user_id": officer_2, "reason": "Nominate the second governance officer", "confirm": True},
    )
    first(
        "POST",
        f"/api/v1/pharmacy/governance-officers/{officer_2}/confirm",
        {"reason": "Confirm the second governance officer", "confirm": True},
    )
    one = Api(base, "pharmacy-accept")
    two = Api(base, "pharmacy-accept")
    _login(one, "officer.one", password)
    _login(two, "officer.two", password)
    one(
        "POST",
        "/api/v1/pharmacy/pharmacists",
        {"user_id": pharmacist, "reason": "Request pharmacist appointment", "confirm": True},
    )
    denied, _ = one(
        "POST",
        f"/api/v1/pharmacy/pharmacists/{pharmacist}/approve",
        {"reason": "Requester tries to approve", "confirm": True},
        ok=(403, 422),
    )
    if denied not in {403, 422}:
        raise RuntimeError(f"Requester approval was not refused: {denied}")
    two(
        "POST",
        f"/api/v1/pharmacy/pharmacists/{pharmacist}/approve",
        {"reason": "Approve pharmacist appointment", "confirm": True},
    )


def prepare_medicine(api: Api, category_id: str, name: str, sku: str, barcode: str, lot: str, quantity: int, pharmacist: str, base: str, password: str) -> dict:
    _, created = api(
        "POST",
        "/api/v1/inventory/products",
        {
            "sku": sku,
            "barcode": barcode,
            "brand": "Stage 3F.3 Pharma",
            "name": name,
            "price_cents": 1500,
            "category_id": category_id,
            "pharmacy": {
                "product_kind": "MEDICINE",
                "dispensing_class": "OTC",
                "generic_name": name,
                "manufacturer": "Stage 3F.3",
                "dosage_form": "tablet",
                "route": "oral",
                "strength_amount": "500",
                "strength_unit": "mg",
                "pack_size_label": "1 tablet",
                "units_per_pack": 1,
                "base_unit_code": "PIECE",
                "selling_unit_code": "PIECE",
                "price_control": "NONE",
                "ingredients": [{"name": name, "strength_amount": "500", "strength_unit": "mg", "is_active_ingredient": True}],
            },
        },
    )
    _, order = api(
        "POST",
        "/api/v1/inventory/purchase-orders",
        {
            "supplier_name": "Stage 3F.3 Pharma",
            "destination_store_id": STORE,
            "notes": lot,
            "lines": [{"product_id": created["id"], "quantity_ordered": quantity, "unit_cost_cents": 400}],
        },
    )
    api("POST", f"/api/v1/inventory/purchase-orders/{order['id']}/order")
    _, received = api(
        "POST",
        f"/api/v1/inventory/purchase-orders/{order['id']}/receive",
        {
            "note": lot,
            "lines": [
                {
                    "purchase_order_line_id": order["lines"][0]["id"],
                    "quantity": quantity,
                    "manufacturer_lot": lot,
                    "expiry_date": EXPIRY,
                }
            ],
        },
    )
    lot_id = next(item["batch_item_id"] for item in received["receipts"][-1]["lots"] if item.get("manufacturer_lot") == lot)
    releaser = Api(base, "pharmacy-accept")
    _login(releaser, "pharmacist.one", password)
    releaser("POST", f"/api/v1/pharmacy/lots/{lot_id}/release", {"reason": f"Release {lot}", "confirm": True})
    return {"product_id": created["id"], "lot_id": str(lot_id), "pharmacist": pharmacist}


def line_amounts(api: Api, quantity: int) -> dict[str, int]:
    _, settings = api("GET", "/api/v1/settings")
    rate = int(settings.get("standard_rate_bps") or 0) if settings.get("vat_registered") else 0
    gross = 1500 * quantity
    tax = (gross * rate + 5_000) // 10_000 if rate else 0
    return {"subtotal_cents": gross, "tax_cents": tax, "line_total_cents": gross + tax, "total_cents": gross + tax}


def sell(api: Api, cashier_id: str, product_id: str, quantity: int) -> dict:
    sale_id = str(uuid.uuid4())
    money = line_amounts(api, quantity)
    status, body = api(
        "POST",
        "/api/v1/sync/push",
        {
            "device_id": "P3F3",
            "events": [
                {
                    "idempotency_key": str(uuid.uuid4()),
                    "entity_type": "sale",
                    "operation": "upsert",
                    "payload": {
                        "id": sale_id,
                        "store_id": STORE,
                        "cashier_id": cashier_id,
                        "currency": "USD",
                        "payment_method": "cash",
                        "subtotal_cents": money["subtotal_cents"],
                        "tax_cents": money["tax_cents"],
                        "total_cents": money["total_cents"],
                        "client_sale_id": str(uuid.uuid4()),
                        "items": [
                            {
                                "id": str(uuid.uuid4()),
                                "product_id": product_id,
                                "quantity": quantity,
                                "unit_price_cents": 1500,
                                "tax_cents": money["tax_cents"],
                                "line_total_cents": money["line_total_cents"],
                            }
                        ],
                    },
                    "occurred_at": datetime.now(UTC).isoformat(),
                }
            ],
        },
        auth="device",
    )
    applied = status == 200 and isinstance(body, dict) and any(row.get("status") == "applied" for row in body.get("results") or [])
    invoice = (find_invoice(body, sale_id) or invoice_from_insights(api, sale_id)) if applied else ""
    if not applied or not invoice:
        raise RuntimeError(f"Sale was not accepted: {status} {str(body)[:800]}")
    return {"sale_id": sale_id, "invoice": invoice}


def find_invoice(body: object, sale_id: str) -> str:
    if isinstance(body, dict):
        for event in body.get("results") or body.get("events") or []:
            payload = event.get("payload") or event.get("result") or event
            if isinstance(payload, dict) and str(payload.get("id") or "") == sale_id:
                number = payload.get("invoice_number")
                if number:
                    return str(number)
        number = body.get("invoice_number")
        if number:
            return str(number)
    return ""


def invoice_from_insights(api: Api, sale_id: str) -> str:
    _, rows = api("GET", "/api/v1/sales-insights/transactions?limit=50")
    if not isinstance(rows, list):
        return ""
    for row in rows:
        if str(row.get("id")) == sale_id and row.get("invoice_number"):
            return str(row["invoice_number"])
    return ""


def post_return(api: Api, body: dict) -> tuple[int, object]:
    headers = {
        "X-Tenant-Domain": api.tenant,
        "Content-Type": "application/json",
        "X-Client-Device": "web",
        "Authorization": f"Bearer {api.token}",
        "Idempotency-Key": str(uuid.uuid4()),
    }
    request = Request(api.base + "/api/v1/returns", data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urlopen(request, timeout=60) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else None
    except HTTPError as error:
        raw = error.read().decode()
        if error.code not in {200, 201, 409, 422}:
            raise RuntimeError(f"POST /api/v1/returns -> {error.code} {raw[:800]}") from error
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = {"raw": raw[:400]}
        return error.code, parsed


def recall(api: Api, prepared: dict) -> None:
    api(
        "POST",
        "/api/v1/pharmacy/recalls",
        {
            "reference": "3F3-RECALL",
            "source_text": "Stage 3F.3",
            "severity": "high",
            "reason": "Recall before the portal return",
            "lots": [{"product_id": prepared["product_id"], "manufacturer_lot": "LOT-RECALL"}],
        },
    )


def supplier_return_rest(api: Api, prepared: dict) -> None:
    api(
        "POST",
        "/api/v1/pharmacy/supplier-returns",
        {
            "reference": "3F3-SUP-1",
            "reason": "Return the unsold unit before the customer return",
            "lines": [{"batch_item_id": prepared["lot_id"], "quantity": 1}],
        },
    )


def seed_grocery(base: str, admin_password: str, staff_password: str) -> dict:
    del staff_password
    api = Api(base, "accept-grocery")
    _login(api, "admin", admin_password)
    api(
        "PUT",
        "/api/v1/settings/profile",
        {"business_profile": "grocery", "capabilities": None, "complete_onboarding": True},
    )
    _, settings = api("GET", "/api/v1/settings")
    if "pharmacy_catalog" in set(settings.get("capabilities") or []):
        raise RuntimeError("Grocery tenant gained the pharmacy catalogue.")
    store_id = str(uuid.uuid4())
    api(
        "POST",
        "/api/v1/sync/push",
        {
            "device_id": "grocery-bootstrap",
            "events": [
                {
                    "idempotency_key": f"store-{store_id}",
                    "entity_type": "store",
                    "operation": "upsert",
                    "payload": {"id": store_id, "code": "G3F3", "name": "Stage 3F.3 Grocery", "currency": "USD"},
                    "occurred_at": datetime.now(UTC).isoformat(),
                }
            ],
        },
        auth="shared",
    )
    _, categories = api("GET", "/api/v1/categories")
    category_id = categories[0]["id"]
    _, product = api(
        "POST",
        "/api/v1/inventory/products",
        {"sku": "3F3-GROC", "barcode": "6291000003199", "name": "Stage 3F.3 Rice", "price_cents": 1500, "category_id": category_id},
    )
    api(
        "POST",
        "/api/v1/inventory/adjust",
        {
            "adjustment_id": str(uuid.uuid4()),
            "product_id": product["id"],
            "store_id": store_id,
            "mode": "add",
            "quantity": 3,
            "reason_code": "SUPPLIER_SAMPLE_IN",
            "note": "3F3 grocery",
            "unit_cost_cents": 100,
        },
    )
    _, device = api("POST", "/api/v1/devices", {"store_id": store_id, "code": "G3F3", "name": "Grocery register"})
    api.device_key = device["key"]
    _, me = api("GET", "/api/v1/auth/me")
    sale_id = str(uuid.uuid4())
    money = line_amounts(api, 1)
    status, body = api(
        "POST",
        "/api/v1/sync/push",
        {
            "device_id": "G3F3",
            "events": [
                {
                    "idempotency_key": str(uuid.uuid4()),
                    "entity_type": "sale",
                    "operation": "upsert",
                    "payload": {
                        "id": sale_id,
                        "store_id": store_id,
                        "cashier_id": me["id"],
                        "currency": "USD",
                        "payment_method": "cash",
                        "subtotal_cents": money["subtotal_cents"],
                        "tax_cents": money["tax_cents"],
                        "total_cents": money["total_cents"],
                        "client_sale_id": str(uuid.uuid4()),
                        "items": [
                            {
                                "id": str(uuid.uuid4()),
                                "product_id": product["id"],
                                "quantity": 1,
                                "unit_price_cents": 1500,
                                "tax_cents": money["tax_cents"],
                                "line_total_cents": money["line_total_cents"],
                            }
                        ],
                    },
                    "occurred_at": datetime.now(UTC).isoformat(),
                }
            ],
        },
        auth="device",
    )
    applied = status == 200 and isinstance(body, dict) and any(row.get("status") == "applied" for row in body.get("results") or [])
    invoice = (find_invoice(body, sale_id) or invoice_from_insights(api, sale_id)) if applied else ""
    if not applied or not invoice:
        raise RuntimeError(f"Grocery sale was not accepted: {status} {str(body)[:800]}")
    return {"invoice": invoice, "product_id": product["id"], "store_id": store_id}


def verify() -> None:
    data = json.loads((EVIDENCE / "invoices.json").read_text(encoding="utf-8"))
    base = os.environ["ACCEPTANCE_API_URL"]
    api = Api(base, "pharmacy-accept")
    _login(api, "admin", os.environ["ACCEPTANCE_ADMIN_PASSWORD"])
    key_path = Path(__file__).resolve().parent / ".env.stage3f3.device"
    api.device_key = key_path.read_text(encoding="utf-8").strip()
    results: list[dict] = []
    valid = lot_row(api, data["lots"]["valid"])
    record(results, "portal-return-quarantine", valid.get("status") == "QUARANTINED" and valid.get("remaining") == 4)
    resale, resale_body = sell_expect(api, data, "valid")
    reason = ""
    if isinstance(resale_body, dict):
        reason = ((resale_body.get("error") or {}).get("details") or {}).get("reason") or ""
    record(results, "quarantine-blocks-resale", resale == 422 and reason == "lot_quarantined")
    excess = excess_return(api, data["pharmacy"]["excess"]["invoice"])
    excess_lot = lot_row(api, data["lots"]["excess"])
    record(
        results,
        "excess-return-rejected",
        excess["status"] in {409, 422}
        and excess["returns_after"] == excess["returns_before"]
        and excess_lot.get("status") == "RELEASED"
        and excess_lot.get("remaining") == 1,
    )
    recalled = lot_row(api, data["lots"]["recalled"])
    record(results, "recall-status-preserved", recalled.get("status") == "RECALLED")
    supplier = lot_row(api, data["lots"]["supplier"])
    record(results, "supplier-status-preserved", supplier.get("status") == "SUPPLIER_RETURN")
    grocery = Api(base, "accept-grocery")
    _login(grocery, "admin", os.environ["ACCEPTANCE_ADMIN_PASSWORD"])
    _, settings = grocery("GET", "/api/v1/settings")
    record(results, "grocery-has-no-pharmacy-catalog", "pharmacy_catalog" not in set(settings.get("capabilities") or []))
    resold, _ = grocery_resale(grocery, data["grocery"])
    _, stock = grocery("GET", f"/api/v1/inventory/stock?store_id={data['grocery']['store_id']}&q=3F3-GROC")
    rows = stock.get("rows") if isinstance(stock, dict) else stock
    stock_row = next((item for item in (rows or []) if item.get("sku") == "3F3-GROC"), {})
    record(results, "grocery-resale", resold == 200 and stock_row.get("quantity_on_hand") == 2)
    (EVIDENCE / "api-verify.json").write_text(
        json.dumps(
            {
                "results": results,
                "lots": {"valid": valid, "recalled": recalled, "supplier": supplier, "excess": excess_lot},
                "excess_http_status": excess["status"],
                "returns_before": excess["returns_before"],
                "returns_after": excess["returns_after"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if any(item["status"] != "passed" for item in results):
        raise SystemExit("Portal verification failed.")


def lot_row(api: Api, lot_id: str) -> dict:
    _, page = api("GET", "/api/v1/inventory/batches?limit=200")
    for row in page.get("rows") or []:
        _, detail = api("GET", f"/api/v1/inventory/batches/{row['id']}")
        for item in detail.get("items") or []:
            if str(item.get("id") or item.get("batch_item_id")) == lot_id or str(item.get("batch_item_id")) == lot_id:
                return {"status": item.get("lot_status"), "remaining": item.get("quantity_remaining")}
    return {}


def sell_expect(api: Api, data: dict, key: str) -> tuple[int, object]:
    product = data["pharmacy"][key]
    money = line_amounts(api, 1)
    return api(
        "POST",
        "/api/v1/sync/push",
        {
            "device_id": "P3F3",
            "events": [
                {
                    "idempotency_key": str(uuid.uuid4()),
                    "entity_type": "sale",
                    "operation": "upsert",
                    "payload": {
                        "id": str(uuid.uuid4()),
                        "store_id": STORE,
                        "cashier_id": api_me(api),
                        "currency": "USD",
                        "payment_method": "cash",
                        "subtotal_cents": money["subtotal_cents"],
                        "tax_cents": money["tax_cents"],
                        "total_cents": money["total_cents"],
                        "client_sale_id": str(uuid.uuid4()),
                        "items": [
                            {
                                "id": str(uuid.uuid4()),
                                "product_id": product.get("product_id") or "",
                                "quantity": 1,
                                "unit_price_cents": 1500,
                                "tax_cents": money["tax_cents"],
                                "line_total_cents": money["line_total_cents"],
                            }
                        ],
                    },
                    "occurred_at": datetime.now(UTC).isoformat(),
                }
            ],
        },
        auth="device",
        ok=(200, 422),
    )


def api_me(api: Api) -> str:
    _, me = api("GET", "/api/v1/auth/me")
    return me["id"]


def excess_return(api: Api, invoice: str) -> dict:
    _, before = api("GET", "/api/v1/returns")
    before_count = len(before or [])
    _, me = api("GET", "/api/v1/auth/me")
    _, receipt = api("GET", f"/api/v1/returns/receipts/{invoice}")
    item = receipt["items"][0]
    status, body = post_return(
        api,
        {
            "id": str(uuid.uuid4()),
            "original_sale_id": receipt["sale_id"],
            "store_id": receipt["store_id"],
            "cashier_id": me["id"],
            "currency": receipt["currency"],
            "processed_at": datetime.now(UTC).isoformat(),
            "subtotal_cents": item["unit_price_cents"] * 2,
            "tax_refund_cents": 0,
            "restocking_fee_cents": 0,
            "total_refund_cents": item["unit_price_cents"] * 2,
            "reason_notes": "Too many",
            "credit_note_number": None,
            "shift_id": None,
            "items": [
                {
                    "id": str(uuid.uuid4()),
                    "sale_item_id": item["sale_item_id"],
                    "product_id": item["product_id"],
                    "quantity": 2,
                    "unit_price_cents": item["unit_price_cents"],
                    "tax_refund_cents": 0,
                    "restocking_fee_cents": 0,
                    "refund_cents": item["unit_price_cents"] * 2,
                    "condition_status": "unopened_resealable",
                    "reason_code": "changed_mind",
                    "serial_value": None,
                    "serial_kind": None,
                }
            ],
            "tenders": [{"method": "cash", "amount_cents": item["unit_price_cents"] * 2, "store_credit_code": None}],
            "override": None,
        },
    )
    _, after = api("GET", "/api/v1/returns")
    return {"status": status, "body": body if isinstance(body, dict) else {}, "returns_before": before_count, "returns_after": len(after or [])}


def grocery_resale(api: Api, grocery: dict) -> tuple[int, object]:
    _, device = api("POST", "/api/v1/devices", {"store_id": grocery["store_id"], "code": "G3F3B", "name": "Grocery resale"})
    api.device_key = device["key"]
    _, me = api("GET", "/api/v1/auth/me")
    money = line_amounts(api, 1)
    return api(
        "POST",
        "/api/v1/sync/push",
        {
            "device_id": "G3F3B",
            "events": [
                {
                    "idempotency_key": str(uuid.uuid4()),
                    "entity_type": "sale",
                    "operation": "upsert",
                    "payload": {
                        "id": str(uuid.uuid4()),
                        "store_id": grocery["store_id"],
                        "cashier_id": me["id"],
                        "currency": "USD",
                        "payment_method": "cash",
                        "subtotal_cents": money["subtotal_cents"],
                        "tax_cents": money["tax_cents"],
                        "total_cents": money["total_cents"],
                        "client_sale_id": str(uuid.uuid4()),
                        "items": [
                            {
                                "id": str(uuid.uuid4()),
                                "product_id": grocery["product_id"],
                                "quantity": 1,
                                "unit_price_cents": 1500,
                                "tax_cents": money["tax_cents"],
                                "line_total_cents": money["line_total_cents"],
                            }
                        ],
                    },
                    "occurred_at": datetime.now(UTC).isoformat(),
                }
            ],
        },
        auth="device",
        ok=(200, 422),
    )


def record(results: list[dict], name: str, passed: bool) -> None:
    results.append({"name": name, "status": "passed" if passed else "failed"})
    print(f"{'PASS' if passed else 'FAIL'} {name}")


if __name__ == "__main__":
    main()
