import json
import uuid

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.product import Product
from app.models.staff import EmployeeProfile
from app.models.user import User
from wholesale_support import CABLE, CASHIER_ID, PHONE, STORE, admin, device, event, line, push, sale, seed

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


IBAN = "AE070331234567890123456"
PROFILE = {
    "labour_id": "10012345678901",
    "bank_routing_code": "803320101",
    "iban": IBAN,
    "bank_name": "Salary Bank",
    "account_holder": "Front Cashier",
    "job_title": "Cashier",
    "basic_salary_cents": 360_000,
    "housing_allowance_cents": 100_000,
    "transport_allowance_cents": 40_000,
}


def _portal(client, headers, username: str, permissions: list[str]) -> dict[str, str]:
    role = client.post("/api/v1/roles", headers=headers, json={"name": username, "permissions": permissions})
    assert role.status_code == 201, role.text
    created = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": username,
            "email": f"{username}@example.com",
            "full_name": username,
            "role_id": role.json()["id"],
            "password": "payroll-password-1",
            "has_portal_access": True,
        },
    )
    assert created.status_code == 201, created.text
    login = client.post("/api/v1/auth/login-password", json={"username": username, "password": "payroll-password-1"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_salary_is_versioned_and_an_approved_run_keeps_its_snapshot(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    saved = client.put(f"/api/v1/staff/employees/{CASHIER_ID}", headers=headers, json=PROFILE)
    assert saved.status_code == 200, saved.text
    session.expire_all()
    stored = session.scalar(select(EmployeeProfile).where(EmployeeProfile.user_id == uuid.UUID(CASHIER_ID)))
    assert stored is not None
    assert stored.iban == ""
    assert stored.iban_last4 == "3456"
    assert IBAN not in (stored.iban_encrypted or "")
    audits = list(session.scalars(select(AuditLog).where(AuditLog.action == "payroll.profile")))
    assert audits
    trail = json.dumps(
        [{"details": row.details, "new": row.new_values, "old": row.old_values} for row in audits],
        default=str,
    )
    assert IBAN not in trail

    checksum = client.put(
        f"/api/v1/staff/employees/{CASHIER_ID}", headers=headers, json={**PROFILE, "iban": "AE000331234567890123456"}
    )
    assert checksum.status_code == 422

    run = client.post("/api/v1/staff/payroll/runs", headers=headers, json={"year": 2026, "month": 11})
    assert run.status_code == 201, run.text
    original = run.json()["lines"][0]["basic_cents"]
    assert client.post(f"/api/v1/staff/payroll/runs/{run.json()['id']}/finalize", headers=headers).status_code == 200
    locked = client.put(
        f"/api/v1/staff/employees/{CASHIER_ID}",
        headers=headers,
        json={**PROFILE, "basic_salary_cents": 400_000},
    )
    assert locked.status_code == 409
    later = client.put(
        f"/api/v1/staff/employees/{CASHIER_ID}",
        headers=headers,
        json={**PROFILE, "basic_salary_cents": 400_000, "effective_from": "2026-12-01"},
    )
    assert later.status_code == 200, later.text
    history = client.get(f"/api/v1/staff/employees/{CASHIER_ID}/salary-history", headers=headers)
    assert history.status_code == 200
    assert len(history.json()) == 2
    kept = client.get("/api/v1/staff/payroll/runs", headers=headers).json()[0]
    assert kept["lines"][0]["basic_cents"] == original


def test_draft_profile_and_unapproved_time_are_reported(client) -> None:
    seed(client)
    headers, _ = admin(client)
    draft = client.put(
        f"/api/v1/staff/employees/{CASHIER_ID}",
        headers=headers,
        json={"profile_status": "DRAFT", "job_title": "Cashier", "basic_salary_cents": 100_000},
    )
    assert draft.status_code == 200, draft.text
    blocked = client.post("/api/v1/staff/payroll/runs", headers=headers, json={"year": 2026, "month": 9})
    assert blocked.status_code == 422
    assert "draft" in blocked.text.lower()

    assert client.put(f"/api/v1/staff/employees/{CASHIER_ID}", headers=headers, json=PROFILE).status_code == 200
    entry = str(uuid.uuid4())
    shift = {
        "id": entry,
        "user_id": CASHIER_ID,
        "store_id": STORE,
        "clock_in_at": "2026-09-02T04:00:00Z",
        "clock_out_at": "2026-09-02T14:00:00Z",
    }
    assert push(client, [event("unapproved-clock", "time_entry", shift)]).status_code == 200
    run = client.post("/api/v1/staff/payroll/runs", headers=headers, json={"year": 2026, "month": 9})
    assert run.status_code == 201, run.text
    body = run.json()
    assert body["lines"][0]["overtime_cents"] == 0
    assert any(row["code"] == "unapproved_timesheet" for row in body["exceptions"])


def test_review_payment_and_payslip_stay_separate_from_the_wps_file(client) -> None:
    seed(client)
    headers, actor = admin(client)
    client.put(f"/api/v1/staff/employees/{CASHIER_ID}", headers=headers, json=PROFILE)
    reviewer = _portal(client, headers, "payroll.reviewer", ["portal:access", "payroll:manage"])
    stranger = _portal(client, headers, "payroll.stranger", ["portal:access"])
    client.put(
        "/api/v1/staff/payroll/settings",
        headers=headers,
        json={
            "employer_id": "1000000000001",
            "bank_routing_code": "803320101",
            "bank_name": "Salary Bank",
            "segregate_approval": True,
        },
    )
    run = client.post("/api/v1/staff/payroll/runs", headers=headers, json={"year": 2026, "month": 8})
    assert run.status_code == 201, run.text
    run_id = run.json()["id"]
    line_id = run.json()["lines"][0]["id"]
    net = run.json()["lines"][0]["net_cents"]
    submitted = client.post(f"/api/v1/staff/payroll/runs/{run_id}/submit", headers=headers)
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "UNDER_REVIEW"
    assert client.post(f"/api/v1/staff/payroll/runs/{run_id}/recalculate", headers=headers).status_code == 409
    own = client.post(f"/api/v1/staff/payroll/runs/{run_id}/approve", headers=headers)
    assert own.status_code == 403
    rejected = client.post(
        f"/api/v1/staff/payroll/runs/{run_id}/reject",
        headers=reviewer,
        json={"note": "Check overtime"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "DRAFT"
    assert client.post(f"/api/v1/staff/payroll/runs/{run_id}/submit", headers=headers).status_code == 200
    assert client.post(f"/api/v1/staff/payroll/runs/{run_id}/approve", headers=reviewer).status_code == 200
    assert actor
    early = client.get(f"/api/v1/staff/payroll/payslips/{line_id}.pdf", headers=headers)
    # The slip exists only after approval. The request above approved it, so the file is available.
    assert early.status_code == 200
    assert early.content.startswith(b"%PDF")
    blocked = client.get(f"/api/v1/staff/payroll/payslips/{line_id}.pdf", headers=stranger)
    assert blocked.status_code == 403
    assert client.get(f"/api/v1/staff/payroll/payslips/{line_id}.pdf", headers=device()).status_code == 403
    preview = client.post(f"/api/v1/staff/payroll/runs/{run_id}/wps/validate", headers=headers)
    assert preview.status_code == 200
    assert preview.json()["ready"] is True
    assert preview.json()["provider"] == "uae_sif_edr_scr"
    assert "not a MOHRE submission receipt" in preview.json()["provider_note"]
    sif = client.get(f"/api/v1/staff/payroll/runs/{run_id}/wps.sif", headers=headers)
    assert sif.status_code == 200
    listed = client.get("/api/v1/staff/payroll/runs", headers=headers).json()
    assert listed[0]["payment_status"] == "GENERATED"
    paid = client.post(
        f"/api/v1/staff/payroll/runs/{run_id}/payments",
        headers=headers,
        json={"amount_cents": net, "reference": "BANK-1001", "status": "PAID"},
    )
    assert paid.status_code == 201, paid.text
    assert client.get("/api/v1/staff/payroll/runs", headers=headers).json()[0]["payment_status"] == "PAID"
    duplicate = client.post(
        f"/api/v1/staff/payroll/runs/{run_id}/payments",
        headers=headers,
        json={"amount_cents": net, "reference": "BANK-1001", "status": "PAID"},
    )
    assert duplicate.status_code == 409

    cancelled = client.post("/api/v1/staff/payroll/runs", headers=headers, json={"year": 2026, "month": 7})
    assert cancelled.status_code == 201, cancelled.text
    assert client.post(
        f"/api/v1/staff/payroll/runs/{cancelled.json()['id']}/cancel", headers=headers, json={"note": ""}
    ).status_code == 200
    replacement = client.post("/api/v1/staff/payroll/runs", headers=headers, json={"year": 2026, "month": 7})
    assert replacement.status_code == 201, replacement.text
