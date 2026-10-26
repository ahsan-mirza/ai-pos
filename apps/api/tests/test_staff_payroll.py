import uuid

from app.models.product import Product
from app.models.user import User
from wholesale_support import CABLE, CASHIER_ID, PHONE, STORE, admin, event, line, push, sale, seed

PERIOD = {"from": "2026-10-01", "to": "2026-10-31"}


def test_commissions_pick_the_most_specific_rule(client, session) -> None:
    values = seed(client, phone_units=1)
    headers, _ = admin(client)
    cashier = session.get(User, uuid.UUID(CASHIER_ID))
    phone_category = str(session.get(Product, uuid.UUID(PHONE)).category_id)
    general = client.post(
        "/api/v1/staff/commission-rules",
        headers=headers,
        json={"name": "Everything", "basis": "NET_SALES", "rate_bps": 100},
    )
    assert general.status_code == 201, general.text
    specific = client.post(
        "/api/v1/staff/commission-rules",
        headers=headers,
        json={
            "name": "Phones",
            "basis": "NET_SALES",
            "rate_bps": 300,
            "category_ids": [phone_category],
            "role_ids": [str(cashier.role_id)],
        },
    )
    assert specific.status_code == 201
    body = sale([line(CABLE, 10, 1500), line(PHONE, 1, 79_900, serial=values[0])])
    assert push(client, [event("commission-sale", "sale", body)]).status_code == 200

    person = client.get("/api/v1/staff/commissions", headers=headers, params=PERIOD).json()["staff"][0]
    by_rule = {row["rule_name"]: row for row in person["by_rule"]}
    # Cables earn 1% of 150.00 under the general rule; the phone earns 3% of 799.00 under the phone rule.
    assert by_rule["Everything"]["commission_cents"] == 150
    assert by_rule["Phones"]["commission_cents"] == 2397
    assert person["commission_cents"] == 150 + 2397


def test_payroll_run_with_overtime_commission_and_wps_file(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    client.post(
        "/api/v1/staff/commission-rules", headers=headers, json={"name": "All", "basis": "NET_SALES", "rate_bps": 200}
    )
    assert push(client, [event("payroll-sale", "sale", sale([line(CABLE, 100, 1500)]))]).status_code == 200
    entry = str(uuid.uuid4())
    shift = {
        "id": entry,
        "user_id": CASHIER_ID,
        "store_id": STORE,
        "clock_in_at": "2026-10-19T04:00:00Z",
        "clock_out_at": "2026-10-19T14:00:00Z",
    }
    assert push(client, [event("payroll-clock", "time_entry", shift)]).status_code == 200
    client.post("/api/v1/timesheets/approve", headers=headers, json={"entry_ids": [entry]})

    profile = {
        "labour_id": "10012345678901",
        "bank_routing_code": "803320101",
        "iban": "AE070331234567890123456",
        "job_title": "Cashier",
        "nationality": "Indian",
        "basic_salary_cents": 360_000,
        "housing_allowance_cents": 100_000,
        "transport_allowance_cents": 40_000,
    }
    saved = client.put(f"/api/v1/staff/employees/{CASHIER_ID}", headers=headers, json=profile)
    assert saved.status_code == 200, saved.text
    person = next(row for row in saved.json() if row["user_id"] == CASHIER_ID)
    assert person["profile"]["employee_code"] == "EMP0001"
    assert person["profile"]["job_title"] == "Cashier"
    typed = client.put(
        f"/api/v1/staff/employees/{CASHIER_ID}",
        headers=headers,
        json={**profile, "employee_code": "E999"},
    )
    assert typed.status_code == 422
    again = client.put(f"/api/v1/staff/employees/{CASHIER_ID}", headers=headers, json=profile)
    kept = next(row for row in again.json() if row["user_id"] == CASHIER_ID)
    assert kept["profile"]["employee_code"] == "EMP0001"
    bad_iban = client.put(f"/api/v1/staff/employees/{CASHIER_ID}", headers=headers, json={**profile, "iban": "GB00"})
    assert bad_iban.status_code == 422

    run = client.post("/api/v1/staff/payroll/runs", headers=headers, json={"year": 2026, "month": 10})
    assert run.status_code == 201, run.text
    pay = run.json()["lines"][0]
    # 10 hours worked, 2 of them overtime: 3600.00 / 240 hours x 1.25 x 2 = 37.50.
    assert (pay["overtime_minutes"], pay["overtime_cents"], pay["commission_cents"]) == (120, 3750, 3000)
    assert pay["net_cents"] == 360_000 + 140_000 + 3750 + 3000
    adjusted = client.put(
        f"/api/v1/staff/payroll/runs/{run.json()['id']}/lines/{pay['id']}",
        headers=headers,
        json={"bonus_cents": 10_000, "deductions_cents": 5_000, "unpaid_leave_days": 1, "note": "Advance recovery"},
    ).json()
    line_after = adjusted["lines"][0]
    assert line_after["leave_deduction_cents"] == 500_000 // 30
    assert line_after["net_cents"] == 506_750 + 10_000 - 5_000 - 500_000 // 30

    early = client.get(f"/api/v1/staff/payroll/runs/{run.json()['id']}/wps.sif", headers=headers)
    assert early.status_code == 409
    client.post(f"/api/v1/staff/payroll/runs/{run.json()['id']}/finalize", headers=headers)
    no_employer = client.get(f"/api/v1/staff/payroll/runs/{run.json()['id']}/wps.sif", headers=headers)
    assert no_employer.status_code == 422
    client.put(
        "/api/v1/staff/payroll/settings",
        headers=headers,
        json={"employer_id": "1000000000001", "bank_routing_code": "803320101"},
    )
    sif = client.get(f"/api/v1/staff/payroll/runs/{run.json()['id']}/wps.sif", headers=headers)
    assert sif.status_code == 200 and sif.headers["content-disposition"].endswith('.SIF"')
    edr, scr = sif.text.strip().split("\r\n")
    fields = edr.split(",")
    assert fields[:4] == ["EDR", "10012345678901", "803320101", "AE070331234567890123456"]
    assert fields[4:7] == ["2026-10-01", "2026-10-31", "31"]
    assert float(fields[7]) + float(fields[8]) == line_after["net_cents"] / 100
    assert scr.startswith("SCR,1000000000001,803320101,") and scr.split(",")[5:7] == ["102026", "1"]
    locked = client.put(
        f"/api/v1/staff/payroll/runs/{run.json()['id']}/lines/{pay['id']}", headers=headers, json={"bonus_cents": 1}
    )
    assert locked.status_code == 409
    again = client.post("/api/v1/staff/payroll/runs", headers=headers, json={"year": 2026, "month": 10})
    assert again.status_code == 409
